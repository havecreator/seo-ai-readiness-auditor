#!/bin/bash
# Double-click this file (macOS) to start the SEO & AI Readiness Auditor.
cd "$(dirname "$0")" || exit 1

if [ ! -f "app.py" ]; then
  echo "app.py was not found next to run.command. Keep all project files in one folder."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x ".venv/bin/streamlit" ]; then
  echo "First run: creating a virtual environment and installing requirements (1-2 minutes)..."
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ and try again."
    read -r -p "Press Enter to close..."
    exit 1
  fi
  python3 -m venv .venv || { read -r -p "Could not create .venv. Press Enter to close..."; exit 1; }
  ./.venv/bin/python -m pip install --upgrade pip
  ./.venv/bin/python -m pip install -r requirements.txt || { read -r -p "Install failed. Press Enter to close..."; exit 1; }
  cp requirements.txt .venv/installed-requirements.txt
elif ! cmp -s requirements.txt .venv/installed-requirements.txt; then
  echo "requirements.txt changed: updating packages..."
  ./.venv/bin/python -m pip install -r requirements.txt && cp requirements.txt .venv/installed-requirements.txt
fi

echo "Starting the app... it will open in your browser at http://localhost:8501"
echo "Keep this window open while you use the app. Press Ctrl+C to stop."
( sleep 4; open "http://localhost:8501" ) &
PYTHONWARNINGS=ignore ./.venv/bin/streamlit run app.py --server.port 8501
