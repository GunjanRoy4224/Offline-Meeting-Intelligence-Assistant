# 🎙️ [Offline Meeting Intelligence Assistant]

A **production-grade**, fully asynchronous audio intelligence system that transcribes speech to text and automatically extracts structured action items using a local LLM — all with a sub-50ms API response time.

> Upload a file **or** record live from your browser → get back a full transcript + structured task list, without blocking your application.

---

## 🆕 What's New (Latest Improvements)

### 1. 🖥️ Web UI Dashboard (`app/static/index.html`)
A full glassmorphism-styled dashboard served directly at `http://localhost:8000/`. No separate frontend server needed.

- **Dual input modes** side-by-side — Upload a file *or* record live from the browser
- **Live pipeline progress bar** — shows real-time stage (`transcribing → extracting → validating`) via polling
- **Active Jobs table** — auto-refreshing list of all pipeline jobs with status badges
- **Job Details modal** — click any row to view the full transcript + all extracted action items with confidence scores

### 2. 🎤 Browser-Based Live Recording
Record directly from your microphone in the browser. Audio is captured via the [MediaRecorder API](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder), assembled into a WAV blob, and automatically submitted to `POST /upload` when you click **Stop Meeting**. No separate software required.

### 3. ⚡ Asynchronous Ollama Processing (`workers/processors/ollama_processor.py`)
The LLM task extraction pipeline was upgraded from sequential `requests` calls to fully **async/concurrent** processing using `httpx.AsyncClient`:

| Before | After |
|--------|-------|
| Chunks processed one-by-one | All chunks fired concurrently with `asyncio.gather()` |
| Per-chunk Ollama health checks | Single health check before fan-out |
| Synchronous `requests.post()` | Async `httpx.AsyncClient` |
| Sequential, slow for long audio | Parallel — scales with chunk count |

The Celery worker bridges sync→async correctly for all pool types (`solo`, `prefork`, `gevent`) using a safe asyncio runner.

### 4. 🎙️ CLI Meeting Recorder (`data/recorder.py`)
A standalone Python script to record live meetings from the terminal. Uses **time-slice chunking** — automatically splits long recordings into chunks (default: 15-minute slices) and uploads each chunk to the pipeline as it's recorded (fire-and-forget threading). No need to wait until the meeting ends.

```bash
python data/recorder.py
# Press Ctrl+C to stop
```

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  INPUT METHODS                          │
│                                                         │
│  Browser UI (/)          CLI Recorder                   │
│  ┌─────────────────┐    ┌─────────────────┐            │
│  │  📁 File Upload  │    │ 🎤 PyAudio      │            │
│  │  (drag & drop)  │    │  Time-Slicing   │            │
│  └────────┬────────┘    └────────┬────────┘            │
│           │  🎙️ Browser MediaRecorder                   │
│           │  (record live in-browser)                   │
└───────────┼─────────────────────────────────────────────┘
            │
            ▼  POST /upload
  ┌──────────────────────┐
  │   FastAPI + Uvicorn   │  ←── Static UI served at /
  │   (app/main.py)       │  ←── /jobs, /status/{id}
  └──────────┬───────────┘
             │ enqueue (< 50ms return)
             ▼
  ┌──────────────────────┐
  │    Redis Queue        │
  └──────────┬───────────┘
             │ consume
             ▼
  ┌──────────────────────────────────────────────┐
  │           Celery Worker                      │
  │                                              │
  │  Step 1: Faster-Whisper → Full Transcript    │
  │  Step 2: Async Ollama (qwen2.5)              │
  │    ├── chunk 1 ──┐                           │
  │    ├── chunk 2 ──┼── asyncio.gather() ──▶    │
  │    └── chunk N ──┘   (concurrent)            │
  │  Step 3: Pydantic Validation                 │
  └──────────────────┬───────────────────────────┘
                     │ write results
                     ▼
  ┌──────────────────────┐
  │   SQLite Database     │
  └──────────────────────┘
             ▲
             │ poll
  GET /status/{job_id}  ←── Browser UI polls every 3s
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API** | FastAPI + Uvicorn | Async HTTP server |
| **Web UI** | Vanilla HTML/CSS/JS (Tailwind CDN) | Glassmorphism dashboard at `/` |
| **Job Queue** | Celery + Redis | Distributed task queue |
| **Speech-to-Text** | Faster-Whisper | Audio transcription (CPU/GPU) |
| **Local LLM** | Ollama + qwen2.5 | Async task extraction |
| **LLM HTTP Client** | httpx (async) | Concurrent Ollama API calls |
| **Validation** | Pydantic v2 | Structured output validation |
| **Database** | SQLite | Job state persistence |
| **Audio (CLI)** | PyAudio + wave | Terminal meeting recorder |
| **Audio (browser)** | MediaRecorder API | In-browser live recording |

---

## ✨ Features

