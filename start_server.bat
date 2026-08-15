@echo off
TITLE NitroStream Launcher
echo Starting NitroStream Stack...

REM Set Project Directory
set PROJECT_DIR=D:\projects\homeserver\homeserver
set VENV_PYTHON=%PROJECT_DIR%\venv\Scripts\python.exe
set VENV_ACTIVATE=%PROJECT_DIR%\venv\Scripts\activate.bat

REM Verify Virtual Environment exists
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual Environment Python not found at %VENV_PYTHON%
    echo Please ensure the venv folder exists!
    pause
    exit /b
)

REM 1. Start Huey Worker
echo Launching Huey Worker...
start "Huey Worker" cmd /k "cd /d %PROJECT_DIR% && call "%VENV_ACTIVATE%" && "%VENV_PYTHON%" manage.py run_huey"

REM 2. Start Waitress Server
echo Launching Waitress Server...
start "Waitress Server" cmd /k "cd /d %PROJECT_DIR% && call "%VENV_ACTIVATE%" && "%VENV_PYTHON%" run.py"

REM 3. Start Nginx Server
echo Launching Nginx...
start "Nginx Server" cmd /c "cd /d C:\nginx && start nginx"

echo All services initiated successfully, King!
pause