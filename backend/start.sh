#!/usr/bin/env bash
# Runs the API and the background worker in one container (they share the
# /data volume). If either process exits, stop the other so the platform
# restarts the container.
set -euo pipefail

# Create tables once before both processes start, to avoid racing on it.
python -c "import app.core.native_threads; from app.database.session import init_db; init_db()"

python -m app.worker &
WORKER_PID=$!

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*' &
API_PID=$!

trap 'kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null || true' TERM INT

wait -n "$WORKER_PID" "$API_PID"
EXIT_CODE=$?
kill -TERM "$WORKER_PID" "$API_PID" 2>/dev/null || true
wait || true
exit "$EXIT_CODE"
