@echo off
cd /d "%~dp0"
python -m pip install -r backend\requirements.txt
start "" http://localhost:8000
cd backend && python -m uvicorn app.main:app --port 8000
pause
