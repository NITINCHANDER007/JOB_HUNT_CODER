# 🤖 AutoApply AI

**AutoApply AI** is an intelligent job application automation platform that uses AI (Google Gemini) and browser automation (Playwright) to research job postings, tailor your resume and cover letter, and submit applications on your behalf — all while tracking every submission in a dashboard with Gmail confirmation monitoring.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start (Docker)](#quick-start-docker)
5. [Manual Setup (No Docker)](#manual-setup-no-docker)
6. [Environment Variables Reference](#environment-variables-reference)
7. [Generating Secret Keys](#generating-secret-keys)
8. [Gemini API Key](#gemini-api-key)
9. [Google OAuth & Gmail Setup](#google-oauth--gmail-setup)
10. [Running the Services](#running-the-services)
11. [Adding a New Platform Adapter](#adding-a-new-platform-adapter)
12. [API Endpoints Reference](#api-endpoints-reference)
13. [Troubleshooting](#troubleshooting)

---

## Project Overview

AutoApply AI automates the most tedious parts of a job search:

| Feature | Description |
|---|---|
| **Resume Parsing** | Extracts structured data from PDF/DOCX resumes using pdfplumber + PyMuPDF |
| **AI Tailoring** | Uses Gemini to rewrite resume bullets and generate cover letters for each job |
| **Browser Automation** | Playwright fills and submits application forms on LinkedIn, Indeed, Greenhouse, Lever, Workday, and more |
| **Application Tracking** | PostgreSQL-backed dashboard tracks every application with status, timestamps, and screenshots |
| **Gmail Monitoring** | Google OAuth reads your inbox for confirmation emails and updates application status automatically |
| **Async Processing** | Celery + Redis queue handles browser sessions so the API stays fast |
| **Rate Limiting** | Configurable daily application caps prevent ban-triggering bursts |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          AutoApply AI                               │
├───────────────────┬─────────────────────────────────────────────────┤
│   Frontend        │              Backend (Flask)                     │
│   (React/Vite)    │                                                  │
│   localhost:3000  │   /api/auth          /api/profile               │
│                   │   /api/applications  /api/dashboard              │
│   HTML/CSS/JS ────┼──▶ Flask App (port 5000)                        │
│                   │         │                                        │
└───────────────────┘         │                                        │
                              ▼                                        │
                     ┌────────────────┐                               │
                     │  PostgreSQL 16  │  (application data,          │
                     │  port 5432      │   users, profiles)           │
                     └────────────────┘                               │
                              │                                        │
                     ┌────────▼───────┐       ┌──────────────────┐   │
                     │  Redis 7        │◀─────▶│  Celery Worker   │   │
                     │  port 6379      │       │  (browser tasks) │   │
                     └────────────────┘       └────────┬─────────┘   │
                                                       │              │
                                              ┌────────▼─────────┐   │
                                              │  Playwright       │   │
                                              │  (Chromium)       │   │
                                              │                   │   │
                                              │  ┌─────────────┐ │   │
                                              │  │ LinkedIn     │ │   │
                                              │  │ Indeed       │ │   │
                                              │  │ Greenhouse   │ │   │
                                              │  │ Lever        │ │   │
                                              │  │ Workday      │ │   │
                                              │  │ Custom...    │ │   │
                                              │  └─────────────┘ │   │
                                              └──────────────────┘   │
                                                                      │
                     ┌────────────────┐       ┌──────────────────┐   │
                     │  Gemini API    │       │  Google OAuth    │   │
                     │  (AI tailoring)│       │  (Gmail reading) │   │
                     └────────────────┘       └──────────────────┘   │
                                                                      │
                     ┌────────────────┐                               │
                     │  Flower UI     │  (Celery task monitor)        │
                     │  port 5555     │                               │
                     └────────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

**Request flow for a new application:**

```
User clicks "Apply" in UI
        │
        ▼
POST /api/applications/submit
        │
        ▼
Flask validates & saves JobApplication (status=queued)
        │
        ▼
Celery task enqueued in Redis
        │
        ▼
Worker picks up task:
  1. Gemini tailors resume + cover letter
  2. Playwright launches Chromium
  3. Navigates to job URL
  4. Fills & submits form
  5. Takes screenshot
  6. Updates DB (status=submitted / failed)
        │
        ▼
Gmail poller (periodic Celery beat task)
  Scans inbox for confirmation emails
  Updates status=confirmed
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | Required |
| pip | 23+ | Comes with Python |
| Docker & Docker Compose | Latest | For containerized setup |
| Node.js | 18+ | Optional — only needed to build/develop the frontend |
| npm or pnpm | Latest | Optional — frontend only |
| Git | Any | For cloning |

> **Windows users:** Docker Desktop is recommended. WSL2 backend gives the best Playwright compatibility.

---

## Quick Start (Docker)

The fastest way to get everything running:

```bash
# 1. Clone the repo
git clone https://github.com/yourname/autoapply-ai.git
cd autoapply-ai

# 2. Copy and configure environment
cp .env.example .env
# Edit .env — at minimum set GEMINI_API_KEY and the secret keys (see below)

# 3. Build and start all services
docker compose up --build

# 4. In a new terminal, run database migrations
docker compose exec app flask db upgrade

# 5. Open the app
#    API:     http://localhost:5000/health
#    Flower:  http://localhost:5555
#    Frontend: http://localhost:3000 (if frontend container added)
```

To stop everything:
```bash
docker compose down
# To also delete volumes (wipes DB and Redis):
docker compose down -v
```

---

## Manual Setup (No Docker)

### 1. Install PostgreSQL and Redis

**Windows:**
- PostgreSQL: https://www.postgresql.org/download/windows/
- Redis: Use the Windows port from https://github.com/tporadowski/redis/releases or run via WSL2

**macOS (Homebrew):**
```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install -y postgresql redis-server
sudo systemctl start postgresql redis-server
```

### 2. Create the database

```bash
psql -U postgres
CREATE USER autoapply WITH PASSWORD 'autoapply_pass';
CREATE DATABASE autoapply_db OWNER autoapply;
\q
```

### 3. Set up Python environment

```bash
cd autoapply-ai/backend

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
playwright install-deps chromium   # Linux only
```

### 4. Configure environment

```bash
cd ..   # back to autoapply-ai/
cp .env.example .env
# Edit .env with your values
```

### 5. Run database migrations

```bash
cd backend
flask db upgrade
```

### 6. Start the backend

```bash
# Terminal 1 — Flask API
flask run --host=0.0.0.0 --port=5000

# Terminal 2 — Celery worker
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — Flower monitor (optional)
celery -A app.worker.celery_app flower --port=5555
```

### 7. Start the frontend (optional)

```bash
cd autoapply-ai/frontend
npm install
npm run dev
# Open http://localhost:3000
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `FLASK_ENV` | No | `production` | `development` enables debug mode & hot reload |
| `FLASK_SECRET_KEY` | **Yes** | — | Flask session signing key (32+ random chars) |
| `DATABASE_URL` | **Yes** | SQLite fallback | PostgreSQL connection string |
| `REDIS_URL` | **Yes** | `redis://localhost:6379/0` | Redis connection for Celery broker |
| `CELERY_BROKER_URL` | No | `REDIS_URL` | Celery broker (defaults to REDIS_URL) |
| `CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/1` | Celery result store |
| `JWT_SECRET_KEY` | **Yes** | — | JWT signing secret (32+ random chars) |
| `JWT_ACCESS_TOKEN_EXPIRES` | No | `86400` | Token TTL in seconds (default: 24 h) |
| `FERNET_KEY` | **Yes** | — | Fernet symmetric encryption key for stored credentials |
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model name |
| `GOOGLE_CLIENT_ID` | For Gmail | — | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | For Gmail | — | OAuth 2.0 client secret |
| `GOOGLE_REDIRECT_URI` | For Gmail | `http://localhost:5000/api/auth/gmail/callback` | OAuth callback URL |
| `UPLOAD_FOLDER` | No | `uploads` | Root upload directory |
| `RESUME_FOLDER` | No | `uploads/resumes` | Resume file storage |
| `SCREENSHOT_FOLDER` | No | `uploads/screenshots` | Application screenshots |
| `MAX_CONTENT_LENGTH` | No | `16777216` | Max upload size in bytes (16 MB) |
| `MAX_APPLICATIONS_PER_DAY` | No | `50` | Daily application rate cap |
| `PLAYWRIGHT_HEADLESS` | No | `true` | Run browser headlessly |
| `PLAYWRIGHT_TIMEOUT` | No | `30000` | Browser action timeout (ms) |
| `APP_HOST` | No | `0.0.0.0` | Flask bind host |
| `APP_PORT` | No | `5000` | Flask bind port |
| `FRONTEND_URL` | No | `http://localhost:3000` | CORS allowed origin for frontend |

---

## Generating Secret Keys

### Flask Secret Key & JWT Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run twice — once for `FLASK_SECRET_KEY`, once for `JWT_SECRET_KEY`. Each output is a unique 64-character hex string.

### Fernet Encryption Key

Fernet keys must be generated with the cryptography library (they are URL-safe base64-encoded 32-byte keys):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output into `FERNET_KEY` in your `.env`. **Never reuse this key across environments.**

> ⚠️ **Warning:** If you change `FERNET_KEY` after data has been encrypted and stored, all encrypted credential records become unreadable. Rotate keys carefully using a migration script.

---

## Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key and set `GEMINI_API_KEY=your-key` in `.env`
5. Optionally set `GEMINI_MODEL=gemini-2.0-flash` (default) or another available model

Free tier includes generous quota for development. For production, review [pricing](https://ai.google.dev/pricing).

---

## Google OAuth & Gmail Setup

Gmail monitoring (reading confirmation emails) requires OAuth 2.0 credentials.

### Step-by-step

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., `autoapply-ai`)
3. Navigate to **APIs & Services → Library**
4. Enable **Gmail API**
5. Navigate to **APIs & Services → OAuth consent screen**
   - Choose **External** user type
   - Fill in app name, support email
   - Add scopes: `gmail.readonly`
   - Add your email as a test user
6. Navigate to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth 2.0 Client IDs**
   - Application type: **Web application**
   - Authorized redirect URIs: `http://localhost:5000/api/auth/gmail/callback`
   - Click **Create**
7. Copy **Client ID** → `GOOGLE_CLIENT_ID`
8. Copy **Client Secret** → `GOOGLE_CLIENT_SECRET`

### Testing locally

The OAuth flow starts at `GET /api/gmail/authorize` and completes at the callback URI. After authorization, tokens are encrypted with Fernet and stored in the database per user.

---

## Running the Services

### With Docker Compose

```bash
# Start all services
docker compose up

# Start in background
docker compose up -d

# View logs
docker compose logs -f app
docker compose logs -f worker

# Rebuild after dependency changes
docker compose up --build

# Run a one-off command (e.g., Flask CLI)
docker compose exec app flask db upgrade
docker compose exec app flask shell
```

### Without Docker

```bash
# Activate virtualenv first
source backend/.venv/bin/activate   # or .venv\Scripts\activate on Windows

# API server
cd backend && flask run --host=0.0.0.0 --port=5000

# Celery worker (new terminal, same venv)
cd backend && celery -A app.worker.celery_app worker --loglevel=info --concurrency=2

# Celery beat scheduler for periodic tasks like Gmail polling (new terminal)
cd backend && celery -A app.worker.celery_app beat --loglevel=info

# Flower task monitor (new terminal, optional)
cd backend && celery -A app.worker.celery_app flower --port=5555

# Frontend dev server (new terminal)
cd frontend && npm run dev
```

---

## Adding a New Platform Adapter

AutoApply AI uses a modular **adapter pattern** for job platforms. Each adapter is a Python class that knows how to navigate and fill forms on a specific site.

### Step 1: Create the adapter file

```bash
touch backend/app/platforms/my_platform.py
```

### Step 2: Implement the adapter class

```python
# backend/app/platforms/my_platform.py

from playwright.async_api import Page
from app.platforms.base import BasePlatformAdapter, ApplicationPayload, ApplicationResult


class MyPlatformAdapter(BasePlatformAdapter):
    """Adapter for MyPlatform job applications."""

    # The adapter is selected when the job URL matches this domain
    DOMAIN = "myplatform.com"
    NAME = "MyPlatform"

    async def is_supported(self, url: str) -> bool:
        """Return True if this adapter handles the given URL."""
        return self.DOMAIN in url

    async def apply(self, page: Page, payload: ApplicationPayload) -> ApplicationResult:
        """
        Navigate to the job page and submit the application.

        Args:
            page: An open Playwright Page already navigated to payload.job_url
            payload: Structured data including resume text, cover letter, user profile

        Returns:
            ApplicationResult with success flag, screenshot path, and message
        """
        try:
            # 1. Click the apply button
            await page.click("button:has-text('Apply')", timeout=10_000)

            # 2. Fill the form fields
            await page.fill("input[name='firstName']", payload.first_name)
            await page.fill("input[name='lastName']", payload.last_name)
            await page.fill("input[name='email']", payload.email)
            await page.fill("textarea[name='coverLetter']", payload.cover_letter)

            # 3. Upload resume
            async with page.expect_file_chooser() as fc_info:
                await page.click("button:has-text('Upload Resume')")
            file_chooser = await fc_info.value
            await file_chooser.set_files(payload.resume_path)

            # 4. Submit
            await page.click("button[type='submit']:has-text('Submit Application')")
            await page.wait_for_load_state("networkidle", timeout=15_000)

            # 5. Screenshot for proof
            screenshot_path = await self.take_screenshot(page, payload.application_id)

            return ApplicationResult(
                success=True,
                screenshot_path=screenshot_path,
                message="Application submitted successfully on MyPlatform",
            )

        except Exception as e:
            screenshot_path = await self.take_screenshot(page, payload.application_id)
            return ApplicationResult(
                success=False,
                screenshot_path=screenshot_path,
                message=f"Failed to apply on MyPlatform: {str(e)}",
                error=str(e),
            )
```

### Step 3: Register the adapter

Open `backend/app/platforms/__init__.py` and add your adapter to the registry:

```python
from app.platforms.my_platform import MyPlatformAdapter

PLATFORM_ADAPTERS = [
    LinkedInAdapter,
    IndeedAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    WorkdayAdapter,
    MyPlatformAdapter,   # ← Add here
]
```

The adapter selector in `app/worker/tasks.py` iterates `PLATFORM_ADAPTERS` and calls `is_supported(url)` to pick the right one at runtime. No other changes needed.

### Step 4: Write tests

```bash
# backend/tests/platforms/test_my_platform.py
```

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.platforms.my_platform import MyPlatformAdapter

@pytest.mark.asyncio
async def test_is_supported():
    adapter = MyPlatformAdapter()
    assert await adapter.is_supported("https://myplatform.com/jobs/123")
    assert not await adapter.is_supported("https://linkedin.com/jobs/123")

@pytest.mark.asyncio
async def test_apply_success(mock_page):
    adapter = MyPlatformAdapter()
    payload = MagicMock(
        first_name="Jane", last_name="Doe",
        email="jane@example.com", cover_letter="...",
        resume_path="/tmp/resume.pdf", application_id="test-123"
    )
    result = await adapter.apply(mock_page, payload)
    assert result.success
```

### Adapter Checklist

- [ ] Class inherits from `BasePlatformAdapter`
- [ ] `DOMAIN` and `NAME` class attributes set
- [ ] `is_supported()` implemented
- [ ] `apply()` returns `ApplicationResult`
- [ ] Screenshot taken on both success and failure
- [ ] Adapter registered in `PLATFORM_ADAPTERS`
- [ ] Tests written
- [ ] Tested against the live site in headful mode (`PLAYWRIGHT_HEADLESS=false`)

---

## API Endpoints Reference

All endpoints are prefixed with `/api`. Authentication uses JWT Bearer tokens.

### Auth — `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/register` | None | Create a new user account |
| `POST` | `/login` | None | Login, returns JWT access token |
| `POST` | `/logout` | JWT | Invalidate session |
| `GET` | `/me` | JWT | Get current user info |
| `POST` | `/refresh` | JWT | Refresh access token |

**Register request body:**
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123!",
  "full_name": "Jane Doe"
}
```

**Login response:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "user": { "id": 1, "email": "user@example.com", "full_name": "Jane Doe" }
}
```

---

### Profile — `/api/profile`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | JWT | Get user profile |
| `PUT` | `/` | JWT | Update profile fields |
| `POST` | `/resume` | JWT | Upload resume (PDF/DOCX) |
| `GET` | `/resume` | JWT | Get parsed resume data |
| `DELETE` | `/resume` | JWT | Remove resume |
| `POST` | `/credentials` | JWT | Store job portal credentials (encrypted) |
| `GET` | `/credentials` | JWT | List saved credential entries (masked) |
| `DELETE` | `/credentials/:id` | JWT | Delete a credential entry |

**Upload resume:** `multipart/form-data` with field `resume` (PDF or DOCX, max 16 MB).

---

### Applications — `/api/applications`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/submit` | JWT | Queue a new job application |
| `GET` | `/` | JWT | List all applications (paginated) |
| `GET` | `/:id` | JWT | Get single application details |
| `PATCH` | `/:id/status` | JWT | Manually update application status |
| `DELETE` | `/:id` | JWT | Delete application record |
| `GET` | `/:id/screenshot` | JWT | Download application screenshot |

**Submit request body:**
```json
{
  "job_url": "https://jobs.greenhouse.io/example/12345",
  "job_title": "Senior Software Engineer",
  "company_name": "Acme Corp",
  "job_description": "We are looking for...",
  "tailor_resume": true,
  "custom_cover_letter": null
}
```

**Application statuses:** `queued` → `processing` → `submitted` → `confirmed` / `failed`

---

### Dashboard — `/api/dashboard`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/stats` | JWT | Aggregate stats (total, by status, weekly trend) |
| `GET` | `/activity` | JWT | Recent activity feed |
| `GET` | `/platforms` | JWT | Applications grouped by platform |

**Stats response:**
```json
{
  "total": 47,
  "submitted": 38,
  "confirmed": 12,
  "failed": 5,
  "queued": 4,
  "today": 6,
  "this_week": 23,
  "response_rate": 31.6
}
```

---

### Gmail — `/api/gmail`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/authorize` | JWT | Start Gmail OAuth flow |
| `GET` | `/callback` | None | OAuth redirect callback |
| `GET` | `/status` | JWT | Check if Gmail is connected |
| `POST` | `/disconnect` | JWT | Revoke Gmail access |
| `POST` | `/sync` | JWT | Manually trigger inbox scan |

---

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Service health check |

---

## Troubleshooting

### `ModuleNotFoundError` on startup

Ensure your virtual environment is activated and dependencies are installed:
```bash
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

---

### Playwright `Error: Executable doesn't exist`

The Chromium browser binary was not installed. Run:
```bash
playwright install chromium
# On Linux, also run:
playwright install-deps chromium
```

In Docker, this is handled in the Dockerfile automatically.

---

### `FATAL: role "autoapply" does not exist`

The PostgreSQL user hasn't been created yet. Run:
```sql
psql -U postgres -c "CREATE USER autoapply WITH PASSWORD 'autoapply_pass';"
psql -U postgres -c "CREATE DATABASE autoapply_db OWNER autoapply;"
```

---

### `celery.exceptions.NotRegistered: app.worker.tasks.submit_application`

The Celery app can't find the task. Make sure:
1. `PYTHONPATH` includes the `backend/` directory
2. You're running Celery from `backend/`: `cd backend && celery -A app.worker.celery_app worker`

---

### `cryptography.fernet.InvalidToken`

This means data was encrypted with a different `FERNET_KEY` than the one currently in `.env`. Either:
- Restore the original key, or
- Clear the credential records in the database and re-enter them

---

### `google.auth.exceptions.TransportError` (Gmail)

Check that:
1. The Gmail API is enabled in your Google Cloud project
2. `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are correctly set
3. The redirect URI in Google Cloud Console **exactly** matches `GOOGLE_REDIRECT_URI` in `.env`

---

### Applications stuck in `queued` status

The Celery worker is not running or can't connect to Redis:
```bash
# Check Redis is running
redis-cli ping   # should return PONG

# Check worker logs
docker compose logs -f worker
# or locally:
celery -A app.worker.celery_app worker --loglevel=debug
```

---

### Rate limit errors from job platforms

If you're seeing CAPTCHAs or blocks:
1. Reduce `MAX_APPLICATIONS_PER_DAY` in `.env`
2. Add delays between applications in the Celery task
3. Set `PLAYWRIGHT_HEADLESS=false` to debug what the browser sees

---

### Docker port conflicts

If `5432` or `6379` are already in use locally:
```yaml
# In docker-compose.yml, change the HOST port (left side):
ports:
  - "5433:5432"   # Use 5433 locally instead
```

Update `DATABASE_URL` accordingly: `postgresql://autoapply:autoapply_pass@localhost:5433/autoapply_db`

---

## Project Structure

```
autoapply-ai/
├── .env.example              # Environment variable template
├── docker-compose.yml        # Multi-service Docker orchestration
├── README.md                 # This file
│
├── backend/
│   ├── Dockerfile            # Python 3.11 + Playwright image
│   ├── requirements.txt      # Python dependencies
│   ├── run.py                # App entry point
│   │
│   └── app/
│       ├── __init__.py       # Flask application factory
│       ├── config.py         # Configuration classes
│       │
│       ├── models/           # SQLAlchemy ORM models
│       │   ├── user.py
│       │   ├── profile.py
│       │   ├── application.py
│       │   └── credential.py
│       │
│       ├── api/              # Flask Blueprints (REST API)
│       │   ├── auth.py
│       │   ├── profile.py
│       │   ├── applications.py
│       │   ├── dashboard.py
│       │   └── gmail.py
│       │
│       ├── services/         # Business logic layer
│       │   ├── ai_service.py         # Gemini integration
│       │   ├── resume_parser.py      # PDF/DOCX parsing
│       │   ├── gmail_service.py      # Gmail OAuth + reading
│       │   └── encryption_service.py # Fernet encryption helpers
│       │
│       ├── platforms/        # Job platform adapters
│       │   ├── base.py               # Abstract base adapter
│       │   ├── __init__.py           # Adapter registry
│       │   ├── linkedin.py
│       │   ├── indeed.py
│       │   ├── greenhouse.py
│       │   ├── lever.py
│       │   └── workday.py
│       │
│       └── worker/           # Celery async tasks
│           ├── celery_app.py         # Celery instance
│           └── tasks.py              # Task definitions
│
├── frontend/                 # React + Vite UI
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── App.jsx
│       ├── pages/
│       └── components/
│
├── uploads/                  # User file storage (gitignored)
│   ├── resumes/
│   └── screenshots/
│
└── logs/                     # Application logs (gitignored)
```

---

## 🚀 LinkedIn Easy Apply & Persistent Browser Automation

AutoApply AI features a dedicated, production-grade **LinkedIn Easy Apply handler** using a **persistent Chrome profile**:

### 1. Persistent Browser Profile & Authentication
- **Zero Password Sharing:** You never need to enter your LinkedIn password into the website.
- **Dedicated Persistent Profile:** Playwright uses a persistent user data directory (`backend/browser_profiles/user_<id>/`) storing session cookies (`li_at`, `JSESSIONID`), cache, and local storage.
- **One-Click Manual Login:** In **Settings → LinkedIn Easy Apply & Browser Session**, click **"Connect LinkedIn"**. AutoApply AI launches a visible (headed) Chromium window where you can log in, solve 2FA/OTP or CAPTCHA. Once logged in, the session is saved and automatically reused across all subsequent applications.
- **Live Session Verification:** Test your session at any time with the **"Verify Session"** button.

### 2. End-to-End Easy Apply Workflow
When a LinkedIn job URL is provided:
1. **Session Check:** Verifies that your browser session is authenticated.
2. **Details Extraction:** Extracts the real job title, company name, location, and full job description from the DOM.
3. **Requirement & Skill Eligibility Matching:** Compares candidate skills, years of experience, and qualifications against the posting to calculate a compatibility score and matching skills breakdown.
4. **Already Applied Check:** Detects if you have already submitted to this job on LinkedIn and stops safely.
5. **Form Automation:** Clicks **Easy Apply** and navigates multi-step dialogs (contact information, resume selection/upload, work experience, education, and screening questions).
6. **Chatbot Missing Info Gate:** If an unknown required question appears, automation pauses and asks you conversationally via the floating chatbot.
7. **Pre-Submission Review & Approval Gate:** When reaching the final Review step, the system pauses, takes a screenshot of the filled review, and asks for your approval in the chatbot or dashboard before submitting.
8. **Receipt Verification:** Clicks Submit only upon approval and verifies post-submission confirmation signals before marking the job as **Applied – Verified**.

### 3. Application Lifecycle Statuses
AutoApply AI strictly enforces 6 verifiable lifecycle states:
- **Pending (`QUEUED`):** Application received and waiting in the worker queue.
- **In Progress (`APPLYING`):** Browser is running, filling forms, and navigating steps.
- **Submitted – Unverified (`SUBMITTED`):** Form was filled and submitted, but portal receipt was ambiguous.
- **Applied – Verified (`APPLIED`):** Application submission confirmed with verified portal receipt.
- **Failed (`FAILED`):** Non-retryable error such as closed/expired job posting.
- **Manual Intervention Required (`NEEDS_ACTION`):** Paused for user action (login, CAPTCHA, missing questions, or pre-submission review approval).

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-new-adapter`
3. Write tests: `pytest backend/tests/`
4. Commit with conventional commits: `feat: add MyPlatform adapter`
5. Open a pull request

---

## License

MIT License. See [LICENSE](LICENSE) for details.
