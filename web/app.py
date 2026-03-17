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
from config import (
    OPENCLAW_REPLY_TIMEOUT,
    VIDEO_SHOOT_DIR,
    VIDEO_DIGITAL_HUMAN_DIR,
    VIDEO_CARTOON_HEAD_DIR,
    VIDEO_DIGITAL_HUMAN_DEFAULT,
    VIDEO_CARTOON_HEAD_DEFAULT,
    VIDEO_SHOOT_DEFAULT,
)

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


def _log(job_id: str, msg: str, step: str = "info") -> None:
    ts = datetime.now().isoformat()
    entry = {"ts": ts, "text": msg, "step": step, "msg": msg}
    with jobs_lock:
        if job_id not in jobs:
            jobs[job_id] = {"logs": [], "status": "pending", "created_at": ts}
        jobs[job_id]["logs"].append(entry)
        q = jobs[job_id].get("log_queue")
        if q:
            try:
                q.put_nowait(entry)
            except queue.Full:
                pass


# ─── API：主流程 ─────────────────────────────────────────────────────
class CreateJobRequest(BaseModel):
    script: str
    openclaw_timeout: Optional[int] = None
    target_duration_minutes: Optional[int] = None  # 文稿目标时长（分钟）
    wait_openclaw: Optional[bool] = True  # 是否等待 OpenClaw 回复
    use_local_videos: Optional[bool] = False  # 使用本地视频（不调用 OpenClaw）
    local_digital_human: Optional[str] = None  # 数字人视频路径/文件名
    local_cartoon_head: Optional[str] = None   # 卡通头部视频路径/文件名
    local_recording: Optional[str] = None      # 录屏视频路径/文件名


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
            "script": req.script[:200] if req.script else "",
            "folder": None,
            "steps": {},
            "artifacts": {},
            "use_local_videos": req.use_local_videos or False,
            "local_digital_human": req.local_digital_human or "",
            "local_cartoon_head": req.local_cartoon_head or "",
            "local_recording": req.local_recording or "",
        }

    def run():
        with jobs_lock:
            jobs[job_id]["status"] = "running"
        try:
            target_mins = req.target_duration_minutes if req.target_duration_minutes is not None else None
            _log(job_id, "[1/4] 生成分镜提示词...", "storyboard")
            prompt = build_storyboard_prompt(req.script, minutes=target_mins)
            _log(job_id, "[2/4] 调用 LLM 生成分镜 JSON...", "storyboard")
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
            with jobs_lock:
                jobs[job_id]["folder"] = folder_name
                jobs[job_id]["steps"]["storyboard"] = "done"
                jobs[job_id]["artifacts"] = {"script": True, "storyboard": True, "shots": shots, "folder": folder_name}
            _log(job_id, f"[3/4] 生成录屏指令，共 {len(shots)} 个分镜...", "openclaw")
            instruction = build_recording_instruction(shots, folder_name)
            (out_dir / "recording_task.txt").write_text(instruction, encoding="utf-8")
            with jobs_lock:
                jobs[job_id]["artifacts"]["recording_task"] = True
            _log(job_id, "[4/4] 等待发送给 OpenClaw...", "openclaw")
            with jobs_lock:
                j = jobs.get(job_id, {})
                if j.get("skip_openclaw"):
                    _log(job_id, "用户选择跳过，使用最新/指定视频继续", "done")
                    jobs[job_id]["status"] = "done"
                    return
                if j.get("use_local_videos"):
                    _log(job_id, "使用本地视频模式，跳过 OpenClaw", "done")
                    dig = _resolve_local_video_path(
                        "digital_human", j.get("local_digital_human"),
                        VIDEO_DIGITAL_HUMAN_DEFAULT, VIDEO_DIGITAL_HUMAN_DIR
                    )
                    cart = _resolve_local_video_path(
                        "cartoon_head", j.get("local_cartoon_head"),
                        VIDEO_CARTOON_HEAD_DEFAULT, VIDEO_CARTOON_HEAD_DIR
                    )
                    rec = _resolve_local_video_path(
                        "recording", j.get("local_recording"),
                        VIDEO_SHOOT_DEFAULT, VIDEO_SHOOT_DIR
                    )
                    jobs[job_id]["artifacts"]["local_videos"] = {
                        "digital_human": dig,
                        "cartoon_head": cart,
                        "recording": rec,
                    }
                    jobs[job_id]["steps"]["openclaw"] = "done"
                    jobs[job_id]["status"] = "done"
                    return
            timeout_sec = req.openclaw_timeout if req.openclaw_timeout is not None else OPENCLAW_REPLY_TIMEOUT
            wait_oc = req.wait_openclaw if req.wait_openclaw is not None else True
            reply = send_as_user_and_wait_reply(instruction, timeout=timeout_sec, wait=wait_oc)
            with jobs_lock:
                jobs[job_id]["artifacts"]["openclaw_reply"] = reply[:500] if reply else ""
                jobs[job_id]["steps"]["openclaw"] = "done"
            _log(job_id, f"OpenClaw 回复：{reply[:200] if reply else '（无）'}...", "done")
            jobs[job_id]["status"] = "done"
        except Exception as e:
            _log(job_id, f"[错误] {e}", "error")
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