- ⚡ **Sub-50ms API response** — uploads are queued instantly
- 🖥️ **Built-in Web Dashboard** — no separate frontend server needed
- 🎤 **Dual recording modes** — upload a file *or* record live from the browser
- 🎙️ **CLI Meeting Recorder** — terminal recorder with time-slice chunking
- 🔀 **Concurrent LLM extraction** — all transcript chunks processed in parallel with `asyncio.gather()`
- 🔄 **Automatic retries** — Celery retries failed tasks up to 3 times
- 📏 **Long transcript support** — map-reduce chunking for transcripts exceeding LLM context limits
- 🔒 **Fully local** — no cloud APIs, no data leaves your machine
- 📊 **Confidence scoring** — every extracted task has a confidence score
- ✅ **Type-safe validation** — Pydantic v2 schemas on every request/response

---

## 📁 Project Structure

```
 Offline Meeting Intelligence Assistant/
├── app/
│   ├── config.py                   # Centralized settings (env-driven)
│   ├── models.py                   # Pydantic request/response schemas
│   ├── main.py                     # FastAPI app & all HTTP endpoints
│   └── static/
│       └── index.html              # ✨ Web UI dashboard (served at /)
├── workers/
│   ├── celery_app.py               # Celery configuration & broker setup
│   ├── tasks.py                    # Main Celery task (sync→async bridge)
│   └── processors/
│       ├── whisper_processor.py    # Faster-Whisper speech-to-text
│       ├── ollama_processor.py     # ✨ Async Ollama LLM task extraction
│       └── validation.py           # Pydantic output validation
├── data/
│   ├── downloader.py               # Download real AMI corpus meetings
│   ├── processor.py                # Batch process audio/transcripts
│   ├── recorder.py                 # ✨ CLI time-slice meeting recorder
│   └── sample_meetings/            # Local meeting audio files
├── database/                       # SQLite database (auto-created)
├── uploads/                        # Temporary audio upload storage
├── logs/                           # Application logs
├── docker-compose.yml              # Redis service
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
└── .gitignore
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.9+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Redis)
- [Ollama](https://ollama.com/) installed and running

---

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/GunjanRoy4224/Offline-Meeting-Intelligence-Assistant.git
cd  Offline Meeting Intelligence Assistant

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env to customize settings if needed
```

Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL_SIZE` | `base` | Whisper model (`tiny`, `base`, `small`, `medium`, `large`) |
| `WHISPER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `OLLAMA_MODEL` | `qwen2.5:latest` | Ollama model name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT` | `120` | Per-chunk LLM timeout (seconds) |
| `REDIS_HOST` | `localhost` | Redis host |
| `MAX_UPLOAD_SIZE` | `104857600` | Max audio file size (bytes, default 100 MB) |

---

### 4. Start All Services

You need **4 terminal windows** running simultaneously:

**Terminal 1 — Redis (via Docker)**
```bash
docker-compose up
```

**Terminal 2 — Ollama LLM Server**
```bash
ollama serve
```
Then pull the model once:
```bash
ollama pull qwen2.5:latest
```

**Terminal 3 — FastAPI Server**
```bash
# Windows
venv\Scripts\activate
python -m uvicorn app.main:app --reload
```

**Terminal 4 — Celery Worker**
```bash
# Windows
venv\Scripts\activate
celery -A workers.celery_app worker --loglevel=info
```

---

## 🌐 Using the Web UI

Open **http://localhost:8000/** in your browser.

```
┌──────────────────────┬──────────────────────┐
│   📁 Upload Audio    │   🎤 Live Recording   │
│                      │                      │
│  Drag & drop or      │  Click "Start         │
│  click to browse.    │  Meeting" to record   │
│  Supports MP3, WAV,  │  from your mic.       │
│  OGG, FLAC, M4A.     │  Click "Stop Meeting" │
│                      │  to upload & process. │
└──────────────────────┴──────────────────────┘
│            Active Pipeline Jobs              │
│  ┌──────────────────────────────────────┐   │
│  │ filename │ time │ status │ progress  │   │
│  │ ...      │ ...  │  ✅    │ ████ 100% │   │
│  └──────────────────────────────────────┘   │
│         (click any row for details)          │
└──────────────────────────────────────────────┘
```

Click any job row to open a **detail modal** showing:
- Full meeting transcript (scrollable)
- All extracted action items with assignee, deadline, and confidence score

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/` | Web UI Dashboard |
| `GET` | `/health` | Health check |
| `POST` | `/upload` | Upload an audio file |
| `GET` | `/status/{job_id}` | Poll processing status |
| `GET` | `/jobs?limit=10` | List recent jobs |
| `GET` | `/docs` | Swagger interactive API docs |

### Upload Audio (cURL)

```bash
curl -X POST \
  -F "file=@meeting.mp3" \
  http://localhost:8000/upload
```

**Response (202 Accepted):**
```json
{
  "job_id": "3f2a1b4c-...",
  "status": "queued",
  "filename": "meeting.mp3",
  "message": "File queued for processing"
}
```

### Poll Job Status

```bash
curl http://localhost:8000/status/3f2a1b4c-...
```

