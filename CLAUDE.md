# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python application for scraping and managing event data from the Skip the Small Talk website. Tracks events, venues, facilitators, and social media marketing tasks in a local SQLite database (v2 normalized schema). Features a Streamlit dashboard for visualization and workflow management.

## Common Commands

All commands use [Taskfile](https://taskfile.dev/):

```bash
# Database
task seed              # Initialize database from schema.sql and seed_data.yaml (wipes existing data)
task seed-update       # Upsert cities/venues/facilitators/tags from seed_data.yaml (preserves event data)

# Scraper
task refresh           # Scrape website and update database
task refresh-debug     # Scrape with browser visible (debugging)

# Validation
task validate-new      # Review and validate newly scraped events (sets event.validated)

# Dashboard
task dashboard         # Launch Streamlit dashboard (default task)

# Dev
task test              # Run test suite (pytest)
task db                # Open SQLite database in interactive shell
task notebook          # Launch Jupyter notebook
task install-poetry    # Install Poetry virtual environment only
task clean             # Remove Python cache and notebook checkpoints
task teardown          # Delete virtual environment

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
│   ├── database.py              # SQLite operations (v1 and v2 functions)
│   ├── models.py                # Data models (Event)
│   └── config.py                # Configuration constants
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── scripts/
│   ├── refresh_events.py        # CLI: run scraper
│   ├── seed_db.py               # CLI: initialize database from scratch
│   ├── seed_update.py           # CLI: upsert lookup data without wiping events
│   ├── validate_new.py          # CLI: review and validate newly scraped events
│   └── validate_marketing.py    # CLI: confirm event details before marketing tasks
├── tests/
│   └── test_database_v2.py      # Tests for UTM generation and upsert_events_v2
├── data/
│   ├── seed_data.yaml           # Manually maintained: cities, venues, facilitators, tags
│   └── events.db                # SQLite database (gitignored)
├── schema.sql                   # v2 database DDL (source of truth for schema)
├── STST_DBv2_plan.md            # Architecture and build plan
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Taskfile.yml
```

### Key Components

- **scraper.py**: Uses Selenium with headless Chrome to scrape events from skipthesmalltalk.com. Extracts titles, dates, locations, tags, and ticket links. Calls `upsert_events_v2()`.

- **database.py**: SQLite operations. Contains both legacy v1 functions and the active v2 functions:
  - `get_v2_connection()` — connection with foreign keys enabled
  - `upsert_events_v2()` — insert/update events in the normalized schema
  - `load_venue_alias_lookup_v2()`, `load_tag_lookup_v2()`, `load_city_name_lookup_v2()` — in-memory lookup tables
  - `_generate_utm_link()` — builds UTM-tagged URLs for grid/story posts

- **seed_db.py / seed_update.py**: Read `data/seed_data.yaml` and populate the `city`, `venue`, `venue_alias`, `facilitator`, and `tag` tables.

- **validate_new.py**: Interactive CLI to review newly scraped events and set `event.validated = 1`.

- **dashboard/app.py**: Streamlit dashboard for viewing events and tracking marketing task completion.

### Database Schema (v2)

Seven tables. See `schema.sql` for full DDL. Summary:

- **`city`** — lookup: cities where STST operates. Includes `drive_folder_url` for Google Drive upload links.
- **`facilitator`** — lookup: one row per facilitator, linked to a city.
- **`venue`** — lookup: one row per venue, linked to a city.
- **`venue_alias`** — maps scraper location strings to canonical venue rows.
- **`event`** — core table, populated by scraper. Includes `validated`, ticket fields (`tickets_sold`, `ticket_threshold`, `num_attended`), and dating ticket fields.
- **`tag`** / **`event_tag`** — many-to-many tags (age group, affinity, status).

Key design decisions:
- `sold_out` is stored on `event` (fast queries) and also as a tag in `event_tag` (kept in sync by the scraper).
- `venue_alias` is the primary mechanism for resolving scraped location strings to `venue` and `city`.
- `city.website_city_name` handles cases where the STST website uses a broader city label (e.g., "Boston" for Cambridge/Somerville/Boston events).

## Dependencies

- Python 3.11+
- Poetry for package management
- Core: pandas, numpy
- Web scraping: selenium, webdriver-manager
- Dashboard: streamlit
- Database: sqlite3 (stdlib)
- Dev: pytest

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
