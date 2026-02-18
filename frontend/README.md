# InterviewInsight AI Frontend Dashboard

## Run Locally

```bash
cd frontend
npm install
npm run dev
```

Open in browser:

- Auth: `http://localhost:5173/auth`
- Workspace: `http://localhost:5173/app`
- Live Interview: `http://localhost:5173/interview/live`
- Dashboard: `http://localhost:5173/dashboard/<sessionId>`
- Progress Dashboard: `http://localhost:5173/progress/<userId>`
- Reflective Learning Panel: `http://localhost:5173/reflective/<sessionId>`

Optional video playback URL:

- `http://localhost:5173/dashboard/<sessionId>?videoUrl=https://.../interview.mp4`

## Backend API Dependencies

The dashboard relies on these backend endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `GET /app/me/sessions`
- `POST /app/me/sessions/start`
- `POST /app/live/start`
- `POST /app/live/{sessionId}/answer`
- `POST /app/live/{sessionId}/end`
- `GET /app/live/avatar/config`
- `POST /app/live/avatar/speak`
- `POST /app/live/avatar/status`
- `GET /app/live/avatar/audio/{requestId}`
- `GET /analysis/{sessionId}/results`
  - returns summary scores, timeline arrays, segment labels, and feedback summary
- `POST /analysis/video` (upstream data generation before dashboard use)
- `POST /reports/{sessionId}/generate`
  - returns structured report payload for PDF generation/download
- `GET /scores/{sessionId}/explain`
  - returns advanced multimodal scores, explanations, LLM rationale, and fairness summary
- `GET /users/{userId}/performance-history`
  - returns timestamped session score history for trend visualization
- `POST /reflective/{sessionId}/responses`
  - stores user reflection and returns LLM-assisted coaching guidance
- `GET /reflective/{userId}/summaries`
  - returns aggregated reflections + feedback highlights

## Product Flow

1. Register/login in `/auth`
2. Create a session in `/app`
3. Start a live interview in `/interview/live`
4. Open session dashboard
5. Add reflective notes and track trends over time

## Live Interview Flow

1. Open `/interview/live`
2. Allow webcam + microphone
3. Answer AI interviewer prompts
4. End interview to upload recording and run analysis automatically

Optional provider avatar mode:

```bash
# frontend/.env
VITE_ENABLE_PROVIDER_AVATAR=1
VITE_API_BASE_URL=http://localhost:8000
```

If provider config is not available on backend, UI falls back to browser TTS automatically.

For Simli real-time human avatar, also run backend worker:

```bash
cd ../backend
source interviewinsight_env/bin/activate
python simli_worker.py dev
```

## Report Export

The dashboard includes a **Download Full Report** button that:

1. captures selected charts as images (`html2canvas`)
2. requests report JSON from the backend (`/reports/{sessionId}/generate`)
3. renders and downloads a PDF (`jsPDF`) named `interview_report_<sessionId>.pdf`

Library versions:

- `jspdf@^2.5.2`
- `html2canvas@^1.4.1`

## Frontend Unit Tests

```bash
cd frontend
npm test
```
