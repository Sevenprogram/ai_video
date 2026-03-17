"""
AI 视频工作流仪表盘 - FastAPI 后端

启动方式（在项目根目录）：
    uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import queue
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from main import DEFAULT_PROMPT, run_workflow
from config import VIDEO_DURATION_MINUTES

# --------------------------------------------------------------------------- #
# 应用初始化
# --------------------------------------------------------------------------- #

app = FastAPI(title="AI视频工作流仪表盘", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
OUTPUTS_DIR = ROOT / "outputs"

# --------------------------------------------------------------------------- #
# 任务存储（内存）
# --------------------------------------------------------------------------- #

# job_id -> {status, created_at, prompt, logs, artifacts, error}
JOBS: Dict[str, Dict[str, Any]] = {}
# job_id -> queue.Queue  （用于 SSE 推送）
JOB_QUEUES: Dict[str, queue.Queue] = {}


def _make_job(job_id: str, prompt: str) -> dict:
    return {
        "id":         job_id,
        "status":     "pending",   # pending / running / done / error
        "created_at": datetime.now().isoformat(),
        "prompt":     prompt,
        "logs":       [],          # [{step, msg, ts, extra}]
        "artifacts":  {},
        "error":      None,
        "current_step": None,
        "steps": {                 # step -> "pending" / "running" / "done" / "error"
            "script":     "pending",
            "audio":      "pending",
            "storyboard": "pending",
            "openclaw":   "pending",
            "pipeline":   "pending",
        },
    }


# --------------------------------------------------------------------------- #
# Pydantic 模型
# --------------------------------------------------------------------------- #

class CreateJobRequest(BaseModel):
    prompt: Optional[str] = None
    wait_for_openclaw: bool = True   # False = 发送后不等回复，直接用现有录屏继续合成
    duration_minutes: int = VIDEO_DURATION_MINUTES  # 目标视频时长（分钟）


# --------------------------------------------------------------------------- #
# 工作流后台线程
# --------------------------------------------------------------------------- #

def _workflow_thread(job_id: str, prompt: str, wait_for_openclaw: bool = True, duration_minutes: int = VIDEO_DURATION_MINUTES):
    job = JOBS[job_id]
    q   = JOB_QUEUES[job_id]
    job["status"] = "running"

    _STEP_ORDER = ["script", "audio", "storyboard", "openclaw", "pipeline"]
    _current_step = [None]

    def log_fn(step: str, msg: str, **extra):
        ts = datetime.now().isoformat()

        # 更新步骤状态
        if step in _STEP_ORDER:
            # 将上一步标为 done（如果有的话）
            prev = _current_step[0]
            if prev and prev != step and job["steps"].get(prev) == "running":
                job["steps"][prev] = "done"
            job["steps"][step] = "running"
            _current_step[0] = step
            job["current_step"] = step
        elif step == "done":
            # 所有步骤完成
            for s in _STEP_ORDER:
                if job["steps"][s] == "running":
                    job["steps"][s] = "done"
            _current_step[0] = "done"
        elif step == "error":
            cur = _current_step[0]
            if cur and cur in _STEP_ORDER:
                job["steps"][cur] = "error"

        # 追加日志
        entry = {"step": step, "msg": msg, "ts": ts}
        if extra:
            entry["extra"] = {k: v for k, v in extra.items()
                              if k not in ("artifacts",) and _is_json_safe(v)}
        job["logs"].append(entry)

        # 推入 SSE 队列
        payload = json.dumps(entry, ensure_ascii=False)
        q.put(f"data: {payload}\n\n")

    try:
        outputs_base = str(OUTPUTS_DIR)
        artifacts = run_workflow(
            prompt,
            log_fn=log_fn,
            outputs_base=outputs_base,
            wait_for_openclaw=wait_for_openclaw,
            duration_minutes=duration_minutes,
        )
        job["artifacts"] = {k: str(v) if v else None for k, v in artifacts.items()
                            if k != "shots"}
        job["artifacts"]["shots"] = artifacts.get("shots", [])
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"]  = str(exc)
        ts = datetime.now().isoformat()
        entry = {"step": "error", "msg": str(exc), "ts": ts}
        job["logs"].append(entry)
        q.put(f"data: {json.dumps(entry, ensure_ascii=False)}\n\n")
    finally:
        q.put(None)  # 终止信号


def _is_json_safe(v) -> bool:
    try:
        json.dumps(v)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# API 端点
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/default-prompt")
def get_default_prompt():
    return {"prompt": DEFAULT_PROMPT}


@app.post("/api/jobs", status_code=201)
def create_job(body: CreateJobRequest):
    job_id   = str(uuid.uuid4())
    prompt   = (body.prompt or "").strip() or DEFAULT_PROMPT
    wait     = body.wait_for_openclaw
    duration = body.duration_minutes

    job = _make_job(job_id, prompt)
    job["wait_for_openclaw"]  = wait
    job["duration_minutes"]   = duration
    JOBS[job_id] = job
    JOB_QUEUES[job_id] = queue.Queue()

    t = threading.Thread(
        target=_workflow_thread, args=(job_id, prompt, wait, duration), daemon=True
    )
    t.start()

    return {"job_id": job_id}


@app.get("/api/jobs")
def list_jobs():
    result = []
    for job in sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True):
        result.append({
            "id":           job["id"],
            "status":       job["status"],
            "created_at":   job["created_at"],
            "prompt":       job["prompt"][:80] + ("..." if len(job["prompt"]) > 80 else ""),
            "current_step": job.get("current_step"),
            "steps":        job["steps"],
        })
    return result


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return {
        "id":           job["id"],
        "status":       job["status"],
        "created_at":   job["created_at"],
        "prompt":       job["prompt"],
        "steps":        job["steps"],
        "current_step": job.get("current_step"),
        "logs":         job["logs"],
        "artifacts":    job["artifacts"],
        "error":        job["error"],
    }


@app.get("/api/jobs/{job_id}/stream")
def stream_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")

    q = JOB_QUEUES.get(job_id)

    def event_gen():
        # 先回放历史日志
        for entry in job["logs"]:
            yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"

        # 如果已结束就直接返回
        if job["status"] in ("done", "error") and q is None:
            return

        # 持续读取新事件
        if q:
            while True:
                item = q.get()
                if item is None:
                    break
                yield item

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/files/{folder}/{filename}")
def serve_file(folder: str, filename: str):
    """提供 outputs/ 下的文件访问（文稿/音频/xlsx 等）。"""
    path = OUTPUTS_DIR / folder / filename
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(path))


# --------------------------------------------------------------------------- #
# 静态文件（前端）
# --------------------------------------------------------------------------- #

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
