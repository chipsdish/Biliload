#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"
URL="http://${HOST}:${PORT}"

if curl -fsS "${URL}/api/health" >/dev/null 2>&1; then
  open "${URL}"
  exit 0
fi

export HOST
export PORT
export OPEN_BROWSER=1

exec ./run.sh
