# WatchWise

> AI-powered Chrome Extension that analyzes YouTube videos using community feedback, transcripts, and Gemini to help you decide whether a video is worth your time.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![Chrome Extension](https://img.shields.io/badge/Manifest-V3-orange)
![Gemini](https://img.shields.io/badge/Powered%20by-Gemini-4285F4)

### Third-Party Services

WatchWise integrates with Google Gemini API, YouTube Data API, and YouTube Transcript API. Use of these services is subject to their respective terms of service and usage limits.
---

# Overview

Every day, students and developers spend hours on YouTube tutorials that turn out to be outdated, misleading, or simply low quality.

WatchWise helps users decide whether a video is worth watching by combining transcript analysis, community feedback, and AI reasoning into a single recommendation.

Instead of relying solely on likes or view counts, WatchWise evaluates multiple quality signals to generate a structured report that includes educational value, community trust, outdated content risk, misinformation risk, AI-generated summaries, and actionable recommendations.

---

# Features

- AI-powered analysis of educational YouTube videos
- Watch Score (0–100)
- Educational Value Score
- Community Trust Score
- Outdated Content Detection
- Misinformation Risk Analysis
- AI-generated Summary
- Recommendation with Pros & Cons
- Community Evidence extracted from comments
- SQLite-backed response caching for faster repeated analyses
- Bring Your Own Gemini API Key (BYOK)
- Prompt Injection Protection
- HTML Sanitization
- Rate Limiting
- Hosted and self-hostable backend

---

# Architecture

```text
                    Chrome Extension
                            │
                            ▼
                     FastAPI Backend
                            │
                            ▼
                  SQLite Cache Lookup
                            │
                 ┌──────────┴──────────┐
                 │                     │
           Cache Hit              Cache Miss
                 │                     │
                 │          ┌──────────┴──────────┐
                 │          ▼                     ▼
                 │   YouTube Data API   YouTube Transcript API
                 │          │                     │
                 │          └──────────┬──────────┘
                 │                     ▼
                 │             Gemini AI Analysis
                 │                     │
                 │                     ▼
                 │          Store Result in Cache
                 │                     │
                 └──────────────┬──────┘
                                ▼
                    Recommendation Response
```

---

# Tech Stack

## Frontend

- Chrome Extension (Manifest V3)
- HTML
- CSS
- JavaScript

## Backend

- Python
- FastAPI
- Uvicorn

## Artificial Intelligence

- Google Gemini API

## Data Sources

- YouTube Data API
- YouTube Transcript API

## Database

- SQLite

---

# Project Structure

```text
WatchWise/
│
├── backend/
│   ├── core/
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
│   
│
└── extension/
    ├── manifest.json
    ├── popup.html
    ├── popup.js
    ├── options.html
    ├── options.js
    └── icons/
```

---

# Installation

## Using the Hosted Backend (Recommended)

WatchWise is designed to work out of the box using the hosted backend. No Python installation or backend setup is required.

### Step 1: Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/WatchWise.git
cd WatchWise
```

Alternatively, download the repository as a ZIP and extract it.

---

### Step 2: Load the Chrome Extension

1. Open Google Chrome.
2. Navigate to:

```
chrome://extensions
```

3. Enable **Developer Mode** (top-right corner).
4. Click **Load unpacked**.
5. Select the `extension/` folder from this repository.

The extension is now installed and ready to use.

By default, it connects to the hosted WatchWise backend automatically.

---

## Bring Your Own Gemini API Key (Optional)

WatchWise works without a personal Gemini API key by using the hosted backend's shared daily quota.

If the shared quota has been exhausted, or if you prefer to use your own Gemini API key:

1. Open the extension.
2. Click the **Settings** icon.
3. Select **My Gemini API Key**.
4. Generate a free API key from:

```
https://aistudio.google.com/apikey
```

5. Paste your API key and save.

Your API key:

- is stored only in your browser using `chrome.storage.local`
- is never logged
- is never stored on the server
- is used only for the current analysis request

---

# Self-Hosting (Optional)

Developers who want to run their own backend or contribute to WatchWise can self-host the FastAPI server.

## Backend Setup

Navigate to the backend directory.

```bash
cd backend
```

Create a virtual environment.

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies.

```bash
pip install -r requirements.txt
```

Create a `.env` file inside the `backend/` directory.

```env
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
DEFAULT_DAILY_QUOTA=100
```
### Getting the required API Keys

#### YouTube Data API Key

Visit the **Google Cloud Console**:

   https://console.cloud.google.com/

#### Gemini API Key

Visit **Google AI Studio**:

   https://aistudio.google.com/apikey

Start the backend.

```bash
uvicorn main:app --reload
```

The backend will be available at:

```
http://localhost:8000
```

Interactive API documentation is available at:

```
http://localhost:8000/docs
```

---

## Using a Local Backend

If you are running your own backend:

1. Open the extension.
2. Click **Settings**.
3. Expand the **Advanced** section.
4. Change the Backend URL to:

```
http://localhost:8000
```

5. Save the settings.

The extension will now communicate with your locally hosted backend instead of the public WatchWise server.

---

# Screenshots

## Extension Popup

*(Add screenshot here)*

---

## Settings Page

*(Add screenshot here)*

---

## Analysis Result

*(coming soon)*

---

# Demo

A short demonstration video of WatchWise is available here:

```
(coming soon)
```

---

# Security

WatchWise has been designed with security in mind.

- API keys are never logged.
- User-supplied Gemini API keys are never stored on the server.
- HTML is sanitized before analysis.
- Prompt injection attempts inside transcripts or comments are treated strictly as data.
- Rate limiting protects the backend against abuse.
- Cached analyses never contain user API keys or sensitive information.

---

# Privacy Policy

WatchWise respects user privacy.

## Information Processed

To analyze a YouTube video, the backend processes:

- Video URL
- Video transcript (when available)
- Public YouTube comments
- Optional user-supplied Gemini API key (only for the current request)

## Information Stored

The backend stores:

- Cached AI analysis results
- No personal user accounts
- No passwords
- No browsing history
- No user Gemini API keys

User-provided Gemini API keys are used only for the current analysis request and are never logged, persisted, cached, or shared.

---

# Contributing & Project Notes

Contributions are welcome! If you'd like to improve WatchWise:

1. Fork the repository.
2. Create a feature branch.
   ```bash
   git checkout -b feature/my-feature
   ```
3. Commit and push your changes.
4. Open a Pull Request with a clear description.

Before submitting, please ensure that:

- Existing functionality continues to work.
- Tests pass successfully.
- No API keys or sensitive information are committed.
- Documentation is updated when necessary.

### Current Limitations

WatchWise is an AI-assisted recommendation tool and should not be treated as an authoritative source.

Current limitations include:

- Supports **English transcripts only**.
- Videos without accessible transcripts cannot currently be analyzed.
- Long transcripts are **truncated** before AI analysis to improve performance and control API costs.
- Community insights are based on public YouTube comments and should be treated as supporting evidence rather than absolute truth.
- Important technical, financial, legal, or medical information should always be verified using official sources.

---

# Future Improvements

- Chrome Web Store release
- Multi-language transcript support
- Automatic video category detection (Education, Music, Gaming, News, etc.)
- Playlist and channel-level analysis

---

# License

This project is licensed under the MIT License.

---

# Author

**Malakonda Chaitanya Bhargav**

B.Tech Computer Science and Engineering (AI & ML)

SRM Institute of Science and Technology

GitHub: https://github.com/BhargavMalakonda

LinkedIn: https://www.linkedin.com/in/chaitanya-bhargav-malakonda/

---

If you find this project useful, consider giving it a star. Feedback, suggestions, and contributions are always welcome.
