"""
FastAPI main application.
Handles all HTTP endpoints:
- POST /upload - Upload audio file
- GET /status/{job_id} - Check job processing status
- GET /health - Health check
"""

import logging
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import config and models
from app.config import (
    API_TITLE, API_DESCRIPTION, API_VERSION,
    UPLOAD_DIR, MAX_UPLOAD_SIZE, ALLOWED_AUDIO_FORMATS,
    CHUNK_SIZE, DEBUG, PRINT_CONFIG_ON_STARTUP
)
from app.models import (
    UploadResponse, StatusResponse, HealthCheckResponse,
    JobStatus, Task
)

import json
import sqlite3

# ============================================================================
# LOGGING & APP SETUP
# ============================================================================

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse, tags=["ui"])
async def serve_ui():
    index_file = static_dir / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>UI Template not found</h1>"

# ============================================================================
# DATABASE INITIALIZATION & UTILITIES
# ============================================================================

def init_database():
    from app.config import DATABASE_FILE
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            status TEXT NOT NULL,
            task_id TEXT,
            transcript TEXT,
            tasks TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            progress TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def get_job_from_db(job_id: str) -> Optional[dict]:
    from app.config import DATABASE_FILE
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Database error: {e}")
        return None

def save_job_to_db(job_id: str, filename: str, task_id: str, status: str = JobStatus.QUEUED):
    from app.config import DATABASE_FILE
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO jobs (job_id, filename, task_id, status, created_at, progress)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (job_id, filename, task_id, status, datetime.utcnow().isoformat(), "queued"))
        conn.commit()
        conn.close()
        logger.info(f"Job {job_id} saved to database")
    except Exception as e:
        logger.error(f"Error saving job: {e}")

def update_job_in_db(job_id: str, **kwargs):
    from app.config import DATABASE_FILE
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [job_id]
        cursor.execute(f"UPDATE jobs SET {fields} WHERE job_id = ?", values)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating job: {e}")

def validate_audio_file(file: UploadFile) -> bool:
    return file.content_type in ALLOWED_AUDIO_FORMATS

async def save_upload_file(file: UploadFile, job_id: str) -> Path:
    safe_name = re.sub(r'[^\w.\-]', '_', file.filename)  # Sanitize for ffmpeg/ctranslate2 safety
    file_path = UPLOAD_DIR / f"{job_id}_{safe_name}"
    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(CHUNK_SIZE):
                f.write(chunk)
        logger.info(f"File saved: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    from app.config import print_config
    logger.info("🚀 Starting Audio Pipeline API")
    init_database()
    if PRINT_CONFIG_ON_STARTUP:
        print_config()

@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    logger.debug("Health check requested")
    return HealthCheckResponse(status="ok")

@app.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_audio(file: UploadFile = File(...)):
    try:
        if not validate_audio_file(file):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid audio format. Allowed: {', '.join(ALLOWED_AUDIO_FORMATS)}"
            )
        
        contents = await file.read()
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_UPLOAD_SIZE / (1024*1024):.0f} MB"
            )
        await file.seek(0)
        
        job_id = str(uuid.uuid4())
        logger.info(f"[{job_id}] New upload: {file.filename}")
        
        file_path = await save_upload_file(file, job_id)
        
        try:
            from workers.tasks import process_audio_task
            task_result = process_audio_task.delay(str(file_path), job_id)
            task_id = task_result.id
            logger.info(f"[{job_id}] Task queued: {task_id}")
        except Exception as e:
            logger.warning(f"[{job_id}] Could not queue with Celery: {e}")
            task_id = None
        
        save_job_to_db(job_id, file.filename, task_id or "local", JobStatus.QUEUED)
        
        return UploadResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            filename=file.filename,
            message="File queued for processing"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    try:
        job = get_job_from_db(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(status_code=404, detail="Job not found")
        
        logger.debug(f"Status check for job {job_id}: {job['status']}")
        
        tasks = None
        if job.get('tasks'):
            try:
                task_dicts = json.loads(job['tasks'])
                tasks = [Task(**t) for t in task_dicts]
            except Exception as e:
                logger.error(f"Error parsing tasks: {e}")
        
        return StatusResponse(
            job_id=job_id,
            status=JobStatus(job['status']),
            filename=job['filename'],
            progress=job.get('progress'),
            transcript=job.get('transcript'),
            tasks=tasks,
            error=job.get('error'),
            created_at=datetime.fromisoformat(job['created_at']),
            completed_at=datetime.fromisoformat(job['completed_at']) if job.get('completed_at') else None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/jobs", tags=["debugging"])
async def list_jobs(limit: int = 10):
    from app.config import DATABASE_FILE
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT job_id, filename, status, created_at FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        return []

# ============================================================================
# ERROR HANDLERS & ENTRY POINT
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

if __name__ == "__main__":
    import uvicorn
    from app.config import API_HOST, API_PORT, API_RELOAD
    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT, reload=API_RELOAD, log_level="info")