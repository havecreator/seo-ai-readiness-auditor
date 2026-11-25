@echo off
REM Double-click this file (Windows) to start the SEO & AI Readiness Auditor.
cd /d "%~dp0"

if not exist "app.py" (
    echo app.py was not found next to run.bat. Keep all project files in one folder.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\streamlit.exe" (
    echo First run: creating a virtual environment and installing requirements ^(1-2 minutes^)...
    where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
    if not exist ".venv\Scripts\python.exe" (
        echo Python 3 is not installed. Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH" during setup, then try again.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installing requirements failed. Check your internet connection.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\installed-requirements.txt" >nul
) else (
    fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul
    if errorlevel 1 (
        echo requirements.txt changed: updating packages...
        ".venv\Scripts\python.exe" -m pip install -r requirements.txt && copy /y requirements.txt ".venv\installed-requirements.txt" >nul
    )
)

set PYTHONWARNINGS=ignore
echo Starting the app... it will open in your browser at http://localhost:8501
echo Keep this window open while you use the app. Press Ctrl+C to stop.
start "" /min cmd /c "timeout /t 4 >nul & start http://localhost:8501"
".venv\Scripts\streamlit.exe" run app.py --server.port 8501
pause
