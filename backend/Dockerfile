FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

# FFmpeg pulls the audio out of uploaded videos.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the speech-to-text model into the image so the first upload after a
# deploy doesn't wait for a ~500 MB download.
ARG WHISPER_MODEL=small
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"

COPY app ./app

# Result cache (optional persistent disk: mount a volume at /data).
ENV CACHE_DIR=/data/cache

# Railway sets $PORT; one worker process keeps the in-memory cache and limits
# consistent (jobs run on a thread pool inside it).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