def _get_log_entries(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            return None
        q = jobs[job_id].get("log_queue")
        if not q:
            q = queue.Queue()
            jobs[job_id]["log_queue"] = q
            for e in jobs[job_id].get("logs", []):
                q.put(e)
        return q


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        out = []
        for jid, j in jobs.items():
            out.append({
                "id": jid,
                "status": j.get("status", "pending"),
                "created_at": j.get("created_at", ""),
                "prompt": j.get("script", "")[:80],
            })
        out.sort(key=lambda x: x["created_at"] or "", reverse=True)
        return out


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "job not found")
        j = jobs[job_id]
        return {
            "id": job_id,
            "status": j.get("status", "pending"),
            "created_at": j.get("created_at", ""),
            "steps": j.get("steps", {}),
            "logs": j.get("logs", []),
            "artifacts": j.get("artifacts", {}),
        }


@app.get("/api/files/{folder}/{filename:path}")
def serve_file(folder: str, filename: str):
    if ".." in folder or ".." in filename:
        raise HTTPException(404, "file not found")
    path = (OUTPUTS / folder / filename).resolve()
    if not path.exists() or not path.is_file() or not str(path).startswith(str(OUTPUTS.resolve())):
        raise HTTPException(404, "file not found")
    return FileResponse(path)


@app.get("/api/jobs/{job_id}/logs")
def stream_logs(job_id: str):
    q = _get_log_entries(job_id)
    if not q:
        raise HTTPException(404, "job not found")

    def gen():
        while True:
            try:
                entry = q.get(timeout=15)
                payload = {"text": entry.get("text", entry.get("msg", "")), "step": entry.get("step", "info"), "ts": entry.get("ts", ""), "msg": entry.get("msg", entry.get("text", ""))}
                yield f"data: {json.dumps(payload)}\n\n"
            except queue.Empty:
                yield ": ping\n\n"
            except GeneratorExit:
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/jobs/{job_id}/stream")
def stream_job(job_id: str):
    """Alias for /logs, compatible with reference frontend."""
    return stream_logs(job_id)


@app.get("/api/local-videos")
def list_local_videos(source: Optional[str] = Query(None)):
    """
    列出本地视频文件。source: video_shoot | digital_human | cartoon_head
    不传则返回所有类型的文件列表。
    """
    VIDEO_EXT = (".mp4", ".webm", ".mov", ".avi", ".mkv")
    CFG = {"video_shoot": VIDEO_SHOOT_DIR, "digital_human": VIDEO_DIGITAL_HUMAN_DIR, "cartoon_head": VIDEO_CARTOON_HEAD_DIR}
    result = {}

    def scan_dir(cfg_key: str) -> list:
        p = Path(CFG.get(cfg_key, ""))
        base = (ROOT / p).resolve() if not p.is_absolute() else p
        if not base.exists() or not base.is_dir():
            return []
        files = []
        try:
            for f in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.is_file() and f.suffix.lower() in VIDEO_EXT:
                    files.append(f.name)
        except OSError:
            pass
        return files[:50]

    if not source or source == "video_shoot":
        result["video_shoot"] = scan_dir("video_shoot")
    if not source or source == "digital_human":
        result["digital_human"] = scan_dir("digital_human")
    if not source or source == "cartoon_head":
        result["cartoon_head"] = scan_dir("cartoon_head")
    return result


@app.get("/api/local-video-defaults")
def get_local_video_defaults():
    """返回数字人、卡通、录屏的默认路径（用于 UI 占位及用户未填写时使用）。"""
    return {
        "digital_human": f"{VIDEO_DIGITAL_HUMAN_DIR}/{VIDEO_DIGITAL_HUMAN_DEFAULT}",
        "cartoon_head": f"{VIDEO_CARTOON_HEAD_DIR}/{VIDEO_CARTOON_HEAD_DEFAULT}",
        "recording": f"{VIDEO_SHOOT_DIR}/{VIDEO_SHOOT_DEFAULT}",
    }


