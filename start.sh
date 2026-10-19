#!/usr/bin/env bash
# One-command start for CodeLiteracy on macOS/Linux (Windows: double-click start.bat).
set -e
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  echo "[1/3] First run: creating the Python environment..."
  python3 -m venv backend/.venv
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
fi
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "backend/.env was created. Paste your free Gemini key after GEMINI_API_KEY= (https://aistudio.google.com/apikey)."
fi
if [ ! -d frontend/node_modules ]; then
  echo "[2/3] First run: installing the frontend packages..."
  (cd frontend && npm install)
fi

echo "[3/3] Starting CodeLiteracy at http://localhost:5173 (Ctrl+C stops both)."
(cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000) &
BACKEND=$!
trap 'kill $BACKEND 2>/dev/null' EXIT
cd frontend && npm run dev
