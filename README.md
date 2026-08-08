# WatchWise

> AI-powered Chrome Extension that analyzes YouTube videos using community feedback, transcripts, and Gemini to help you decide whether a video is worth your time.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![Chrome Extension](https://img.shields.io/badge/Manifest-V3-orange)
![Gemini](https://img.shields.io/badge/Powered%20by-Gemini-4285F4)

---

# Overview

Every day, students and developers spend hours on YouTube tutorials that turn out to be outdated, misleading, or simply low quality.

WatchWise helps users decide whether a video is worth watching by combining transcript analysis, community feedback, and AI reasoning into a single recommendation.

Instead of relying solely on likes or view counts, WatchWise evaluates multiple quality signals to generate a structured report that includes educational value, community trust, outdated content risk, misinformation risk, AI-generated summaries, and actionable recommendations.

---

# Features

- AI-assisted analysis of educational YouTube videos
- Watch Score (0–100)
- Educational Value Score
- Community Trust Score
- Outdated Content Detection
- Misinformation Risk Analysis
- Lightweight YouTube category pre-filter to reduce unnecessary AI calls
- AI-generated Summary
- Recommendation with Pros & Cons
- Community Evidence extracted from comments
- SQLite-backed response caching for faster repeated analyses
- Persistent Chrome Side Panel experience
- One-click "Analyze New Video" workflow
- Prompt Injection Protection
- HTML Sanitization
- Rate Limiting

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
                 │          ▼                     ▼
                 │          └─Category Pre-Filter─┘
                 │                     │
                 │                     ▼
                 │                Educational?
                 │
                 │               │         │
                 │               │ No      │ Yes
                 │               ▼         │
                 │          Return Early   │
                 │                         │
                 │                         ▼
                 │                  Gemini AI Analysis
                 │                         │
                 │                         ▼
                 │                  Store Result in Cache
                 │                         │
                 └─────────────────────────┘
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
│   ├── scripts/
│   ├── main.py
│   └── requirements.txt
│
├── extension/
│   ├── manifest.json
│   ├── background.js
│   ├── popup.html
│   ├── popup.js
│   ├── sidepanel.html
│   ├── sidepanel.js
│   ├── options.html
│   ├── options.js
│   └── icons/
│
├── setup.sh
├── setup.bat
└── README.md
```

---

# Installation

WatchWise runs entirely on your local machine.

You'll run the FastAPI backend locally and connect the Chrome extension to it.

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/BhargavMalakonda/WatchWise.git
cd WatchWise
```

Alternatively, download the repository as a ZIP and extract it.

---

## Step 2: Install Dependencies

### Windows

Run:

```bash
setup.bat
```

### macOS / Linux

Run:

```bash
chmod +x setup.sh
./setup.sh
```

The setup script automatically:

- Creates a Python virtual environment
- Installs all required dependencies
- Generates a starter `.env` file (if missing)

---

## Step 3: Configure API Keys

Open the generated `.env` file inside the `backend/` directory and add your API keys before starting the backend.

### Required API Keys

#### YouTube Data API v3

Get an API key from:

```text
https://console.cloud.google.com/
```

#### Google Gemini API

Get a free API key from:

```text
https://aistudio.google.com/apikey
```

Example:

```env
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

---

## Step 4: Start the Backend

### Windows

```bash
cd backend
venv\Scripts\activate
uvicorn main:app --reload
```

### macOS / Linux

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

---

## Step 5: Load the Chrome Extension

1. Open Google Chrome.
2. Navigate to:

```text
chrome://extensions
```

3. Enable **Developer Mode**.
4. Click **Load unpacked**.
5. Select the `extension/` folder.

The extension is now installed.

---

## Step 6: Open WatchWise

1. Open any YouTube video.
2. Click the WatchWise extension icon.
3. The WatchWise Side Panel will open.
4. Open **Settings**.
5. Expand **Advanced**.
6. Set:

```text
Backend URL
http://localhost:8000
```

7. Save the settings.

WatchWise will now communicate with your local FastAPI backend.

---


# Screenshots

## Side Panel

<img width="1917" height="963" alt="image" src="https://github.com/user-attachments/assets/5062b0ee-8bf4-4eeb-8045-472d02011420" />

---

## Settings Page

<img width="1917" height="970" alt="image" src="https://github.com/user-attachments/assets/feb3388a-a2bd-4dbb-beb9-2ad57b7011cd" />

---

## Analysis Result

<img width="1917" height="977" alt="image" src="https://github.com/user-attachments/assets/253271f0-c24b-4b2b-951c-c531ae8ed466" />

---

# Demo

A short demonstration video of WatchWise is available here:

```
(coming soon)
```

---

# Security

WatchWise has been designed with security in mind.

- API keys are never logged by WatchWise.
- Gemini API keys are loaded from the local `.env` file or supplied directly by the user through the extension.
- HTML content is sanitized before analysis.
- Prompt injection attempts inside transcripts or comments are treated strictly as data.
- Rate limiting helps protect the backend from abuse.
- Cached analyses never contain API keys or sensitive user information.

---

# Privacy Policy

WatchWise respects user privacy.

## Information Processed

To analyze a YouTube video, the backend processes:

- Video URL
- Video transcript (when available)
- Public YouTube comments
- Gemini API key (either from the local backend configuration or provided through the extension)

## Information Stored

The backend stores:

- Cached AI analysis results
- No user accounts
- No passwords
- No personal profile information
- No browsing history outside videos explicitly analyzed by the user
- No Gemini API keys inside the cache database

Gemini API keys are never logged, cached, or shared by WatchWise. When using the local backend configuration, keys remain stored only on the user's machine.

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

- WatchWise relies on YouTube-provided metadata and transcripts; inaccurate video categorization by YouTube may occasionally affect analysis eligibility.
- Educational-content detection is intentionally conservative and may allow some non-educational videos to be analyzed.
- Supports **English transcripts only**.
- Videos without accessible transcripts cannot currently be analyzed.
- Long transcripts are **truncated** before AI analysis to improve performance and control API costs.
- Community insights are based on public YouTube comments and should be treated as supporting evidence rather than absolute truth.
- Important technical, financial, legal, or medical information should always be verified using official sources.

---

# Future Improvements

- Chrome Web Store release
- Multi-language transcript support
- Improved educational-content classification beyond YouTube category metadata
- Playlist and channel-level analysis

---

# License

This project is licensed under the MIT License.

---

# Author

**Malakonda Chaitanya Bhargav**

Reliance Foundation Undergraduate Scholar

B.Tech Computer Science and Engineering (AI & ML)

SRM Institute of Science and Technology

GitHub: https://github.com/BhargavMalakonda

LinkedIn: https://www.linkedin.com/in/chaitanya-bhargav-malakonda/

---

If you find this project useful, consider giving it a star. Feedback, suggestions, and contributions are always welcome.
