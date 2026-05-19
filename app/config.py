"""
Configuration file for the audio pipeline application.
All settings are defined here. Change values here instead of hardcoding them.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# PATHS
# ============================================================================

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directories
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE_DIR = BASE_DIR / "database"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
SAMPLE_MEETINGS_DIR = DATA_DIR / "sample_meetings"

# Create directories if they don't exist
UPLOAD_DIR.mkdir(exist_ok=True)
DATABASE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
SAMPLE_MEETINGS_DIR.mkdir(exist_ok=True)

# Database file
DATABASE_FILE = DATABASE_DIR / "jobs.db"

# ============================================================================
# CELERY & REDIS
# ============================================================================

# Redis connection string
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Celery configuration
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Celery settings
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit

# ============================================================================
# WHISPER (SPEECH-TO-TEXT)
# ============================================================================

# Faster-Whisper model size
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")

# ============================================================================
# OLLAMA (LOCAL LLM)
# ============================================================================

# Ollama server connection
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")

# Ollama generation settings
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", 0.3))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", 0.9))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", 40))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", 1024))
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 120))

# ============================================================================
# FASTAPI
# ============================================================================

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
API_RELOAD = os.getenv("API_RELOAD", "False").lower() == "true"
API_WORKERS = int(os.getenv("API_WORKERS", 4))

API_TITLE = "Audio Intelligence Pipeline"
API_DESCRIPTION = """
Asynchronous audio processing pipeline for:
- Converting speech to text (Faster-Whisper)
- Extracting tasks and action items (Local Ollama LLM)
- Validating structured output (Pydantic)
"""
API_VERSION = "1.0.0"

# ============================================================================
# FILE UPLOAD
# ============================================================================

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 100 * 1024 * 1024))
ALLOWED_AUDIO_FORMATS = {
    "audio/mpeg",      # .mp3
    "audio/wav",       # .wav
    "audio/ogg",       # .ogg
    "audio/flac",      # .flac
    "audio/x-m4a",     # .m4a
}
CHUNK_SIZE = 10 * 1024 * 1024

# ============================================================================
# PROCESSING & LOGGING
# ============================================================================

TRANSCRIPT_CHUNK_SIZE = int(os.getenv("TRANSCRIPT_CHUNK_SIZE", 2000))
TRANSCRIPT_CHUNK_OVERLAP = int(os.getenv("TRANSCRIPT_CHUNK_OVERLAP", 200))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = LOGS_DIR / "app.log"

TEST_MODE = os.getenv("TEST_MODE", "False").lower() == "true"
TEST_AUDIO_DURATION = 2

JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", 1800))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 300))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 60))
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", 0.5))

DEBUG = os.getenv("DEBUG", "False").lower() == "true"
PRINT_CONFIG_ON_STARTUP = os.getenv("PRINT_CONFIG_ON_STARTUP", "True").lower() == "true"

def validate_config() -> bool:
    errors = []
    if not UPLOAD_DIR.exists():
        errors.append(f"Upload directory doesn't exist: {UPLOAD_DIR}")
    return len(errors) == 0

def print_config():
    print("\n" + "="*60)
    print("AUDIO PIPELINE CONFIGURATION")
    print("="*60)
    print("\nPATHS:")
    print(f"  Base Dir: {BASE_DIR}")
    print(f"  Uploads: {UPLOAD_DIR}")
    print(f"  Database: {DATABASE_FILE}")
    print("\nCELERY & REDIS:")
    print(f"  Redis URL: {REDIS_URL}")
    print("\nWHISPER (SPEECH-TO-TEXT):")
    print(f"  Model: {WHISPER_MODEL_SIZE}")
    print(f"  Device: {WHISPER_DEVICE}")
    print("\nOLLAMA (LOCAL LLM):")
    print(f"  Host: {OLLAMA_HOST}")
    print(f"  Model: {OLLAMA_MODEL}")
    print(f"  Temperature: {OLLAMA_TEMPERATURE}")
    print("\nFASTAPI:")
    print(f"  Host: {API_HOST}:{API_PORT}")
    print(f"  Workers: {API_WORKERS}")
    print("\nFILE UPLOAD:")
    print(f"  Max Size: {MAX_UPLOAD_SIZE / (1024*1024):.0f} MB")
    print("\n" + "="*60 + "\n")