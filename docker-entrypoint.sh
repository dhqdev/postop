#!/bin/sh
set -e
ROLE="${1:-api}"
export ROLE
case "$ROLE" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' \
      --workers "${API_WORKERS:-2}"
    ;;
  worker)
    exec python -m app.worker
    ;;
  *)
    exec "$@"
    ;;
esac
