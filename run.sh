#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -U pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt

exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8787}" --reload

