from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .pipeline import PipelineError, extract_bvid, normalize_bilibili_input, run_pipeline

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
INDEX_PATH = DATA_DIR / "index.json"
STATIC_DIR = ROOT / "static"

app = FastAPI(title="Biliload", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def allow_private_network_access(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

executor = ThreadPoolExecutor(max_workers=int(os.getenv("BILILOAD_WORKERS", "1")))
lock = threading.RLock()
jobs: dict[str, dict] = {}


class CreateJobRequest(BaseModel):
    url: str = Field(min_length=1)
    task_type: Literal["subtitle", "video"] = "subtitle"
    source_language: str = Field(default="auto")
    whisper_model: str = Field(default="small")
    translator: Literal["google", "none"] = "google"
    cookies_browser: Literal["chrome", "firefox", "edge", "safari", "none"] = "chrome"


class JobResponse(BaseModel):
    id: str
    status: str
    progress: float
    message: str
    created_at: str
    updated_at: str
    url: str
    source_language: str
    whisper_model: str
    translator: str
    cookies_browser: str | None
    task_type: str = "subtitle"
    title: str | None = None
    bvid: str | None = None
    detected_language: str | None = None
    error: str | None = None
    files: dict[str, str] = {}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=JobResponse)
def create_job(request: CreateJobRequest) -> dict:
    job_id = uuid.uuid4().hex[:12]
    now = utc_now()
    cookies_browser = None if request.cookies_browser == "none" else request.cookies_browser
    try:
        normalized_url, bvid = normalize_bilibili_input(request.url)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = {
        "id": job_id,
        "status": "queued",
        "progress": 0.0,
        "message": "任务已排队",
        "created_at": now,
        "updated_at": now,
        "url": normalized_url,
        "input": request.url,
        "task_type": request.task_type,
        "source_language": request.source_language,
        "whisper_model": request.whisper_model,
        "translator": request.translator,
        "cookies_browser": cookies_browser,
        "title": None,
        "bvid": bvid,
        "detected_language": None,
        "error": None,
        "files": {},
    }
    with lock:
        jobs[job_id] = job
    executor.submit(run_job, job_id)
    return job


@app.get("/api/jobs", response_model=list[JobResponse])
def list_jobs() -> list[dict]:
    load_jobs_from_disk()
    with lock:
        return sorted(jobs.values(), key=lambda job: job["created_at"], reverse=True)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> dict:
    with lock:
        job = jobs.get(job_id)
        if not job:
            job = load_job_from_disk(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@app.get("/api/jobs/{job_id}/files/{kind}")
def get_job_file(job_id: str, kind: str) -> FileResponse:
    job = get_job(job_id)
    filename = job.get("files", {}).get(kind)
    if not filename:
        raise HTTPException(status_code=404, detail="File kind not found")
    path = JOBS_DIR / job_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, filename=filename)


@app.get("/api/page-subtitle")
def page_subtitle(
    url: str | None = Query(default=None),
    job_id: str | None = Query(default=None),
) -> dict:
    if not job_id:
        bvid = extract_bvid(url)
        index_data = read_index()
        job_id = index_data.get("by_bvid", {}).get(bvid) if bvid else None
    if not job_id:
        return {"found": False, "reason": "当前 B 站页面还没有生成过字幕"}

    job = get_job(job_id)
    json_file = job.get("files", {}).get("json")
    if job.get("status") != "completed" or not json_file:
        return {"found": False, "reason": "字幕任务还没有完成", "job": job}

    subtitle_path = JOBS_DIR / job_id / json_file
    if not subtitle_path.exists():
        return {"found": False, "reason": "字幕文件不存在", "job": job}

    return {
        "found": True,
        "job": job,
        "cues": json.loads(subtitle_path.read_text(encoding="utf-8")),
    }


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    job_dir = JOBS_DIR / job_id

    def progress(status: str, fraction: float, message: str) -> None:
        update_job(
            job_id,
            status=status,
            progress=round(max(0, min(fraction, 1)), 3),
            message=message,
        )

    try:
        metadata = run_pipeline(
            job_id=job_id,
            url=job["url"],
            job_dir=job_dir,
            source_language=job["source_language"],
            whisper_model=job["whisper_model"],
            translator=job["translator"],
            cookies_browser=job["cookies_browser"],
            task_type=job.get("task_type", "subtitle"),
            progress=progress,
        )
        update_job(
            job_id,
            status="completed",
            progress=1.0,
            message="完成",
            title=metadata.get("title"),
            bvid=metadata.get("bvid"),
            detected_language=metadata.get("detected_language"),
            files=metadata.get("files", {}),
        )
        write_index(job_id)
        persist_job(job_id)
    except Exception as exc:
        update_job(job_id, status="failed", progress=1.0, message="失败", error=str(exc))
        persist_job(job_id)


def update_job(job_id: str, **updates: object) -> None:
    with lock:
        job = jobs[job_id]
        job.update(updates)
        job["updated_at"] = utc_now()


def persist_job(job_id: str) -> None:
    with lock:
        job = jobs[job_id]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_job_from_disk(job_id: str) -> dict | None:
    path = JOBS_DIR / job_id / "job.json"
    if not path.exists():
        return None
    job = json.loads(path.read_text(encoding="utf-8"))
    with lock:
        jobs[job_id] = job
    return job


def load_jobs_from_disk() -> None:
    if not JOBS_DIR.exists():
        return
    for path in JOBS_DIR.glob("*/job.json"):
        job_id = path.parent.name
        with lock:
            already_loaded = job_id in jobs
        if not already_loaded:
            load_job_from_disk(job_id)


def read_index() -> dict:
    if not INDEX_PATH.exists():
        return {"by_bvid": {}, "jobs": {}}
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def write_index(job_id: str) -> None:
    job = get_job(job_id)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index_data = read_index()
    index_data.setdefault("jobs", {})[job_id] = {
        "title": job.get("title"),
        "bvid": job.get("bvid"),
        "updated_at": job.get("updated_at"),
    }
    if job.get("bvid"):
        index_data.setdefault("by_bvid", {})[job["bvid"]] = job_id
    INDEX_PATH.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
