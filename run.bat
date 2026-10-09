@echo off
cd /d "%~dp0"
python -m pip install -r backend\requirements.txt -r frontend\requirements.txt
start "ARES API" cmd /k "cd backend && python -m uvicorn app.main:app --port 8000"
timeout /t 3 >nul
cd frontend && python -m streamlit run streamlit_app.py
pause
