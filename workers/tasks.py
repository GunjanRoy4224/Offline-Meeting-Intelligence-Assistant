"""
Celery worker tasks.
These are the actual background jobs that workers execute.
Each task represents a unit of work that can be parallelized.
"""

import logging
from pathlib import Path
from datetime import datetime
import json
import sqlite3
import asyncio

from workers.celery_app import celery_app
from workers.processors.whisper_processor import transcribe_audio
from workers.processors.ollama_processor import extract_tasks_mapreduce
from workers.processors.validation import validate_and_parse_tasks
from app.config import DATABASE_FILE

logger = logging.getLogger(__name__)

def update_job_status(job_id: str, status: str, **kwargs):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        fields = ["status = ?"]
        values = [status]
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        values.append(job_id)
        query = f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?"
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        logger.info(f"[{job_id}] Status updated: {status}")
    except Exception as e:
        logger.error(f"[{job_id}] Error updating job: {e}")

@celery_app.task(
    bind=True,
    name='workers.tasks.process_audio_task',
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=60,
)
def process_audio_task(self, file_path: str, job_id: str):
    logger.info(f"[{job_id}] Starting audio processing")
    logger.info(f"[{job_id}] File: {file_path}")
    
    try:
        logger.info(f"[{job_id}] Step 1/3: Transcribing audio...")
        update_job_status(job_id, "processing", progress="transcribing")
        self.update_state(state='PROGRESS', meta={'current': 'transcribing', 'status': 'Converting speech to text...'})
        
        transcript = transcribe_audio(file_path)
        logger.info(f"[{job_id}] Transcription complete: {len(transcript)} characters")
        if not transcript or len(transcript.strip()) == 0:
            raise ValueError("Transcription produced empty result")
            
        logger.info(f"[{job_id}] Step 2/3: Extracting tasks with LLM...")
        update_job_status(job_id, "processing", progress="extracting")
        self.update_state(state='PROGRESS', meta={'current': 'extracting', 'status': 'Analyzing transcript with LLM...'})
        
        # Safe asyncio runner — works with solo, prefork, and gevent Celery pools.
        # asyncio.run() raises RuntimeError when a loop is already running (gevent/prefork).
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # A loop is already active (e.g. gevent/eventlet pool) — run in a fresh thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, extract_tasks_mapreduce(transcript, job_id))
                raw_tasks = future.result()
        else:
            raw_tasks = loop.run_until_complete(extract_tasks_mapreduce(transcript, job_id))
        logger.info(f"[{job_id}] LLM extraction complete: {len(raw_tasks)} tasks found")
        
        logger.info(f"[{job_id}] Step 3/3: Validating results...")
        update_job_status(job_id, "processing", progress="validating")
        self.update_state(state='PROGRESS', meta={'current': 'validating', 'status': 'Validating extracted data...'})
        
        validated_tasks = validate_and_parse_tasks(raw_tasks, job_id)
        logger.info(f"[{job_id}] Validation complete: {len(validated_tasks)} valid tasks")
        
        logger.info(f"[{job_id}] Saving results to database...")
        tasks_json = json.dumps([t.dict() for t in validated_tasks])
        
        update_job_status(
            job_id,
            "completed",
            progress=None,
            transcript=transcript,
            tasks=tasks_json,
            completed_at=datetime.utcnow().isoformat()
        )
        
        logger.info(f"[{job_id}] Cleaning up temporary files...")
        try:
            Path(file_path).unlink(missing_ok=True)
            logger.info(f"[{job_id}] Temporary file deleted")
        except Exception as e:
            logger.warning(f"[{job_id}] Could not delete temp file: {e}")
            
        logger.info(f"[{job_id}] ✓ Processing complete!")
        return {
            "job_id": job_id,
            "status": "completed",
            "transcript_length": len(transcript),
            "tasks_extracted": len(validated_tasks),
            "tasks": [t.dict() for t in validated_tasks]
        }
        
    except FileNotFoundError as e:
        error_msg = f"Audio file not found: {file_path}"
        logger.error(f"[{job_id}] {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise
    except ValueError as e:
        error_msg = f"Invalid audio or processing error: {str(e)}"
        logger.error(f"[{job_id}] {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[{job_id}] {error_msg}", exc_info=True)
        update_job_status(job_id, "failed", error=error_msg)
        raise self.retry(exc=e, countdown=60)

@celery_app.task(name='workers.tasks.cleanup_old_uploads')
def cleanup_old_uploads(days: int = 7):
    from app.config import UPLOAD_DIR
    import time
    
    logger.info(f"Cleaning up uploads older than {days} days")
    current_time = time.time()
    cutoff_time = current_time - (days * 24 * 60 * 60)
    deleted_count = 0
    
    for file_path in UPLOAD_DIR.glob("*"):
        if file_path.is_file():
            file_mtime = file_path.stat().st_mtime
            if file_mtime < cutoff_time:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted: {file_path}")
                except Exception as e:
                    logger.warning(f"Could not delete {file_path}: {e}")
                    
    logger.info(f"Cleanup complete: deleted {deleted_count} files")
    return {"deleted_count": deleted_count}