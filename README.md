# VidMind

**Turn long videos into searchable knowledge.** Paste a YouTube link or upload a video, and in about half a minute you get:

- a one-line **TL;DR** and a written **summary**
- **key points** with concrete names and numbers
- **timestamped chapters** that jump the player to that moment
- **Ask the video**: answers grounded in what's said, with timestamped sources
- **Search by meaning** across the transcript, plus the full transcript

VidMind runs two ways:

| Mode | Who it's for | AI | Sign-in | Database |
| --- | --- | --- | --- | --- |
| **Local** | You, on your own machine | Ollama (local) or Claude | None | SQLite |
| **Public** | Anyone on the internet | Claude API | Supabase (email magic link, optional Google) | Postgres |

The mode follows from configuration: setting `SUPABASE_URL` switches on sign-in, per-user libraries and the safety limits.

---

## How it works

```
YouTube link ──► TranscriptAPI.com (captions) ─┐
                 └─ fallback: yt-dlp ──────────┤
Uploaded file ─► FFmpeg ─► faster-whisper ─────┤
                                               ▼
                                 timestamped transcript
                                               │
              ┌────────────────────────────────┼─────────────────────────────┐
              ▼                                ▼                             ▼
  sentence-transformers + FAISS    Claude / Ollama (one call)      saved transcript
   (semantic search index)     TL;DR · summary · key points ·
                                    timestamped chapters
              │
              └──► Ask the video: retrieve relevant chunks ─► Claude answers with sources
```

- **Jobs** run in the background. Locally they run inside the API process (`JOB_MODE=inline`). In production a separate worker claims them from the database (`JOB_MODE=queue`), so they survive restarts and deploys without a separate queue service.
- **Fallbacks keep it working.** If Claude or Ollama is unreachable, small local Hugging Face models write a basic summary. If TranscriptAPI can't serve a video, yt-dlp is tried.

## Tech stack

- **Frontend:** React 18, Vite, Tailwind CSS, Supabase JS
- **Backend:** Python 3.12, FastAPI, SQLAlchemy (SQLite or Postgres), PyJWT
- **AI:** Anthropic Claude API, or Ollama locally; sentence-transformers and FAISS for search; faster-whisper for uploads
- **Services (public mode):** Supabase (auth and Postgres), TranscriptAPI.com, Railway, Vercel

---

## Run it locally

