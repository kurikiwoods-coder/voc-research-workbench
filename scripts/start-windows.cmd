@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 exit /b 1
)
if not exist ".env" copy /Y ".env.example" ".env" >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Open http://127.0.0.1:8765/ in your browser. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
