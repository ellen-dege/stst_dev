# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python application for scraping and managing event data from the Skip the Small Talk website. Features a Streamlit dashboard for visualization and task management, with SQLite for data persistence.

## Common Commands

All commands use [Taskfile](https://taskfile.dev/):

```bash
# Main workflow
task dashboard      # Launch Streamlit dashboard (default task)
task refresh        # Scrape website and update database
task refresh-debug  # Scrape with browser visible (debugging)

# Development
task notebook       # Launch Jupyter notebook
task install-poetry # Install Poetry virtual environment only
task clean          # Remove Python cache and notebook checkpoints
task teardown       # Delete virtual environment

# Docker
task docker-build   # Build Docker image
task docker-run     # Run dashboard in Docker
task docker-refresh # Run scraper in Docker
task docker-down    # Stop Docker containers
```

## Architecture

```
stst_dev/
├── stst_dev/                    # Python package
│   ├── __init__.py
│   ├── scraper.py               # Web scraper (Selenium)
│   ├── database.py              # SQLite operations
│   ├── models.py                # Data models (Event, SocialMediaTask)
│   └── config.py                # Configuration constants
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── scripts/
│   └── refresh_events.py        # CLI script to run scraper
├── notebooks/                   # Jupyter notebooks (legacy)
├── data/
│   └── events.db                # SQLite database (gitignored)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Taskfile.yml
```

### Key Components

- **scraper.py**: Uses Selenium with headless Chrome to scrape events from skipthesmalltalk.com. Extracts titles, dates, locations, tags, and ticket links.

- **database.py**: SQLite operations including:
  - `init_db()` - Create tables
  - `upsert_events()` - Insert/update events, track new additions
  - `get_upcoming_events()` - Filter future events
  - `get_new_events(days)` - Events added recently
  - `mark_task_complete()` - Social media checklist management

- **dashboard/app.py**: Streamlit dashboard with pages for:
  - Upcoming Events (filterable by location, tags, dating)
  - Newly Added Events
  - Sale Status (events on sale or sold out)
  - Social Media Checklist (per-event task tracking)
  - Statistics

### Database Schema

```sql
-- Main events table
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    full_title TEXT, date TEXT, day_of_week TEXT,
    location TEXT, city TEXT, tags TEXT (JSON),
    is_dating BOOLEAN, sale_status TEXT, link TEXT UNIQUE,
    first_seen_at TIMESTAMP, last_seen_at TIMESTAMP
);

-- Social media task tracking
CREATE TABLE social_media_tasks (
    id INTEGER PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    task_type TEXT, completed BOOLEAN, completed_at TIMESTAMP
);
```

## Dependencies

- Python 3.11+
- Poetry for package management
- Core: pandas, numpy, matplotlib, seaborn
- Web scraping: selenium, webdriver-manager
- Dashboard: streamlit
- Database: sqlite3 (stdlib)

## Docker Usage

```bash
# Build and run dashboard
docker-compose up --build

# Run scraper manually
docker-compose run --rm scraper

# Access dashboard at http://localhost:8501
```

## Security Guidelines

**This repository is intended for public release.** Follow these guidelines to avoid exposing credentials:

### Never Commit
- API keys, tokens, or secrets
- `.env` files or environment variable files
- `credentials.json`, `secrets.json`, or service account files
- Database files containing personal data (`*.db`)
- Private keys (`*.pem`, `*.key`)

### Already Gitignored
The `.gitignore` excludes sensitive files. Before committing, verify with:
```bash
git status --ignored
```

### Environment Variables
If adding features that require credentials (e.g., Google Sheets API):
1. Use environment variables, not hardcoded values
2. Document required env vars in README (without actual values)
3. Use `.env.example` as a template (with placeholder values only)

### Before Publishing
1. Review git history: `git log --all --full-history -- "*.json" "*.env"`
2. Check for hardcoded URLs with personal info
3. Ensure `data/` directory is empty or gitignored
4. **Clear notebook outputs** - they may contain personal Google Sheets URLs or other data

To clear all notebook outputs:
```bash
# Install nbstripout (one-time)
pip install nbstripout

# Strip outputs from all notebooks
find notebooks -name "*.ipynb" -exec nbstripout {} \;
```

### Current Security Status
- No API keys or credentials in codebase
- Database files are gitignored
- Draft notebooks are gitignored
- All scraping is from public website (no auth required)
