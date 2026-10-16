#!/usr/bin/env bash
# Self-contained local run for macOS / Linux (no cloud database, no accounts needed).
# First run builds the dataset + finance layer + 3 models + clusters (~4 min), seeds demo users, then serves.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FINSHIELD_LOCAL=1
cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv; .venv/bin/python -m pip install -e ".[dev]"; }
if [ ! -f "$ROOT/artifacts/local/finshield.db" ]; then .venv/bin/python -m app.ml.pipeline all; fi
.venv/bin/python -m app.cli seed-users
.venv/bin/python -m uvicorn app.main:app --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT
cd "$ROOT/frontend"
[ -d node_modules ] || npm install
npm run dev
