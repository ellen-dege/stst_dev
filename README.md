# STST Events Scraper & Dashboard

A local Python tool for scraping and managing event data from the [Skip the Small Talk](https://www.skipthesmalltalk.com) website. Tracks events, venues, facilitators, and social media marketing tasks in a local SQLite database, with a Streamlit dashboard for visualization and workflow management.

## Requirements

- Python 3.11+
- [Poetry](https://python-poetry.org/) for dependency management
- [Taskfile](https://taskfile.dev/installation/) for task running
- Chrome/Chromium (for Selenium)

## Quick Start

```bash
# Install dependencies
task install-poetry

# Initialize database (first time only)
task seed

# Scrape events from website
task refresh

# Launch dashboard
task dashboard
```

Access the dashboard at `http://localhost:8501`

## Commands

```bash
# Database
task seed              # Initialize database from schema.sql and seed_data.yaml (wipes existing data)
task seed-update       # Upsert cities/venues/facilitators/tags from seed_data.yaml (preserves event data)

# Scraper
task refresh           # Scrape website and update database
task refresh-debug     # Scrape with browser visible (debugging)

# Validation
task validate-new      # Review and validate newly scraped events (sets event.validated)
task validate-marketing  # Confirm event details on site before marketing tasks (sets market_task.validated)

# Dashboard
task dashboard         # Launch Streamlit dashboard (default task)

# Dev
task db                # Open SQLite database in interactive shell
task notebook          # Launch Jupyter notebook
task clean             # Remove Python cache files
task teardown          # Delete virtual environment
```

### Docker

```bash
task docker-build   # Build Docker image
task docker-run     # Run dashboard in Docker
task docker-refresh # Run scraper in Docker
task docker-down    # Stop Docker containers
```

## Architecture

The system has three layers:

1. **`scraper.py`** — scrapes the STST website, upserts event records into SQLite, detects new events and sold-out status changes, auto-creates `market_task` rows for new events
2. **`output.py`** *(planned)* — queries the database and generates plain-text Canva lines and social media post content
3. **`dashboard/app.py`** *(in progress)* — local Streamlit dashboard for viewing events, tracking marketing task completion, and surfacing promotion priorities

## Project Structure

```
stst_dev/
├── stst_dev/                    # Python package
│   ├── __init__.py
│   ├── scraper.py               # Web scraper (Selenium)
│   ├── database.py              # SQLite operations
│   ├── models.py                # Data models
│   └── config.py                # Configuration constants
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── scripts/
│   ├── refresh_events.py        # CLI: run scraper
│   ├── seed_db.py               # CLI: initialize database from scratch
│   ├── seed_update.py           # CLI: upsert lookup table data without wiping events
│   ├── validate_new.py          # CLI: review and validate newly scraped events
│   └── validate_marketing.py    # CLI: confirm event details before marketing tasks
├── data/
│   ├── seed_data.yaml           # Manually maintained: cities, venues, facilitators, tags
│   └── events.db                # SQLite database (gitignored)
├── schema.sql                   # v2 database DDL
├── STST_DBv2_plan.md            # Architecture and build plan
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Taskfile.yml
```

## Database Schema

Seven tables. Lookup tables (`city`, `venue`, `facilitator`, `tag`) are seeded from `seed_data.yaml`. Event data is populated by the scraper.

```mermaid
erDiagram
    city ||--o{ venue : "has"
    city ||--o{ facilitator : "has"
    city ||--o{ event : "hosts"
    venue ||--o{ venue_alias : "has"
    venue ||--o{ event : "hosts"
    facilitator ||--o{ event : "runs"
    event ||--|| market_task : "has"
    event ||--o{ event_tag : "tagged with"
    tag ||--o{ event_tag : "applied to"

    city {
        int city_id PK
        text city_name
        text city_abbrev
        text state
        text country
        text region
        text time_zone
        bool has_dedicated_ig
        text ig_handle
        text website_city_name "label used on STST website (e.g. Boston for Cambridge/Somerville)"
    }

    facilitator {
        int facilitator_id PK
        int city_id FK
        text facilitator_name
        text facilitator_email_1
        text facilitator_email_2
        text ig_handle
        bool tag_on_ig
        bool is_active
    }

    venue {
        int venue_id PK
        int city_id FK
        text venue_name
        text venue_ig_handle_1
        text venue_ig_handle_2
        text venue_website
        text venue_address
        text venue_fb_name
        text venue_contact_emails "semicolon-separated"
        text notes
    }

    venue_alias {
        text alias PK
        int venue_id FK
    }

    event {
        int event_id PK
        int city_id FK
        int venue_id FK
        int facilitator_id FK
        date event_date
        text event_day_of_week
        time event_start_time
        text event_type
        text event_link UK
        bool sold_out
        bool is_dating
        bool validated "set via task validate-new"
        int tickets_sold
        int ticket_threshold
        int num_attended
        int man_tix
        int woman_tix
        int man_tix_understudy
        int woman_tix_understudy
        datetime first_scraped_at
        datetime last_checked_at
        datetime status_changed_at
    }

    market_task {
        int market_task_id PK
        int event_id FK
        bool validated "confirm details on site before marketing; set via task validate-marketing"
        bool weekly_graphic_created
        bool standalone_graphic_created
        bool added_to_biweekly_upcoming
        bool grid_post_scheduled
        bool venue_collab_sent
        bool venue_collab_accepted
        bool story_postlive
        bool story_reminder
        bool story_dayof
        bool extra_promo_pushed
        bool meetup_RSVPs
        bool on_venue_site
        bool on_venue_socials
        bool photo_link_sent
        text utm_link_grid
        text utm_link_story_reminder
        text utm_link_story_dayof
        text notes
        datetime last_updated_at
    }

    tag {
        int tag_id PK
        text tag_name UK
        text tag_category
    }

    event_tag {
        int event_tag_id PK
        int event_id FK
        int tag_id FK
    }
```

### City/Website Name Mapping

The STST website uses broader city labels that don't always match actual city names. `city.website_city_name` stores the label used on the website when it differs from `city.city_name`. The scraper resolves city via venue lookup first (`venue_alias` → `venue` → `city`), using `website_city_name` as a fallback.

| city_name | website_city_name |
|---|---|
| Cambridge | Boston |
| Somerville | Boston |
| New Haven | Connecticut |
| New London | Connecticut |

## Seed Data

`data/seed_data.yaml` is the source of truth for manually maintained lookup data. Edit it to add cities, venues, facilitators, or tags, then run:

```bash
task seed-update   # Safe to run against a live database — preserves all event data
task seed          # Full rebuild — wipes and recreates everything (use for schema changes)
```

## Google Sheets / Ticket Sync (planned)

A `ticket_sync.py` script will sync ticket sales and attendance data from the team's Google Sheet into the `event` table (`tickets_sold`, `ticket_threshold`, `num_attended`). See `STST_DBv2_plan.md` for details.

### Future: Publish to Google Sheets

A `task publish` command could export a read-only view of the database to a shared Google Sheet for broader team access, with tabs such as:

- **Upcoming Events** — validated upcoming events with date, city, venue, facilitator, type, tags, link, and sold-out status
- **Marketing Tasks** — a working copy of upcoming events with the full marketing task checklist as columns (filled in independently of the DB)
- **Newsletter Updates** — events grouped by region or recently added, for drafting newsletter content

This would use a service account for authentication (credentials gitignored) and could be triggered manually or automatically after `task refresh`.

## Build Status

Per `STST_DBv2_plan.md`:

- [x] Define schema and write DDL
- [x] Seed lookup tables (city, venue, facilitator, tag)
- [ ] Build and test scraper v2 (UTM link generation, market_task auto-creation)
- [ ] Build and test ticket_sync.py
- [ ] Build and test output.py
- [ ] Streamlit dashboard v2

## Security

This repository is intended for public release. See `CLAUDE.md` for full security guidelines. Never commit:
- API keys, tokens, or credentials
- `.env` files
- `data/*.db` files (already gitignored)

## License

MIT
