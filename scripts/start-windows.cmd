@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0.." || (
    echo Cannot open the VOC Workbench project folder.
    exit /b 1
)
call :start_workbench
set "VOC_START_EXIT=%errorlevel%"
popd
exit /b %VOC_START_EXIT%

:start_workbench
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Cannot create the environment. Install Python 3.12 with the Windows Python launcher.
        exit /b 1
    )
)
if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 (
        echo Cannot create .env. Check that the project directory is writable and .env.example exists.
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
echo Open http://127.0.0.1:8765/ in your browser. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn src.dashboard.app:app --host 127.0.0.1 --port 8765
exit /b %errorlevel%
