#!/usr/bin/env bash

set -e

echo ""
echo "=================================================="
echo "            WatchWise Setup"
echo "=================================================="
echo ""

# --------------------------------------------------
# Check Python
# --------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found."
    echo ""
    echo "Please install Python 3.11 or newer."
    exit 1
fi

echo "Python detected."

# --------------------------------------------------
# Enter backend
# --------------------------------------------------

cd backend

# --------------------------------------------------
# Create virtual environment
# --------------------------------------------------

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# --------------------------------------------------
# Upgrade pip
# --------------------------------------------------

echo "Upgrading pip..."
python -m pip install --upgrade pip

# --------------------------------------------------
# Install dependencies
# --------------------------------------------------

echo "Installing dependencies..."
pip install -r requirements.txt

# --------------------------------------------------
# Create .env
# --------------------------------------------------

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created backend/.env"
else
    echo "backend/.env already exists."
fi

echo ""
echo "=================================================="
echo "Setup completed successfully!"
echo "=================================================="
echo ""

echo "Next Steps:"
echo ""
echo "1. Open backend/.env"
echo ""
echo "Add your API keys:"
echo ""
echo "YouTube Data API"
echo "https://console.cloud.google.com/"
echo ""
echo "Gemini API"
echo "https://aistudio.google.com/apikey"
echo ""
echo "2. Start the backend:"
echo ""
echo "cd backend"
echo "source venv/bin/activate"
echo "uvicorn main:app --reload"
echo ""
echo "3. Load the Chrome extension:"
echo ""
echo "chrome://extensions"
echo "Enable Developer Mode"
echo "Load unpacked"
echo "Select the extension folder"
echo ""