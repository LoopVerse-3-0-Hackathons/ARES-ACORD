#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -m pip install -r backend/requirements.txt
(sleep 3; python3 -c "import webbrowser;webbrowser.open('http://localhost:8000')") &
cd backend && python3 -m uvicorn app.main:app --port 8000
