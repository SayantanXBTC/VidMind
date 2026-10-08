# VidMind

**Free video summaries. No sign-up.** Paste a YouTube link or upload a video file (MP4, MOV, WEBM…), and you get:

- a one-line **TL;DR** and a written **summary**
- **key points** with concrete names and numbers
- **timestamped chapters** that jump the embedded player to that moment
- **Ask the video**: answers drawn from what's actually said, with moments you can jump to
- the full **transcript**, searchable
- **PDF export** of the whole brief

There are no accounts and no database. Your library lives in your browser, split into **YouTube videos** and **Your uploads**, and every brief has a link you can share.

---

## How it works

```
YouTube link ─► TranscriptAPI.com (captions; yt-dlp fallback) ─┐
Video file   ─► FFmpeg (audio) ─► faster-whisper (speech-to-text, on the server) ─┤
                       ┌──────────────────────────────────────────────────────────┘
                       ▼
           Claude: TL;DR · summary · key points · timestamped chapters
                       │
                       ▼
     result cache, keyed by YouTube video ID ─► anyone opening the same video gets it instantly, free
                       │
                       ▼
   Ask: the full transcript goes to Claude in a prompt-cached block, so follow-up questions are cheap
```

- **Backend:** a small FastAPI app. Jobs run on a thread pool, and finished results are cached in memory and mirrored to JSON files (`CACHE_DIR`). There is nothing else to run.
- **Frontend:** React and Vite. The visitor's library is stored in the browser (IndexedDB), so clearing site data clears it.
- **Uploads:** the file is streamed to a temp folder, its audio is transcribed on the server, and both are deleted right away. The same file uploaded again is served from the cache (it's identified by a hash of its contents). The video plays back from the visitor's own computer.
- **PDF export** happens in the browser (jsPDF, loaded only when used).
- **Cost control without accounts:** limits per visitor IP, plus a site-wide daily cap. Videos already in the cache don't count toward either.

## Tech stack

- **Frontend:** React 18, Vite, Tailwind CSS
- **Backend:** Python 3.12, FastAPI, Anthropic SDK, httpx, yt-dlp, FFmpeg, faster-whisper
- **Services:** Anthropic Claude API, TranscriptAPI.com (or Ollama and yt-dlp locally)

The backend image is about 820 MB, most of it the speech-to-text model baked in. It idles at about 100 MB of RAM and uses about 1.5 GB while transcribing an upload, so give it at least 2 GB (or set `ENABLE_UPLOADS=false` to run on 512 MB).

---

## Run it locally

**Requirements:** Python 3.12+, Node 20+, `ffmpeg` on your PATH (`brew install ffmpeg`), plus either an [Anthropic API key](https://console.anthropic.com) or [Ollama](https://ollama.com) with `ollama pull qwen3:8b`.

**Backend**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (and TRANSCRIPT_API_KEY if you have one)
uvicorn app.main:app --reload --reload-dir app --port 8000
```

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173.

**Tests**

```bash
cd backend
pip install pytest
python -m pytest tests -q
```

The 73 tests need no network or API keys; YouTube, TranscriptAPI and the AI are mocked. They try to break the API with bad links and IDs, malformed and oversized requests, limit abuse, spoofed IPs and prompt injection. They also cover failure handling (no captions, AI outage, crashes), caching, HTTPS redirects, security headers and CORS.

---

## Configuration

### Backend (`backend/.env`)

| Variable | Purpose | Default |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude for summaries and Ask | empty (use Ollama) |
| `ANTHROPIC_MODEL` | Claude model for every AI call: summaries, chapters and Ask | `claude-sonnet-5-5` |
| `ANTHROPIC_EFFORT` | `low` / `medium` / `high` | `low` |
| `TRANSCRIPT_API_KEY` | YouTube transcripts via TranscriptAPI.com (needed on servers) | empty (use yt-dlp) |
| `ALLOWED_ORIGINS` | Frontend URLs allowed to call the API | localhost |
| `CACHE_DIR` | Where finished results are cached | `./cache` (`/data/cache` in Docker) |
| `ANALYSES_PER_IP_PER_DAY` | New videos per visitor per 24 h | 5 |
| `ANALYSES_PER_DAY_TOTAL` | New videos for the whole site per 24 h (caps your bill) | 200 |
| `QUESTIONS_PER_IP_PER_HOUR` | Ask questions per visitor per hour | 30 |
| `MAX_VIDEO_MINUTES` | Longest video accepted | 180 |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute, all endpoints | 120 |
| `ENABLE_UPLOADS` | Allow video file uploads | on |
| `MAX_UPLOAD_MB` | Largest upload | 500 |
| `WHISPER_MODEL` | Speech-to-text model: `tiny`, `base`, `small`, `medium` | `small` |
| `TRANSCRIBE_CONCURRENCY` | Uploads transcribed at the same time | 1 |
| `FORCE_HTTPS` | Redirect HTTP to HTTPS behind a proxy, and send HSTS | on |
| `ENABLE_DOCS` | Serve API docs at `/docs` | off |

Set any limit to `0` for unlimited.

### Frontend (`frontend/.env`)

| Variable | Purpose |
| --- | --- |
| `VITE_API_URL` | Backend URL (`https://…` in production) |

---

## Deploying

- **Backend:** any Docker host. On Railway, set Root Directory to `backend` and the config file to `/backend/railway.toml`, then add `ANTHROPIC_API_KEY`, `TRANSCRIPT_API_KEY` and `ALLOWED_ORIGINS`. A volume at `/data` is optional: it keeps the result cache across deploys.
- **Frontend:** Vercel, with Root Directory `frontend` and `VITE_API_URL` set to the backend's `https://` URL. `frontend/vercel.json` handles routing and security headers. Its Content Security Policy allows backends on `*.up.railway.app` and `*.onrender.com`; add your domain there if you use a custom one.

## Security

- **HTTPS:** the hosting platforms terminate TLS. The API redirects plain-HTTP requests to HTTPS and sends HSTS, and so does the frontend.
- **Abuse and cost limits:** per-IP rate limiting on every endpoint, per-IP daily and site-wide daily caps on new analyses (uploads included), a per-IP question limit, a maximum video length, a maximum upload size, and a 16 KB cap on other request bodies.
- **Uploads:** only video file types are accepted, contents are checked with ffprobe before any work starts, files never leave the temp folder and are deleted after transcription.
- **AI guardrails:** transcripts and questions are treated as untrusted data and escaped so they can't break out of their tags. The model is told never to follow instructions inside them, and Ask answers only questions about the video. This was tested against jailbreaks, prompt-extraction attempts and off-topic requests.
- **Safe failures:** visitors only ever see friendly messages; details go to the server logs.
- **Headers:** Content Security Policy, `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy, and `no-store` on API responses.
- **Secrets:** `.env` files and cookie files are ignored by git, and the browser never sees an API key.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/analyze` | `{ "url": "<YouTube link>" }`. Starts or reuses an analysis and returns the job |
| `POST` | `/api/upload` | Multipart `file`. Starts or reuses an analysis of a video file |
| `GET` | `/api/videos/{id}` | Job status, plus the full result when ready (`?include_result=false` for status only) |
| `POST` | `/api/videos/{id}/ask` | `{ "question": "…" }`. Answer and source moments |
| `GET` | `/api/usage` | New videos used and allowed today for this visitor |

## Project structure

```
vidmind/
├── backend/
│   ├── app/
│   │   ├── api/routes/   analyze, videos, ask, usage, health
│   │   ├── core/         config, limits, security middleware
│   │   ├── services/     YouTube + TranscriptAPI, transcription, LLM client, summarizer, Ask, jobs + cache
│   │   ├── schemas.py
│   │   └── main.py
│   ├── tests/            adversarial API tests
│   ├── Dockerfile
│   └── railway.toml
├── frontend/
│   ├── src/
│   │   ├── components/   omnibox, player, cards, Ask
│   │   ├── pages/        Dashboard, VideoDetails
│   │   ├── services/     API client, browser library (IndexedDB), PDF export
│   │   └── hooks/        job polling
│   └── vercel.json
└── extension/            Chrome extension (talks to a local backend)
```

## Troubleshooting

- **"This video has no captions":** VidMind reads YouTube's captions, so videos without any (including auto-generated ones) can't be summarized.
- **"YouTube is asking VidMind to confirm it's not a bot"** (without TranscriptAPI): YouTube is blocking your IP. Set `TRANSCRIPT_API_KEY`, or locally point `YTDLP_COOKIES_FILE` at a `cookies.txt` exported from a browser signed in to YouTube.
- **"Can't reach VidMind":** check `VITE_API_URL`, and that the frontend's URL is listed in the backend's `ALLOWED_ORIGINS`.
