<<<<<<< HEAD
# InterviewInsight-AI
=======
# InterviewInsight AI

InterviewInsight AI is a full-stack interview practice platform that records a mock interview, runs multimodal analysis (video + audio + transcript), and returns actionable coaching with dashboards, segment-level feedback, reflective learning, and report export.

## Table of Contents

1. [What Problem This Solves](#what-problem-this-solves)
2. [Core Features](#core-features)
3. [Architecture](#architecture)
4. [Tech Stack](#tech-stack)
5. [Repository Layout](#repository-layout)
6. [Local Deployment (From GitHub)](#local-deployment-from-github)
7. [Environment Variables](#environment-variables)
8. [Product Flow](#product-flow)
9. [Analysis Pipeline and Models](#analysis-pipeline-and-models)
10. [API Quick Reference](#api-quick-reference)
11. [Testing and Dry Runs](#testing-and-dry-runs)
12. [Troubleshooting](#troubleshooting)
13. [Production Notes](#production-notes)
14. [Contributing](#contributing)

## What Problem This Solves

Interview prep tools usually give only generic feedback. This project solves that by combining:

- visual behavior signals (eye contact, gaze, head stability, facial emotion),
- audio behavior signals (pace, pauses, pitch, prosody, speech emotion),
- content signals (sentiment, semantic relevance, coherence),
- score explainability and coaching output.

Result: each interview session gives measurable performance scores plus specific segment-level improvements.

## Core Features

- Authenticated product UI (`/auth`, `/app`, `/interview/live`, `/dashboard/:sessionId`)
- Live interview flow with AI-generated follow-up and clarification questions
- Session recording upload at interview end and async analysis through Celery
- Dashboard with score cards, timeline charts, segment cards, recommendations, and replay controls
- Reflection workflow with coaching response and aggregated reflective summaries
- Progress dashboard with historical trends per user
- PDF report generation with optional captured chart snapshots
- Avatar interviewer modes:
  - browser TTS fallback
  - provider mode (Simli)
  - virtual3d mode (OpenAI TTS + viseme timeline)

## Architecture

```mermaid
flowchart LR
  A[React + Vite Frontend] --> B[FastAPI Backend]
  B --> C[(PostgreSQL)]
  B --> D[(Redis)]
  B --> E[Celery Worker]
  E --> F[Video Processor]
  E --> G[Audio Processor]
  E --> H[Transcript Processor]
  F --> I[Multimodal Fusion + Scoring]
  G --> I
  H --> I
  I --> C
  A --> J[Dashboard + Reports + Reflection + Progress]
  J --> B
```

```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend
  participant BE as FastAPI
  participant Q as Celery/Redis
  participant W as Worker

  U->>FE: End live interview
  FE->>BE: POST /app/live/{sessionId}/end (video/audio)
  BE->>Q: enqueue analysis task
  FE->>BE: poll /analysis/{sessionId}/job
  Q->>W: run_video_analysis
  W->>BE: persist analysis + scores
  FE->>BE: GET /app/me/sessions/{sessionId}/analysis
  BE->>FE: full result payload
```

## Tech Stack

- Frontend: React 18, Vite, React Router, Recharts, jsPDF, html2canvas
- Backend API: FastAPI, Uvicorn
- Queue and async: Celery + Redis
- Persistence: PostgreSQL + SQLAlchemy ORM
- Analysis: OpenCV, MediaPipe, Whisper, Transformers, Sentence Transformers, librosa, torch
- Optional real-time avatar: LiveKit + Simli plugins

## Repository Layout

```text
InterviewInsightAI/
├── backend/
│   ├── app/
│   │   ├── api/               # FastAPI route modules
│   │   ├── analysis/          # video/audio/transcript/fusion pipeline
│   │   ├── scoring/           # core + advanced scoring + fairness + LLM judge
│   │   ├── services/          # auth, queue, reports, avatar integrations, session store
│   │   ├── tasks/             # Celery tasks
│   │   ├── models/            # Pydantic request/response models
│   │   ├── db.py              # SQLAlchemy engine/session
│   │   ├── db_models.py       # SQLAlchemy table models
│   │   └── main.py            # FastAPI app entry
│   ├── tests/                 # backend tests + local pipeline runner
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/             # Auth, Workspace, LiveInterview, Dashboard, Progress, Reflective
│   │   ├── components/        # charts/cards/report UI pieces
│   │   ├── context/           # auth context + token refresh
│   │   └── utils/
│   ├── package.json
│   └── .env.example
└── README.md
```

## Local Deployment (From GitHub)

### 1. Prerequisites

- Python 3.11+ (3.12 tested)
- Node.js 18+ and npm
- PostgreSQL 14+
- Redis 6+
- `ffmpeg` on PATH (required for extracting audio from video files)

Install `ffmpeg` on Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

### 2. Clone

```bash
git clone <your-repo-url>
cd InterviewInsightAI
```

### 3. Create `.env` files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Edit both files before first run.

### 4. Start infrastructure (Postgres + Redis)

Option A: Docker

```bash
docker run --name iia-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=interviewinsightai \
  -p 5432:5432 -d postgres:16

docker run --name iia-redis -p 6379:6379 -d redis:7
```

Option B: local services (system packages) is also fine.

### 5. Start backend API

```bash
cd backend
python3 -m venv interviewinsight_env
source interviewinsight_env/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Start Celery worker

In a second terminal:

```bash
cd backend
source interviewinsight_env/bin/activate
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
```

Notes:

- `--pool=solo` is recommended in many local/WSL setups.
- Without a running worker, analysis jobs remain queued and dashboard polling will keep returning pending/404.

### 7. Start frontend

In a third terminal:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### 8. Optional: Simli real-time worker

Only needed for Simli LiveKit mode:

```bash
cd backend
source interviewinsight_env/bin/activate
python simli_worker.py dev
```

### 9. Smoke checks

- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`
- Frontend auth page: `http://localhost:5173/auth`
- Main app: `http://localhost:5173/app`

## Environment Variables

### Backend (`backend/.env`)

#### Required for local baseline

| Key | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+psycopg://postgres:postgres@localhost:5432/interviewinsightai` | SQLAlchemy DB connection |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Queue/cache backend |
| `JWT_SECRET_KEY` | Yes | `change-me-in-production` | JWT signing secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Refresh token TTL |
| `CELERY_BROKER_URL` | No | falls back to `REDIS_URL` | Celery broker |
| `CELERY_RESULT_BACKEND` | No | falls back to `REDIS_URL` | Celery result backend |

#### Analysis/runtime tuning

| Key | Required | Default | Purpose |
|---|---|---|---|
| `IIA_FAST_ANALYSIS` | No | `1` | Fast mode (lower sampling, no remote LLM judge call) |
| `IIA_WHISPER_MODEL` | No | `tiny` | Whisper model size (`tiny`, `base`, `small`, etc.) |
| `IIA_DISABLE_MODEL_LOADING` | No | `0` | Disable heavy pretrained model loading and use fallbacks |
| `OPENAI_API_KEY` | Optional | empty | Enables remote LLM judge + virtual3d TTS + richer interviewer prompts |

#### Avatar config

| Key | Required | Default | Purpose |
|---|---|---|---|
| `IIA_AVATAR_MODE` | No | code default `browser` (template sets `virtual3d`) | `browser`, `provider`, or `virtual3d` |
| `IIA_AVATAR_PROVIDER` | Provider mode | `simli` (recommended) | `simli` |
| `IIA_AVATAR_API_KEY` | Simli provider mode | empty | Simli API key |
| `IIA_AVATAR_BASE_URL` | Simli provider mode | `https://api.simli.ai` | Simli API base URL |
| `IIA_SIMLI_FACE_ID` | Simli provider mode | empty | Simli face ID |
| `IIA_SIMLI_MAX_SESSION_LENGTH` | No | `3600` | Max Simli session seconds |
| `IIA_SIMLI_MAX_IDLE_TIME` | No | `300` | Max Simli idle seconds |
| `IIA_VIRTUAL_AVATAR_TTS_MODEL` | virtual3d mode | `gpt-4o-mini-tts` | OpenAI TTS model |
| `IIA_VIRTUAL_AVATAR_VOICE` | virtual3d mode | `alloy` | OpenAI voice |
| `IIA_BACKEND_BASE_URL` | No | `http://localhost:8000` | Used to build local asset/audio URLs |

#### Simli + LiveKit worker

| Key | Required | Default | Purpose |
|---|---|---|---|
| `LIVEKIT_URL` | Simli LiveKit mode | empty | LiveKit websocket URL |
| `LIVEKIT_API_KEY` | Simli LiveKit mode | empty | LiveKit key |
| `LIVEKIT_API_SECRET` | Simli LiveKit mode | empty | LiveKit secret |
| `SIMLI_API_KEY` | Simli LiveKit mode | empty | Simli API key |
| `SIMLI_FACE_ID` | Simli LiveKit mode | empty | Simli face ID |
| `SIMLI_START_MAX_RETRIES` | No | `5` | Session start retries |
| `SIMLI_START_RETRY_BASE_SECONDS` | No | `3` | Retry backoff start |
| `SIMLI_START_RETRY_MAX_SECONDS` | No | `60` | Retry backoff max |

### Frontend (`frontend/.env`)

| Key | Required | Default | Purpose |
|---|---|---|---|
| `VITE_API_BASE_URL` | Yes | `http://localhost:8000` | Backend API base URL |
| `VITE_ENABLE_PROVIDER_AVATAR` | No | `1` | Enables provider avatar calls in live interview UI |
| `VITE_SIMLI_PLAY_REMOTE_AUDIO` | No | `1` | Play remote room audio when using Simli |
| `VITE_BARGE_IN_SAMPLE_MS` | No | `120` | Barge-in detector sample window |
| `VITE_BARGE_IN_RMS_THRESHOLD` | No | `0.05` | Voice activity threshold |
| `VITE_BARGE_IN_CONSECUTIVE_FRAMES` | No | `7` | Consecutive frame count for barge-in trigger |
| `VITE_BARGE_IN_DYNAMIC_MULTIPLIER` | No | `2.25` | Dynamic threshold multiplier |
| `VITE_ENABLE_BARGE_IN` | No | `0` when unset | Enables barge-in behavior |

## Product Flow

1. Open `http://localhost:5173/auth` and register/login.
2. Go to `http://localhost:5173/app` and create a session (job role + domain).
3. Start interview at `/interview/live`.
4. Answer prompts (speech + text capture, avatar speaking supported).
5. Click end interview; media uploads and analysis job is queued.
6. View outputs:
   - `/dashboard/:sessionId`
   - `/reflective/:sessionId`
   - `/progress/:userId`

## Analysis Pipeline and Models

### End-to-end pipeline

1. Video/audio uploaded at live interview end.
2. Celery runs `analysis.run_video_analysis`.
3. Video processor extracts sampled frame features.
4. Audio processor transcribes and extracts prosodic features.
5. Transcript processor computes relevance/sentiment/coherence.
6. Multimodal fusion builds segment windows and timeline arrays.
7. Scoring modules compute summary + detailed + advanced scores.
8. Fairness checks and LLM/heuristic rationale are added.
9. Dashboard/report APIs return persisted analysis data.

### Pretrained models used

| Component | Model | Purpose | Fallback |
|---|---|---|---|
| Video facial emotion | `trpakov/vit-face-expression` | Per-frame facial emotion distribution | deterministic heuristic emotion scoring |
| Speech-to-text | OpenAI Whisper (`IIA_WHISPER_MODEL`, default `tiny`) | Transcript and timestamped segments | fallback transcript text |
| Speech emotion | `superb/hubert-large-superb-er` | Audio emotion label probabilities | default calm/happy/sad/angry/neutral mix |
| Transcript sentiment | `distilbert-base-uncased-finetuned-sst-2-english` | Segment sentiment scoring | lexical token sentiment heuristic |
| Transcript embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Semantic relevance and coherence vectors | deterministic hashed bag-of-words projection |
| Optional LLM judge | OpenAI chat model (`gpt-4o-mini`) | depth/correctness/relevance rationale | heuristic judge |

### Important runtime notes

- First run may download model files from Hugging Face and take longer.
- In `IIA_FAST_ANALYSIS=1`, sampling is reduced and remote LLM judging is skipped.
- Some Hugging Face `processor_config.json 404` HEAD logs are normal for repos that use `preprocessor_config.json`.

## API Quick Reference

### Health and docs

- `GET /health`
- `GET /api/health`
- `GET /docs`

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`

### Product/session scope

- `GET /app/me/sessions`
- `POST /app/me/sessions/start`
- `GET /app/me/sessions/{sessionId}/status`
- `GET /app/me/sessions/{sessionId}/analysis`
- `GET /app/me/sessions/{sessionId}/scores/explain`
- `POST /app/me/sessions/{sessionId}/report`
- `GET /app/me/sessions/{sessionId}/video`

### Live interview

- `POST /app/live/start`
- `GET /app/live/{sessionId}/state`
- `POST /app/live/{sessionId}/turn-evaluate`
- `POST /app/live/{sessionId}/answer`
- `POST /app/live/{sessionId}/skip`
- `POST /app/live/{sessionId}/end`

### Analysis

- `POST /analysis/video`
- `GET /analysis/jobs/{jobId}`
- `GET /analysis/{sessionId}/job`
- `GET /analysis/{sessionId}/results`
- `GET /analysis/{sessionId}/scores`

### Reports, reflective learning, progress

- `POST /reports/{sessionId}/generate`
- `POST /reflective/{sessionId}/responses`
- `GET /reflective/{userId}/summaries`
- `GET /users/{userId}/performance-history`

## Testing and Dry Runs

### Backend tests

```bash
cd backend
source interviewinsight_env/bin/activate
pytest -q
```

### Lightweight pipeline dry run

```bash
cd backend
source interviewinsight_env/bin/activate
python tests/run_analysis_pipeline.py --lightweight
```

### Frontend tests and build

```bash
cd frontend
npm test
npm run build
```

## Troubleshooting

### Repeated 404 on dashboard analysis endpoints

If you see repeated requests like:

- `/app/me/sessions/{sessionId}/analysis` -> `404`
- `/analysis/{sessionId}/results` -> `404`

it usually means analysis is not yet available (or worker is not processing).

Checklist:

1. Confirm Redis is up.
2. Confirm Celery worker is running and connected to Redis.
3. Confirm interview was ended via `/app/live/{sessionId}/end`.
4. Check job state with `GET /analysis/{sessionId}/job`.

### Worker receives tasks but results never appear

- Verify `DATABASE_URL` is reachable from both API and worker process.
- Verify media files exist under `backend/app/storage/<sessionId>/` (live flow) or `backend/storage/<sessionId>/` (manual upload flow).
- Watch worker logs for model loading failures.

### `disconnect from room` / avatar interruptions

- If using Simli provider mode, validate Simli keys and room/session setup.
- If using Simli/LiveKit, verify all `LIVEKIT_*` and `SIMLI_*` keys and run `python simli_worker.py dev`.
- Temporarily set `IIA_AVATAR_MODE=browser` to isolate Simli issues.

### Hugging Face warnings / 404 on `processor_config.json`

- Usually non-fatal. Some models do not publish `processor_config.json` and fall back to `preprocessor_config.json`.

### Audio decode warnings (e.g., Opus packet parsing)

- Source media container/codec may be partially malformed.
- Re-encode the source to standard `webm` or `mp4` before upload if needed.

### Port conflicts

```bash
ss -ltnp | grep -E ':(5173|8000|5432|6379)\b'
```

## Production Notes

- Change `JWT_SECRET_KEY` before production.
- Restrict CORS to your production domains.
- Put API behind HTTPS reverse proxy.
- Use managed Postgres/Redis for reliability.
- Persist upload storage paths (`backend/app/storage/` and/or `backend/storage/`) to durable volumes/object storage.
- Pin model versions and prewarm caches to reduce cold-start latency.
- Add proper DB migrations (project currently uses `Base.metadata.create_all`).

## Contributing

1. Create a feature branch.
2. Keep API and UI changes consistent (endpoint + route usage).
3. Run backend/frontend tests before opening PR.
4. Update `.env.example` and this README whenever new config keys are added.
>>>>>>> 5258173 (Initial commit)
