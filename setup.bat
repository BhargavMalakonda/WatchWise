@echo off
title WatchWise Setup

echo.
echo ==================================================
echo               WatchWise Setup
echo ==================================================
echo.

REM --------------------------------------------------
REM Check Python
REM --------------------------------------------------

where python >nul 2>nul

if errorlevel 1 (
    echo Python was not found.
    echo.
    echo Please install Python 3.11 or newer:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b
)

echo Python detected.
echo.

REM --------------------------------------------------
REM Enter backend
REM --------------------------------------------------

cd backend

REM --------------------------------------------------
REM Create virtual environment
REM --------------------------------------------------

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate

echo.

REM --------------------------------------------------
REM Upgrade pip
REM --------------------------------------------------

echo Upgrading pip...
python -m pip install --upgrade pip

echo.

REM --------------------------------------------------
REM Install dependencies
REM --------------------------------------------------

echo Installing dependencies...
pip install -r requirements.txt

echo.

REM --------------------------------------------------
REM Create .env
REM --------------------------------------------------

if not exist .env (
    copy .env.example .env
    echo Created backend\.env
) else (
    echo backend\.env already exists.
)

echo.

REM --------------------------------------------------
REM Finished
REM --------------------------------------------------

echo ==================================================
echo Setup completed successfully!
echo ==================================================
echo.

echo Next Steps:
echo.
echo 1. Open backend\.env
echo.
echo Add your API keys:
echo.
echo   YouTube Data API
echo   https://console.cloud.google.com/
echo.
echo   Gemini API
echo   https://aistudio.google.com/apikey
echo.
echo 2. Start the backend:
echo.
echo      cd backend
echo      venv\Scripts\activate
echo      uvicorn main:app --reload
echo.
echo 3. Load the Chrome extension:
echo.
echo      chrome://extensions
echo      Enable Developer Mode
echo      Click "Load unpacked"
echo      Select the extension folder
echo.

pause