def _resolve_local_video_path(typename: str, value: Optional[str], default_file: str, dir_path: str) -> str:
    """将用户输入解析为完整路径。空则使用默认路径。"""
    if value and value.strip():
        v = value.strip()
        p = Path(v)
        if p.is_absolute() or "/" in v or "\\" in v:
            return v
        return f"{dir_path}/{v}"
    return f"{dir_path}/{default_file}"


# ─── API：录屏先行 ───────────────────────────────────────────────────
recording_jobs: dict = {}


class CreateRecordingJobRequest(BaseModel):
    prompt: Optional[str] = None
    output_filename: Optional[str] = None
    wait_openclaw: Optional[bool] = True  # 是否等待 OpenClaw 回复
    use_local_videos: Optional[bool] = False  # 使用本地视频（不调用 OpenClaw）
    local_digital_human: Optional[str] = None
    local_cartoon_head: Optional[str] = None
    local_recording: Optional[str] = None


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
            "prompt": req.prompt or "",
            "output_filename": req.output_filename or "",
            "openclaw_reply": None,
            "use_local_videos": req.use_local_videos or False,
            "local_digital_human": req.local_digital_human or "",
            "local_cartoon_head": req.local_cartoon_head or "",
            "local_recording": req.local_recording or "",
        }

    def run():
        with jobs_lock:
            recording_jobs[job_id]["status"] = "running"
        try:
            _log_recording(job_id, "录屏先行流程启动")
            with jobs_lock:
                use_local = recording_jobs[job_id].get("use_local_videos")
            if use_local:
                _log_recording(job_id, "使用本地视频模式，跳过 OpenClaw")
                with jobs_lock:
                    rj = recording_jobs[job_id]
                    rj["resolved_local_videos"] = {
                        "digital_human": _resolve_local_video_path(
                            "digital_human", rj.get("local_digital_human"),
                            VIDEO_DIGITAL_HUMAN_DEFAULT, VIDEO_DIGITAL_HUMAN_DIR
                        ),
                        "cartoon_head": _resolve_local_video_path(
                            "cartoon_head", rj.get("local_cartoon_head"),
                            VIDEO_CARTOON_HEAD_DEFAULT, VIDEO_CARTOON_HEAD_DIR
                        ),
                        "recording": _resolve_local_video_path(
                            "recording", rj.get("local_recording"),
                            VIDEO_SHOOT_DEFAULT, VIDEO_SHOOT_DIR
                        ),
                    }
                    recording_jobs[job_id]["status"] = "done"
                return
            if not req.prompt:
                _log_recording(job_id, "错误：缺少提示词")
                recording_jobs[job_id]["status"] = "error"
                return
            _log_recording(job_id, "发送给 OpenClaw...")
            wait_oc = req.wait_openclaw if req.wait_openclaw is not None else True
            reply = send_as_user_and_wait_reply(req.prompt, timeout=OPENCLAW_REPLY_TIMEOUT, wait=wait_oc)
            _log_recording(job_id, f"回复：{reply[:200] if reply else '（无）'}...")
            with jobs_lock:
                recording_jobs[job_id]["openclaw_reply"] = reply
                recording_jobs[job_id]["status"] = "done"
        except Exception as e:
            _log_recording(job_id, f"错误：{e}")
            recording_jobs[job_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/recording/jobs")
def list_recording_jobs():
    with jobs_lock:
        items = [
            {
                "id": jid,
                "status": data.get("status", "pending"),
                "created_at": data.get("created_at", ""),
                "prompt": (data.get("prompt") or "")[:80],
            }
            for jid, data in sorted(
                recording_jobs.items(),
                key=lambda x: x[1].get("created_at", ""),
                reverse=True,
            )
        ]
    return items


@app.get("/api/recording/jobs/{job_id}")
def get_recording_job(job_id: str):
    with jobs_lock:
        if job_id not in recording_jobs:
            raise HTTPException(404, "job not found")
        data = recording_jobs[job_id]
    return {
        "id": job_id,
        "status": data.get("status", "pending"),
        "created_at": data.get("created_at", ""),
        "prompt": data.get("prompt", ""),
        "output_filename": data.get("output_filename", ""),
        "openclaw_reply": data.get("openclaw_reply"),
        "logs": [
            {"ts": e.get("ts"), "text": e.get("text", ""), "step": "info"}
            for e in data.get("logs", [])
        ],
    }


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
