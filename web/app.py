"""
Web 服务：视频工作流、录屏任务的 API 与 SSE 日志流。
"""
import os
import sys
import json
import uuid
import queue
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# 导入主流程
from main import build_storyboard_prompt, build_recording_instruction
from module import gemini_complete
from openclaw import send_as_user_and_wait_reply
from config import OPENCLAW_REPLY_TIMEOUT

app = FastAPI(title="AI Video")
ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

# 静态文件
STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ─── 任务状态 ─────────────────────────────────────────────────────────
jobs: dict = {}
jobs_lock = threading.Lock()


def _log(job_id: str, msg: str) -> None:
    with jobs_lock:
        if job_id not in jobs:
            jobs[job_id] = {"logs": [], "status": "pending", "created_at": datetime.now().isoformat()}
        jobs[job_id]["logs"].append({"ts": datetime.now().isoformat(), "text": msg})
        q = jobs[job_id].get("log_queue")
        if q:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


# ─── API：主流程 ─────────────────────────────────────────────────────
class CreateJobRequest(BaseModel):
    script: str


@app.post("/api/jobs")
def create_job(req: CreateJobRequest):
    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        jobs[job_id] = {
            "logs": [],
            "status": "pending",
            "log_queue": queue.Queue(),
            "created_at": datetime.now().isoformat(),
            "skip_openclaw": False,
            "openclaw_manual_filename": None,
        }

    def run():
        try:
            _log(job_id, "[1/4] 生成分镜提示词...")
            prompt = build_storyboard_prompt(req.script)
            _log(job_id, "[2/4] 调用 LLM 生成分镜 JSON...")
            storyboard = gemini_complete(prompt)
            text = storyboard.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            data = json.loads(text)
            shots = data.get("shots", data) if isinstance(data, dict) else data
            folder_name = f"视频_{datetime.now().strftime('%Y%m%d_%H%M')}"
            out_dir = OUTPUTS / folder_name
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "storyboard.txt").write_text(storyboard, encoding="utf-8")
            (out_dir / "script.txt").write_text(req.script, encoding="utf-8")
            _log(job_id, f"[3/4] 生成录屏指令，共 {len(shots)} 个分镜...")
            instruction = build_recording_instruction(shots, folder_name)
            (out_dir / "recording_task.txt").write_text(instruction, encoding="utf-8")
            _log(job_id, "[4/4] 等待发送给 OpenClaw...")
            with jobs_lock:
                j = jobs.get(job_id, {})
                if j.get("skip_openclaw"):
                    _log(job_id, "用户选择跳过，使用最新/指定视频继续")
                    jobs[job_id]["status"] = "done"
                    return
            reply = send_as_user_and_wait_reply(instruction, timeout=OPENCLAW_REPLY_TIMEOUT)
            _log(job_id, f"OpenClaw 回复：{reply[:200] if reply else '（无）'}...")
            jobs[job_id]["status"] = "done"
        except Exception as e:
            _log(job_id, f"[错误] {e}")
            jobs[job_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/skip-openclaw")
def skip_openclaw(job_id: str, filename: Optional[str] = Query(None)):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "job not found")
        jobs[job_id]["skip_openclaw"] = True
        if filename:
            jobs[job_id]["openclaw_manual_filename"] = filename
    return {"ok": True}


@app.get("/api/jobs/{job_id}/logs")
def stream_logs(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "job not found")
        q = jobs[job_id].get("log_queue")
        if not q:
            q = queue.Queue()
            jobs[job_id]["log_queue"] = q
            for log in jobs[job_id].get("logs", []):
                q.put(log.get("text", ""))

    def gen():
        while True:
            try:
                msg = q.get(timeout=15)
                yield f"data: {json.dumps({'text': msg})}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
            except GeneratorExit:
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ─── API：录屏先行 ───────────────────────────────────────────────────
recording_jobs: dict = {}


class CreateRecordingJobRequest(BaseModel):
    prompt: Optional[str] = None


def _log_recording(job_id: str, msg: str) -> None:
    with jobs_lock:
        if job_id in recording_jobs:
            recording_jobs[job_id]["logs"].append({"ts": datetime.now().isoformat(), "text": msg})
            q = recording_jobs[job_id].get("log_queue")
            if q:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass


@app.post("/api/recording/jobs")
def create_recording_job(req: CreateRecordingJobRequest):
    job_id = str(uuid.uuid4())[:8]
    with jobs_lock:
        recording_jobs[job_id] = {
            "logs": [],
            "status": "pending",
            "log_queue": queue.Queue(),
            "created_at": datetime.now().isoformat(),
        }

    def run():
        try:
            _log_recording(job_id, "录屏先行流程启动")
            if not req.prompt:
                _log_recording(job_id, "错误：缺少提示词")
                recording_jobs[job_id]["status"] = "error"
                return
            _log_recording(job_id, "发送给 OpenClaw...")
            reply = send_as_user_and_wait_reply(req.prompt, timeout=OPENCLAW_REPLY_TIMEOUT)
            _log_recording(job_id, f"回复：{reply[:200] if reply else '（无）'}...")
            recording_jobs[job_id]["status"] = "done"
        except Exception as e:
            _log_recording(job_id, f"错误：{e}")
            recording_jobs[job_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/recording/jobs/{job_id}/skip-openclaw")
def skip_recording_openclaw(job_id: str, filename: Optional[str] = Query(None)):
    with jobs_lock:
        if job_id not in recording_jobs:
            raise HTTPException(404, "job not found")
        recording_jobs[job_id]["skip_openclaw"] = True
        if filename:
            recording_jobs[job_id]["openclaw_manual_filename"] = filename
    return {"ok": True}


@app.get("/api/recording/jobs/{job_id}/logs")
def stream_recording_logs(job_id: str):
    with jobs_lock:
        if job_id not in recording_jobs:
            raise HTTPException(404, "job not found")
        q = recording_jobs[job_id].get("log_queue")
        if not q:
            q = queue.Queue()
            recording_jobs[job_id]["log_queue"] = q
            for log in recording_jobs[job_id].get("logs", []):
                q.put(log.get("text", ""))

    def gen():
        while True:
            try:
                msg = q.get(timeout=15)
                yield f"data: {json.dumps({'text': msg})}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
            except GeneratorExit:
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ─── 页面 ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index():
    path = STATIC / "index.html"
    if path.exists():
        return FileResponse(path)
    return HTMLResponse("<h1>AI Video</h1><p>请将 index.html 放入 web/static/</p>")


@app.get("/recording", response_class=HTMLResponse)
def recording():
    path = STATIC / "recording.html"
    if path.exists():
        return FileResponse(path)
    return HTMLResponse("<h1>录屏先行</h1><p>请将 recording.html 放入 web/static/</p>")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
