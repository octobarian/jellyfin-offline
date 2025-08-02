@echo off
REM Development run script for RV Media Player (Windows)
REM This script runs the application from the source directory

echo Starting RV Media Player...

REM Get the directory where the script is located
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Set environment variables
set PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%
set FLASK_APP=app/app.py
set FLASK_ENV=development

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    
    echo Installing dependencies...
    pip install --upgrade pip
    pip install -r requirements.txt
)

REM Check if mutagen is available
python -c "import mutagen" >nul 2>&1
if errorlevel 1 (
    echo Installing missing dependencies...
    pip install -r requirements.txt
)

REM Run the application
echo Access the web interface at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python -m app.app

pause
