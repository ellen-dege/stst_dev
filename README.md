# STST Events Scraper & Dashboard

A Python application for scraping and managing event data from the [Skip the Small Talk](https://www.skipthesmalltalk.com) website. Features a Streamlit dashboard for visualization and task management.

## Features

- Web scraper using Selenium to extract event data
- SQLite database for persistent storage
- Streamlit dashboard with:
  - Upcoming events (filterable by location, tags, dating)
  - Newly added events
  - Sale status tracking (on sale / sold out)
  - Social media checklist per event
- Google Sheets integration for ticket/attendance data (TODO)
- Docker support for portable deployment

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management
- [Taskfile](https://taskfile.dev/installation/) for task running
- Chrome/Chromium (for Selenium)

## Quick Start

```bash
# Install dependencies
task install-poetry

# Scrape events from website
task refresh

# Launch dashboard (default task)
task dashboard
```

Access the dashboard at `http://localhost:8501`

## Commands

```bash
task dashboard      # Launch Streamlit dashboard
task refresh        # Scrape website and update database
task refresh-debug  # Scrape with browser visible (debugging)
task notebook       # Launch Jupyter notebook
task clean          # Remove cache files
task teardown       # Delete virtual environment
```

### Docker

```bash
task docker-build   # Build Docker image
task docker-run     # Run dashboard in Docker
task docker-refresh # Run scraper in Docker
```

## Streamlit Cloud Deployment (TODO)

For team access without running locally, deploy to [Streamlit Community Cloud](https://streamlit.io/cloud) (free):

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click "New app" and select:
   - Repository: `your-username/stst_dev`
   - Branch: `main`
   - Main file path: `dashboard/app.py`
4. Click "Deploy"

### Optional: Add Authentication

To restrict access to team members, add to `dashboard/app.py`:

```python
import streamlit as st

# Simple password protection
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        password = st.text_input("Password", type="password")
        if password == st.secrets["password"]:
            st.session_state.authenticated = True
            st.rerun()
        elif password:
            st.error("Incorrect password")
        st.stop()

check_password()
```

Then add a `.streamlit/secrets.toml` file (gitignored):
```toml
password = "your-team-password"
```

In Streamlit Cloud, add the secret via the app settings.

## Google Sheets Integration (TODO)

The dashboard integrates with a Google Sheet containing ticket/attendance data from Squarespace. This provides:

- Ticket counts (Man/Woman/Understudy)
- Links to attendance Google Docs
- Canceled event detection (via strikethrough formatting)
- Notes from guest lists

### Setup Google Cloud Service Account

1. **Create a Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project (e.g., "stst-dashboard")
   - Note the project ID

2. **Enable the Google Sheets API**
   - In the Cloud Console, go to "APIs & Services" → "Library"
   - Search for "Google Sheets API" and enable it
   - Also enable "Google Drive API" (needed for access)

3. **Create a Service Account**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Name it (e.g., "stst-sheets-reader")
   - Skip optional permissions, click "Done"

4. **Generate a Key**
   - Click on your new service account
   - Go to "Keys" tab → "Add Key" → "Create new key"
   - Choose JSON format, download the file
   - **Keep this file secure — never commit it to git**

5. **Share the Sheet with the Service Account**
   - Open your Google Sheet
   - Click "Share"
   - Add the service account email (looks like `name@project-id.iam.gserviceaccount.com`)
   - Give it "Viewer" access (read-only)

### Local Development Setup

Option A: Environment variable (recommended)
```bash
# Add to your shell profile or .env file
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
```

Option B: File path
```bash
# Save the JSON file outside the repo, reference by path
export GOOGLE_SERVICE_ACCOUNT_FILE='/path/to/credentials.json'
```

Also set the Sheet ID:
```bash
# The Sheet ID is in the URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit
export STST_ATTENDANCE_SHEET_ID='your-sheet-id-here'
```

### Streamlit Cloud Setup

In Streamlit Cloud, add secrets via the app settings:

```toml
# .streamlit/secrets.toml (local) or Streamlit Cloud secrets UI

[google]
sheet_id = "your-sheet-id-here"

[google.service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "name@project-id.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
# ... rest of service account JSON fields
```

### Dependencies

When implementing, add to `pyproject.toml`:
```bash
poetry add gspread google-auth
```

### Data Mapping

| Sheet Column | Description |
|--------------|-------------|
| Event Names | Matches `events.full_title` |
| Event Date | Event date |
| Attendee Counts | Total ticket count |
| Man Tix / Woman Tix | Gendered ticket counts |
| Man (Understudy) / Woman (Understudy) | Understudy counts |
| URL | Link to attendance Google Doc |
| City (from Guest List) | City |
| Notes (from Guest List) | Notes |

Strikethrough formatting on a row indicates a canceled event.

## Database Schema

```mermaid
erDiagram
    events ||--o{ social_media_tasks : "has"

    events {
        int id PK
        text full_title
        text date
        text day_of_week
        text location
        text city
        text tags "JSON array"
        bool is_dating
        text sale_status "SALE, SOLD_OUT, or NULL"
        text link UK
        timestamp first_seen_at
        timestamp last_seen_at
    }

    social_media_tasks {
        int id PK
        int event_id FK
        text task_type "instagram, facebook, etc."
        bool completed
        timestamp completed_at
    }
```

## Project Structure

```
stst_dev/
├── stst_dev/                    # Python package
│   ├── config.py                # Configuration constants
│   ├── models.py                # Data models (Event, SocialMediaTask)
│   ├── scraper.py               # Web scraper (Selenium)
│   └── database.py              # SQLite operations
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── scripts/
│   └── refresh_events.py        # CLI script to run scraper
├── data/
│   └── events.db                # SQLite database (gitignored)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Taskfile.yml
```

## License

MIT
