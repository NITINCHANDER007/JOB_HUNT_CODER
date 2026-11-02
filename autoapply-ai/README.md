# 🤖 AutoApply AI (Native Windows Edition)

**AutoApply AI** is an intelligent job application automation platform that uses AI (Google Gemini) and browser automation (Playwright) to research job postings, tailor your resume, and submit applications on your behalf — all while tracking every submission in a unified dashboard with Gmail confirmation monitoring and interactive co-pilot assistance.

---

## Table of Contents

1. [Why Native Windows (No Docker)](#why-native-windows-no-docker)
2. [Prerequisites](#prerequisites)
3. [Quick Start (Windows)](#quick-start-windows)
4. [Architecture](#architecture)
5. [Environment Variables Reference](#environment-variables-reference)
6. [Generating Secret Keys](#generating-secret-keys)
7. [Gemini AI Configuration](#gemini-ai-configuration)
8. [Google OAuth & Gmail Setup](#google-oauth--gmail-setup)
9. [Running the Services](#running-the-services)
10. [Running Automated Tests](#running-automated-tests)
11. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## Why Native Windows (No Docker)

AutoApply AI is designed for **native Windows execution** without Docker.

### Why Docker Was Removed:
1. **Desktop Chrome Visibility**: In Docker (Linux containers), browser automation runs in isolated virtual containers without access to the host Windows Desktop Window Manager (DWM). This prevented users from seeing Chrome open on their desktop.
2. **Interactive LinkedIn Login**: Easy Apply requires manual authentication (2FA, SMS OTP, CAPTCHA challenges) inside your own browser. Native execution launches your real desktop Google Chrome with a persistent profile (`browser_profiles/user_<id>`) so you can log in naturally.
3. **Simpler Setup**: No Docker Desktop or WSL2 configuration needed. AutoApply AI runs directly using a standard Python virtual environment (`.venv`) with an automatic SQLite database and built-in asynchronous background workers.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | 3.11+ | Standard Windows Python installer (tested up to 3.14) |
| **pip** | 23+ | Bundled with Python |
| **Google Chrome** | Latest | Installed at standard path (`C:\Program Files\Google\Chrome\Application\chrome.exe`) |
| **Playwright** | 1.47+ | Installed in virtualenv (`playwright install chromium`) |
| **Git** | Any | For version control |

---

## Quick Start (Windows)

The simplest way to run AutoApply AI on Windows:

### 1. Clone the repository
```cmd
git clone https://github.com/NITINCHANDER007/JOB_HUNT_CODER.git
cd JOB_HUNT_CODER
```

### 2. Configure Environment
Copy `.env.example` to `autoapply-ai\.env` if not already present:
```cmd
copy autoapply-ai\.env.example autoapply-ai\.env
```
*(Default settings use SQLite and local background threads with zero manual database or Redis setup needed!)*

### 3. Launch the Server
Double-click `run_server.bat` or run:
```cmd
run_server.bat
```
This script will:
- Automatically create a Python virtual environment (`.venv`) if one does not exist.
- Activate the virtual environment.
- Start the server on **http://localhost:5050**.

Open **http://localhost:5050** in your web browser!

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AutoApply AI (Native Windows)                        │
├────────────────────────────────┬────────────────────────────────────────┤
│   Frontend SPA                 │              Backend (Flask)           │
│   (Vanilla JS + Components)    │                                        │
│   http://localhost:5050        │   /api/auth          /api/profile      │
│                                │   /api/applications  /api/linkedin     │
│   Apply (#/apply) ─────────────┼──▶ Flask App (Port 5050)               │
│   Profile (#/profile)          │         │                              │
└────────────────────────────────┘         │                              │
                                           ▼                              │
                                 ┌──────────────────┐                     │
                                 │  SQLite Database  │ (instance/autoapply.db)
                                 │  (or PostgreSQL) │                     │
                                 └──────────────────┘                     │
                                           │                              │
                        ┌──────────────────┴──────────────────┐           │
                        ▼                                     ▼           │
             ┌─────────────────────┐               ┌────────────────────┐ │
             │ Native Background   │               │ Celery Worker      │ │
             │ Daemon Threads      │ (Default)     │ (Optional, if      │ │
             │ (Async processing)  │               │  Redis is running) │ │
             └──────────┬──────────┘               └─────────┬──────────┘ │
                        │                                    │            │
                        └──────────────────┬─────────────────┘            │
                                           ▼                              │
                                 ┌──────────────────┐                     │
                                 │ Native Windows   │                     │
                                 │ Google Chrome    │                     │
                                 │ (Playwright CDP) │                     │
                                 │                  │                     │
                                 │ 💼 LinkedIn      │                     │
                                 │ 🌿 Greenhouse    │                     │
                                 │ 🚀 Lever         │                     │
                                 │ 📋 Ashby/Workday │                     │
                                 └──────────────────┘                     │
```

---

## Environment Variables Reference

Key configuration options in `autoapply-ai/.env`:

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Flask runtime environment (`development` / `production`) |
| `FLASK_SECRET_KEY` | *(random key)* | Secret key for Flask session security |
| `DATABASE_URL` | `sqlite:///autoapply.db` | Database connection string. Supports SQLite and PostgreSQL |
| `APP_PORT` | `5050` | HTTP port for Flask and frontend |
| `REDIS_URL` | `redis://localhost:6379/0` | Optional Redis URL for Celery |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Optional Celery broker URL |
| `JWT_SECRET_KEY` | *(random key)* | Secret key used to sign JWT auth tokens |
| `JWT_ACCESS_TOKEN_EXPIRES`| `86400` | JWT token lifetime in seconds (24h) |
| `FERNET_KEY` | *(base64 key)* | AES encryption key for securing stored OAuth tokens |
| `GEMINI_API_KEY` | `""` | Google Gemini API key for resume parsing and tailoring |
| `GEMINI_MODEL` | `gemini-2.0-flash`| Gemini model to use |
| `PLAYWRIGHT_HEADLESS` | `false` | Set to `false` to watch Chrome fill forms live on your screen |
| `REQUIRE_USER_APPROVAL` | `true` | Requires manual user confirmation before final application submit |

---

## Running Automated Tests

To run the complete test suite:
```cmd
run_tests.bat
```
Or via PowerShell:
```powershell
$env:PYTHONPATH="autoapply-ai/backend"; .\.venv\Scripts\python.exe -m pytest autoapply-ai/backend/tests -v
```

All 31 automated tests cover:
- LinkedIn session detection, manual login flow, and CDP verification
- Portal automation (Greenhouse, Lever, Ashby, Workday, ByteDance)
- In-page CAPTCHA and review approval handling
- Resume parsing and completeness scoring

---

## Project Structure

```
JOB_HUNT_CODER/
├── run_server.bat            # One-click Windows startup script
├── run_tests.bat             # One-click test runner
├── .gitignore                # Git ignore rules
├── README.md                 # Project documentation
│
└── autoapply-ai/
    ├── .env                  # Active local environment variables
    ├── .env.example          # Environment variable template
    │
    ├── backend/
    │   ├── run.py            # Flask entry point (http://localhost:5050)
    │   ├── requirements.txt  # Python package dependencies
    │   │
    │   ├── app/
    │   │   ├── __init__.py   # Application factory
    │   │   ├── config.py     # Centralized settings
    │   │   ├── models/       # SQLAlchemy models (User, Profile, Application)
    │   │   ├── api/          # Blueprints (Auth, Apply, Profile, LinkedIn)
    │   │   ├── services/     # Orchestrator, Browser Session, AI, Resume Parser
    │   │   ├── adapters/     # Portal-specific form fillers
    │   │   └── worker/       # Background tasks (native threads / Celery)
    │   │
    │   ├── instance/
    │   │   └── autoapply.db  # SQLite database instance
    │   │
    │   ├── browser_profiles/ # Dedicated user Chrome profiles & cookies
    │   ├── uploads/          # Uploaded resumes & screenshots
    │   └── tests/            # Automated test suite
    │
    └── frontend/
        ├── index.html        # SPA shell with dark theme
        └── src/
            ├── components/   # Router, API client, Toast, Chatbot
            ├── pages/        # Apply, Profile, Auth
            └── styles/       # CSS stylesheets
```

---

## Troubleshooting & FAQ

### 1. Chrome is not opening on my desktop
- Make sure Google Chrome is installed on Windows at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- Ensure no zombie Chrome process is locking your profile directory. AutoApply AI automatically cleans up profile locks, but you can also close any background Chrome tasks using Task Manager.

### 2. Can I use PostgreSQL instead of SQLite?
Yes! Set `DATABASE_URL` in `autoapply-ai/.env`:
```env
DATABASE_URL=postgresql://autoapply:autoapply_pass@localhost:5432/autoapply_db
```

### 3. Do I need Redis or Celery to run applications?
No. If Redis is offline, AutoApply AI automatically uses native Python daemon background threads to process applications seamlessly. If you run Redis, Celery will automatically be used.
