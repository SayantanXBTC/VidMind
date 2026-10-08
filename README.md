# VidMind

**Free YouTube video summaries. No sign-up.** Paste a YouTube link, and in about thirty seconds you get:

- a one-line **TL;DR** and a written **summary**
- **key points** with concrete names and numbers
- **timestamped chapters** that jump the embedded player to that moment
- **Ask the video**: answers drawn from what's actually said, with moments you can jump to
- the full **transcript**, searchable

There are no accounts and no database. Your library lives in your browser, and every brief has a link you can share.

---

## How it works

```
YouTube link ─► TranscriptAPI.com (captions; yt-dlp fallback)
                       │
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
- **Cost control without accounts:** limits per visitor IP, plus a site-wide daily cap. Videos already in the cache don't count toward either.

## Tech stack

- **Frontend:** React 18, Vite, Tailwind CSS
- **Backend:** Python 3.12, FastAPI, Anthropic SDK, httpx, yt-dlp
- **Services:** Anthropic Claude API, TranscriptAPI.com (or Ollama and yt-dlp locally)

The backend image is about 70 MB and uses about 100 MB of RAM, so free hosting tiers can run it.

---

## Run it locally

**Requirements:** Python 3.12+ and Node 20+, plus either an [Anthropic API key](https://console.anthropic.com) or [Ollama](https://ollama.com) with `ollama pull qwen3:8b`.

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

The 58 tests need no network or API keys; YouTube, TranscriptAPI and the AI are mocked. They try to break the API with bad links and IDs, malformed and oversized requests, limit abuse, spoofed IPs and prompt injection. They also cover failure handling (no captions, AI outage, crashes), caching, HTTPS redirects, security headers and CORS.

---

## Configuration

### Backend (`backend/.env`)

| Variable | Purpose | Default |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude for summaries and Ask | empty (use Ollama) |
| `ANTHROPIC_MODEL` | `claude-opus-5-5`, `claude-sonnet-5-5` or `claude-haiku-5-5` | `claude-opus-5-5` |
| `ANTHROPIC_EFFORT` | `low` / `medium` / `high` | `low` |
| `TRANSCRIPT_API_KEY` | YouTube transcripts via TranscriptAPI.com (needed on servers) | empty (use yt-dlp) |
| `ALLOWED_ORIGINS` | Frontend URLs allowed to call the API | localhost |
| `CACHE_DIR` | Where finished results are cached | `./cache` (`/data/cache` in Docker) |
| `ANALYSES_PER_IP_PER_DAY` | New videos per visitor per 24 h | 5 |
| `ANALYSES_PER_DAY_TOTAL` | New videos for the whole site per 24 h (caps your bill) | 200 |
| `QUESTIONS_PER_IP_PER_HOUR` | Ask questions per visitor per hour | 30 |
| `MAX_VIDEO_MINUTES` | Longest video accepted | 180 |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute, all endpoints | 120 |
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
- **Abuse and cost limits:** per-IP rate limiting on every endpoint, per-IP daily and site-wide daily caps on new analyses, a per-IP question limit, a maximum video length, and a 16 KB cap on request bodies.
- **AI guardrails:** transcripts and questions are treated as untrusted data and escaped so they can't break out of their tags. The model is told never to follow instructions inside them, and Ask answers only questions about the video. This was tested against jailbreaks, prompt-extraction attempts and off-topic requests.
- **Safe failures:** visitors only ever see friendly messages; details go to the server logs.
- **Headers:** Content Security Policy, `X-Frame-Options: DENY`, `nosniff`, a strict referrer policy, and `no-store` on API responses.
- **Secrets:** `.env` files and cookie files are ignored by git, and the browser never sees an API key.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/analyze` | `{ "url": "<YouTube link>" }`. Starts or reuses an analysis and returns the job |
| `GET` | `/api/videos/{youtubeId}` | Job status, plus the full result when ready (`?include_result=false` for status only) |
| `POST` | `/api/videos/{youtubeId}/ask` | `{ "question": "…" }`. Answer and source moments |
| `GET` | `/api/usage` | New videos used and allowed today for this visitor |

## Project structure

```
vidmind/
├── backend/
│   ├── app/
│   │   ├── api/routes/   analyze, videos, ask, usage, health
│   │   ├── core/         config, limits, security middleware
│   │   ├── services/     YouTube + TranscriptAPI, LLM client, summarizer, Ask, jobs + cache
│   │   ├── schemas.py
│   │   └── main.py
│   ├── tests/            adversarial API tests
│   ├── Dockerfile
│   └── railway.toml
├── frontend/
│   ├── src/
│   │   ├── components/   omnibox, player, cards, Ask
│   │   ├── pages/        Dashboard, VideoDetails
│   │   ├── services/     API client, browser library (IndexedDB)
│   │   └── hooks/        job polling
│   └── vercel.json
└── extension/            Chrome extension (talks to a local backend)
```

## Troubleshooting

- **"This video has no captions":** VidMind reads YouTube's captions, so videos without any (including auto-generated ones) can't be summarized.
- **"YouTube is asking VidMind to confirm it's not a bot"** (without TranscriptAPI): YouTube is blocking your IP. Set `TRANSCRIPT_API_KEY`, or locally point `YTDLP_COOKIES_FILE` at a `cookies.txt` exported from a browser signed in to YouTube.
- **"Can't reach VidMind":** check `VITE_API_URL`, and that the frontend's URL is listed in the backend's `ALLOWED_ORIGINS`.
