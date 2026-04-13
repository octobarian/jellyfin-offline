@echo off
REM Windows setup script for RV Media Player development
REM This script installs required Python dependencies

echo Setting up RV Media Player for Windows development...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://python.org
    pause
    exit /b 1
)

REM Check if pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available
    echo Please ensure Python is properly installed
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install required dependencies
echo Installing required dependencies...
pip install flask
pip install requests
pip install python-dotenv
pip install watchdog
pip install mutagen
pip install pillow
pip install qrcode[pil]
pip install cryptography
pip install pyyaml
pip install jsonschema
pip install pymediainfo
pip install python-vlc

REM Check if all dependencies installed successfully
echo.
echo Checking installation...
python -c "import flask; print('✓ Flask installed')"
python -c "import mutagen; print('✓ Mutagen installed')"
python -c "import requests; print('✓ Requests installed')"
python -c "import PIL; print('✓ Pillow installed')"
python -c "import qrcode; print('✓ QRCode installed')"
python -c "import cryptography; print('✓ Cryptography installed')"
python -c "import yaml; print('✓ PyYAML installed')"
python -c "import jsonschema; print('✓ JSONSchema installed')"
python -c "import pymediainfo; print('✓ PyMediaInfo installed')"

echo.
echo Setup completed successfully!
echo.
echo To run the application:
echo 1. Ensure virtual environment is activated: venv\Scripts\activate.bat
echo 2. Run: python -m app.app
echo 3. Access: http://localhost:5000
echo.
pause