**Response (completed):**
```json
{
  "job_id": "3f2a1b4c-...",
  "status": "completed",
  "filename": "meeting.mp3",
  "progress": "completed",
  "transcript": "John: We need to review the Q3 report by Friday...",
  "tasks": [
    {
      "assignee": "John",
      "task": "Review the Q3 report",
      "deadline": "2024-01-15",
      "confidence": 0.92
    },
    {
      "assignee": "Sarah",
      "task": "Send updated budget to the team",
      "deadline": null,
      "confidence": 0.87
    }
  ],
  "created_at": "2024-01-10T09:00:00",
  "completed_at": "2024-01-10T09:07:34"
}
```

**Possible `status` values:** `queued` → `processing` → `completed` / `failed`  
**Possible `progress` values:** `queued` → `transcribing` → `extracting` → `validating` → `completed`

---

## 🎙️ CLI Meeting Recorder

A standalone terminal recorder that:
- Records audio from your microphone using PyAudio
- Automatically **splits into time-slice chunks** (default: 15 min) during the meeting
- Uploads each chunk to the pipeline in a background thread as recording continues
- You don't need to wait until the meeting ends to start processing

```bash
python data/recorder.py
# Press Ctrl+C to stop and flush the final chunk
```

Recorded chunks are saved under `data/local_records/` and each is submitted as a separate pipeline job.

---

## 🗂️ Sample / Test Data

```bash
# Generate synthetic test data (fast, no download)
python data/downloader.py synthetic

# Download 1 real AMI meeting (large download)
python data/downloader.py 1

# Batch process a folder of audio files
python data/processor.py --batch data/sample_meetings/
```

---

## 📊 Performance Benchmarks

| Metric | Value |
|--------|-------|
| API response time (upload) | < 50ms |
| Transcription (1-hour audio, CPU) | ~5 minutes |
| Task extraction — sequential (old) | ~2 min/chunk × N chunks |
| Task extraction — async concurrent (new) | ~2 min total (all chunks parallel) |
| End-to-end (1-hour meeting) | ~7–10 minutes |
| Max concurrent users | 100+ (add more Celery workers) |
| Validation rejection rate | ~5–10% (bad LLM output caught) |
| Confidence score range | 0.5 – 0.95 |

---

## 🏗️ Design Decisions

| Decision | Rationale |
|----------|-----------|
| **asyncio.gather() for LLM chunks** | Process all N transcript chunks simultaneously instead of one-by-one — dramatically faster for long meetings |
| **Single Ollama health check** | Moved from per-chunk to once before fan-out — avoids N redundant HTTP round-trips |
| **httpx AsyncClient** over requests | Native async HTTP client, plays well with `asyncio.gather()` |
| **Safe asyncio bridge in Celery** | Celery workers may have an event loop already (gevent/prefork) — the bridge handles all pool types safely |
| **MediaRecorder API** for browser recording | Native browser API, no plugin or server-side streaming needed |
| **PyAudio time-slicing** for CLI recorder | Lets you upload and process meeting chunks while the meeting is still ongoing |
| **Celery + Redis** over AWS SQS | Free, local, horizontally scalable |
| **Faster-Whisper** over cloud APIs | Free, accurate, runs offline |
| **Ollama locally** over OpenAI | No API costs, full data privacy |
| **SQLite** over PostgreSQL | No extra server needed at this scale |

---

## 🔧 Troubleshooting

### Redis not running
```bash
docker ps                     # Check if container is running
docker-compose up -d          # Start Redis
docker-compose logs redis     # View Redis logs
redis-cli ping                # Should return PONG
```

### Ollama connection refused
```bash
ollama serve                          # Start server (keep terminal open)
ollama list                           # Check available models
ollama pull qwen2.5:latest            # Pull model if missing
```

### Celery not picking up tasks
```bash
celery -A workers.celery_app worker --loglevel=info
redis-cli ping   # Should return PONG
```

### API not responding
```bash
python -m uvicorn app.main:app --reload
# Check http://localhost:8000/health
```

### High memory / slow model loading
```bash
# Use a smaller Whisper model
WHISPER_MODEL_SIZE=tiny python -m uvicorn app.main:app --reload

# Enable GPU
WHISPER_DEVICE=cuda python -m uvicorn app.main:app --reload
```

> **Note:** Faster-Whisper loads once at worker startup (~30s). Ollama loads on first inference (~10s). This is expected.

### Microphone access denied in browser
Ensure the browser has microphone permissions. The site must be accessed over `http://localhost` (or HTTPS) — microphone access is blocked on plain HTTP from non-localhost origins.

---

## 📦 Supported Audio Formats

| Extension | MIME Type |
|-----------|----------|
| `.mp3` | `audio/mpeg` |
| `.wav` | `audio/wav` |
| `.ogg` | `audio/ogg` |
| `.flac` | `audio/flac` |
| `.m4a` | `audio/x-m4a` |

Maximum file size: **100 MB** (configurable via `MAX_UPLOAD_SIZE`)

---

## 📄 License

MIT License — free to use, modify, and distribute.
