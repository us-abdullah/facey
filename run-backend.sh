#!/usr/bin/env bash
# Free port 8000 and start backend. Run from facey/ or project root.
cd "$(dirname "$0")/backend"
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
if [[ -d venv ]]; then
  source venv/bin/activate
fi
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
