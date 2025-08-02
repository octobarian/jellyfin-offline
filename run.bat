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
) else if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo No virtual environment found. Using system Python...
)

REM Run the application
echo Access the web interface at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.

python -m app.app

pause
