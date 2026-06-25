#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"
URL="http://${HOST}:${PORT}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -U pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

if [ "${OPEN_BROWSER:-0}" = "1" ]; then
  (
    for _ in $(seq 1 80); do
      if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
        open "${URL}" >/dev/null 2>&1 || true
        exit 0
      fi
      sleep 0.5
    done
    open "${URL}" >/dev/null 2>&1 || true
  ) &
fi

exec .venv/bin/uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