**Requirements:** Python 3.12+, Node 20+, `ffmpeg` on your PATH (`brew install ffmpeg`), and either an [Anthropic API key](https://console.anthropic.com) or [Ollama](https://ollama.com) with `ollama pull qwen3:8b`.

**Backend**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in at least one AI option (see below)
uvicorn app.main:app --reload --reload-dir app --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173. With `SUPABASE_URL` unset there's no sign-in, and you're the single "local" user. API docs are at http://localhost:8000/docs.

**Tests**

```bash
cd backend
pip install pytest
python -m pytest tests -q
```

The suite (75 tests) needs no network or API keys. It covers authentication, forged tokens, users reaching each other's data, malicious input, quotas, rate limits, body-size limits, HTTPS redirects, security headers, CORS, and pipeline failure handling.

---

## Configuration

Everything is set with environment variables (`backend/.env`, `frontend/.env`). The `.env.example` files list them all. The important ones:

### Backend

| Variable | Purpose | Default |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Use Claude for summaries and answers | empty (use Ollama) |
| `ANTHROPIC_MODEL` | `claude-opus-5-5`, `claude-sonnet-5-5` or `claude-haiku-5-5` | `claude-opus-5-5` |
| `ANTHROPIC_EFFORT` | `low` / `medium` / `high` | `low` |
| `LLM_PROVIDER` | `auto`, `anthropic`, `ollama` or `none` | `auto` (Claude if keyed, else Ollama) |
| `TRANSCRIPT_API_KEY` | YouTube transcripts via TranscriptAPI.com | empty (use yt-dlp) |
| `DATABASE_URL` | SQLite or Postgres URL | SQLite file |
| `SUPABASE_URL` | Turns on sign-in and public mode | empty (local mode) |
| `ALLOWED_ORIGINS` | Frontend origins allowed by CORS | `localhost` ports |
| `JOB_MODE` | `inline` or `queue` (the Docker image uses `queue`) | `inline` |
| `ENABLE_UPLOADS` | Allow file uploads (Whisper on CPU) | `true` |

### Limits

These default to unlimited locally. Once `SUPABASE_URL` is set, they default to the public values:

| Variable | Public default | Meaning |
| --- | --- | --- |
| `DAILY_VIDEO_LIMIT` | 5 | Videos per user per 24 h |
| `MAX_ACTIVE_JOBS_PER_USER` | 2 | Videos analyzing at once |
| `MAX_VIDEO_MINUTES` | 180 | Longest video accepted |
| `ASK_LIMIT_PER_HOUR` | 60 | Questions per user per hour |
| `SEARCH_LIMIT_PER_HOUR` | 120 | Searches per user per hour |
| `RATE_LIMIT_PER_MINUTE` | 240 | Requests per IP per minute (all endpoints) |
| `FORCE_HTTPS` | on | Redirect HTTP to HTTPS and send HSTS |
| `ENABLE_DOCS` | off | Serve `/docs` |

### Frontend

| Variable | Purpose |
| --- | --- |
| `VITE_API_URL` | Backend URL (`https://…` in production) |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | Sign-in. Leave both empty for local mode |
| `VITE_ENABLE_GOOGLE_AUTH` | Show "Continue with Google" |

---

## Security

- **HTTPS everywhere in production.** Vercel and Railway provide TLS. The API redirects plain-HTTP requests to HTTPS and sends HSTS, and so does the frontend (`vercel.json`).
- **Authentication.** Supabase access tokens are verified on every request (signature, expiry, audience, issuer). Each video belongs to one user; any other user gets the same 404 as for a video that doesn't exist.
- **Abuse limits.** Per-IP rate limiting on every endpoint, per-user daily quotas, concurrent-job caps, per-hour Ask and search limits, a maximum video length, and a 64 KB cap on JSON bodies.
- **AI guardrails.** Transcripts and questions are treated as untrusted data. The prompts tell the model never to follow instructions inside them, and Ask answers only questions about the video. Tested against jailbreaks, prompt-extraction attempts and off-topic requests.
- **Safe failures.** Users see friendly error messages. Stack traces and internal details only go to the server logs, and sign-in tokens are redacted from access logs.
- **Headers.** Content Security Policy, `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy, and `no-store` caching for API responses.
- **Secrets.** `.env` files and YouTube cookie files are ignored by git. Only the Supabase *publishable* key goes to the browser.

## Deploying

VidMind deploys as a static frontend on Vercel and a Docker backend (API + worker) on Railway, with Supabase for sign-in and Postgres. Set the environment variables above on each service; `backend/railway.toml` and `frontend/vercel.json` hold the platform config.

## API

All routes are under `/api`. In public mode they need `Authorization: Bearer <Supabase access token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check (no auth) |
| `GET` | `/me` | Current user, quota and limits |
| `POST` | `/videos/youtube` | Analyze a YouTube video by URL |
| `POST` | `/videos/upload` | Upload a video file (multipart) |
| `GET` | `/videos` | Your library |
| `GET` | `/videos/{id}` | Video details |
| `GET` | `/videos/{id}/status` | Status and progress (polled) |
| `GET` | `/videos/{id}/summary` | TL;DR, summary, key points, chapters |
| `GET` | `/videos/{id}/transcript` | Timestamped transcript |
| `GET` | `/videos/{id}/file` | Uploaded video stream |
| `POST` | `/videos/{id}/search` | Search by meaning |
| `POST` | `/videos/{id}/ask` | Ask a question, with sources |
| `POST` | `/videos/{id}/retry` | Re-run a failed video |
| `DELETE` | `/videos/{id}` | Delete a video and everything derived from it |

## Project structure

```
vidmind/
├── backend/
│   ├── app/
│   │   ├── api/routes/     videos, account, health
│   │   ├── core/           config, auth (Supabase JWT), limits, security middleware
│   │   ├── database/       engine, sessions, lightweight migrations
│   │   ├── models/         SQLAlchemy models
│   │   ├── schemas/        request/response models
│   │   ├── services/       transcripts, LLM, summaries, Q&A, search, processing
│   │   └── worker.py       background job worker (JOB_MODE=queue)
│   ├── tests/              adversarial API and pipeline tests
│   ├── Dockerfile          production image (API + worker)
│   ├── start.sh            runs API and worker together
│   └── railway.toml
├── frontend/
│   ├── src/
│   │   ├── auth/           Supabase session and account context
│   │   ├── components/     omnibox, player, cards, Ask, search
│   │   ├── pages/          Dashboard, VideoDetails, Login
│   │   └── services/       API client, Supabase client
│   └── vercel.json         SPA routing and security headers
├── extension/              Chrome extension (local mode only)
└── docker-compose.yml
```

## Troubleshooting

- **"YouTube is asking VidMind to confirm it's not a bot"** (without TranscriptAPI): YouTube is blocking your IP. Set `TRANSCRIPT_API_KEY`, or locally export a `cookies.txt` from a browser signed in to YouTube and set `YTDLP_COOKIES_FILE`.
- **The sign-in email link doesn't return to the app:** add your app URL with `/**` to Supabase → Authentication → URL Configuration → Redirect URLs.
- **The database won't connect from Railway or your network:** use Supabase's **Session pooler** connection string, not the direct (IPv6-only) one.
- **Summaries are basic:** neither Claude nor Ollama is reachable, so the small fallback models are being used. Check `ANTHROPIC_API_KEY` or that Ollama is running.

## Native-thread note

`app/core/native_threads.py` pins OpenMP/MKL to one thread before any ML import. ctranslate2, PyTorch and FAISS each run their own thread pools, and letting them initialize concurrently in one process caused intermittent crashes with no traceback. Keep this import first in `main.py` and `worker.py`.
# VidMind
