# Skip the Small Talk — Event Database: Build Plan

## Overview

This document captures the architecture and design decisions for a local SQLite database tool to manage Skip the Small Talk event instances, track social media marketing tasks, and generate plain-text output for use in Canva assets and Meta Business Suite post scheduling.

The system has three layers:

1. **`scraper.py`** — scrapes the STST website, upserts event records into SQLite, detects new events and sold-out status changes
2. **`output.py`** — queries the database and generates plain-text checklists and Canva-ready text lines
3. **`streamlit_app.py`** *(future)* — local browser-based dashboard for viewing events, flagging changes, and toggling task completion

---

## Database Schema

Seven tables in total. All table and column names use the singular and snake_case.

### `city`
Lookup table for cities where STST operates. Manually populated.

| Column | Type | Notes |
|---|---|---|
| city_id | INTEGER PK | |
| city_name | TEXT | |
| state | TEXT | |
| country | TEXT | |
| region | TEXT | Matches newsletter regional groupings |
| time_zone | TEXT | IANA format, e.g. "America/Denver"; used for scheduling posts at correct local time |
| has_dedicated_ig | BOOLEAN | Drives template selection in output.py |
| ig_handle | TEXT | City-level IG handle if applicable |

### `facilitator`
One row per facilitator. A city may have multiple facilitators over time.

| Column | Type | Notes |
|---|---|---|
| facilitator_id | INTEGER PK | |
| city_id | INTEGER FK | References city |
| facilitator_name | TEXT | |
| facilitator_email | TEXT | |
| ig_handle | TEXT | |
| tag_on_ig | BOOLEAN | Whether to tag facilitator in social posts |

### `venue`
One row per venue. Cities may have multiple venues.

| Column | Type | Notes |
|---|---|---|
| venue_id | INTEGER PK | |
| city_id | INTEGER FK | References city |
| venue_name | TEXT | |
| venue_ig_handle_1 | TEXT | |
| venue_ig_handle_2 | TEXT | At most two handles |
| venue_events_site | TEXT | |
| venue_address | TEXT | |
| notes | TEXT | e.g. "only use photos taken at this venue" |

### `event`
Core table. One row per event instance. Populated and updated by the scraper.

| Column | Type | Notes |
|---|---|---|
| event_id | INTEGER PK | |
| city_id | INTEGER FK | References city |
| venue_id | INTEGER FK | References venue |
| facilitator_id | INTEGER FK | References facilitator |
| event_date | DATE | |
| event_day_of_week | TEXT | Scraped explicitly, e.g. "Saturday" |
| event_start_time | TIME | |
| event_type | TEXT | e.g. "Regular", "Dating" |
| event_link | TEXT | URL to event page on STST website |
| sold_out | BOOLEAN | Redundant with tag; kept for fast querying |
| is_dating | BOOLEAN | If TRUE, join to event_tag for age/affinity groupings |
| tickets_sold | INTEGER | Synced weekly from team's Google Sheet tracker |
| ticket_threshold | INTEGER | Number of tickets at which event is considered healthy; varies by venue capacity. Used for promotion prioritization and cancellation early warning queries |
| num_attended | INTEGER | Updated post-event from Google Sheet tracker |
| man_tix | INTEGER | Dating events only; NULL otherwise |
| woman_tix | INTEGER | Dating events only; NULL otherwise |
| man_tix_understudy | INTEGER | Dating events only; NULL otherwise |
| woman_tix_understudy | INTEGER | Dating events only; NULL otherwise |
| first_scraped_at | DATETIME | Set on insert, never updated |
| last_checked_at | DATETIME | Updated on every scraper run |
| status_changed_at | DATETIME | Updated only when sold_out flips |

### `market_task`
One row per event, created automatically when the scraper inserts a new event. Tracks completion of social media marketing tasks across the full promotion touchpoint cadence.

| Column | Type | Notes |
|---|---|---|
| market_task_id | INTEGER PK | |
| event_id | INTEGER FK | References event; 1:1 relationship |
| graphic_created | BOOLEAN | Canva asset created and exported |
| grid_post_scheduled | BOOLEAN | Grid post scheduled 10-14 days before event on local account (or Main if no local) |
| venue_collab_sent | BOOLEAN | Collaboration invite sent to venue on IG |
| venue_collab_accepted | BOOLEAN | Venue accepted the collab post |
| story_postlive | BOOLEAN | Story shared when grid post goes live (~10-14 days out) |
| story_reminder | BOOLEAN | Reminder story with ticketing link (3-5 days before event) |
| story_dayof | BOOLEAN | Day-of story with ticketing link |
| extra_promo_pushed | BOOLEAN | Additional promotion for events below ticket threshold |
| photo_link_sent | BOOLEAN | |
| utm_link_grid | TEXT | Generated UTM link for grid post |
| utm_link_story_reminder | TEXT | Generated UTM link for 3-5 day reminder story |
| utm_link_story_dayof | TEXT | Generated UTM link for day-of story |
| notes | TEXT | Freeform field for edge cases |
| last_updated_at | DATETIME | |

### `tag`
Lookup table of all possible tags. Manually populated and extended as needed.

| Column | Type | Notes |
|---|---|---|
| tag_id | INTEGER PK | |
| tag_name | TEXT | e.g. "ages 25-35", "queer", "sold out" |
| tag_category | TEXT | e.g. "age_group", "affinity", "status" |

### `event_tag`
Junction table for the many-to-many relationship between events and tags. The scraper inserts a sold-out tag row here when it detects a status change; other tags are applied manually or via future automation.

| Column | Type | Notes |
|---|---|---|
| event_tag_id | INTEGER PK | |
| event_id | INTEGER FK | References event |
| tag_id | INTEGER FK | References tag |

---

## Key Design Decisions

**`sold_out` is stored redundantly.** It exists as a BOOLEAN on `event` for fast querying and alerting, and also as a tag in `event_tag` for consistency with the tagging system. The scraper is responsible for keeping both in sync.

**`is_dating` as a fast-path filter.** Rather than joining through `event_tag` to determine event type for every query, `is_dating` on `event` lets output scripts quickly branch on template logic. Tag joins for age/affinity groupings only happen when `is_dating = TRUE`.

**Dating ticket fields are nullable.** `man_tix`, `woman_tix`, `man_tix_understudy`, and `woman_tix_understudy` will be NULL for non-dating events. No separate table needed.

**State and country are not denormalized onto `event`.** The `city` table is small (dozens of rows at most) and the join is trivial. Output scripts should join through `city` to retrieve state and country.

**UTM links are generated externally.** The `market_task` table and in-code UTM generation (`_generate_utm_link`) have been removed. UTM links are now produced in Google Sheets from a DB export. The `loc_abbrev` field on `city` (metro-area label concordant with `website_city_name`) is the intended campaign prefix if UTM generation is ever brought back into code.

**Ticket data comes from a separate Google Sheet, not the scraper.** The team maintains a Google Sheet tracking tickets sold per event. This data is synced into `event.tickets_sold` weekly — either via a Sheets API pull script or manual export/import. `ticket_threshold` is set per event based on venue capacity (could default from a future field on `venue` if thresholds are consistent per venue). `num_attended` is updated post-event from the same Sheet. The scraper handles event discovery and sold-out detection; ticket sales tracking is a separate data flow.

---

## Scripts

### `scraper.py`
- Scrapes the STST website for event listings
- Upserts into `event`: inserts new events, updates `last_checked_at` on all
- Detects sold-out status changes: updates `sold_out` on `event`, updates `status_changed_at`, inserts/removes corresponding row in `event_tag`
- Auto-creates a `market_task` row for each newly inserted event
- Prints a summary on each run: new events found, events newly sold out

### `output.py`
- Queries upcoming events with their city, venue, facilitator, and market_task details
- Selects the appropriate template based on `city.has_dedicated_ig` and `event.is_dating`
- Generates plain-text Canva lines (e.g. `7:00pm · Trident Books · Boston, MA`)
- Generates social media task checklists as unformatted text for copy-paste into Meta Business Suite
- Generates story content blocks for each touchpoint (post-live, reminder, day-of) with the correct UTM link, venue IG handle for tagging, and facilitator handle if `tag_on_ig` is TRUE
- For dating events: joins `event_tag` to include age/affinity group information
- **Ticket-driven queries:**
  - Events in the next 7 days where `tickets_sold < ticket_threshold` → priority promotion list
  - Events more than 5 days out with fewer than 6 tickets sold → cancellation early warning
  - Events within 3 days with `tickets_sold < 10` → cancellation decision queue
  - Events in cities without local accounts (`has_dedicated_ig = FALSE`) in the next 7 days → Main-account story coverage list

### `streamlit_app.py` *(future)*
- Local browser dashboard (runs on your machine, no hosting required)
- Table view of upcoming events with sold-out flags highlighted
- **Ticket sales dashboard:** color-coded flags for events below `ticket_threshold` (yellow) and events on cancellation watch (red); sortable by days-until-event and tickets-sold to surface the most urgent items
- **Cancellation watch list:** filtered view of events trending toward the 10-12 ticket cancellation threshold, with days remaining and current ticket count
- **Promotion coverage view:** shows each upcoming event's `market_task` status — which touchpoints are complete, which are pending — so you can see at a glance what still needs scheduling
- New-since-last-run alerts
- Toggle buttons to update `market_task` boolean fields
- Trigger to run output.py for a selected event
- **Post-event analytics view** *(future)*: compare promotion coverage (market_task completeness) against actual attendance for completed events to identify which touchpoints correlate with higher turnout

---

## Build Order

1. Define schema and write DDL (Claude Code)
2. Manually populate `city` (including region and time_zone), `facilitator`, `venue`, and `tag` tables
3. Build and test `scraper.py` (including UTM link generation and market_task auto-creation)
4. Build and test `ticket_sync.py` (Google Sheet integration for ticket sales and attendance)
5. Build and test `output.py` (including story content blocks, UTM links, and ticket-driven queries)
6. Add Streamlit dashboard when core scripts are stable (including ticket sales views, promotion coverage, calendar view)
7. Add Google Calendar API sync
8. *(Optional future)* Automate scraper and ticket sync to run on a daily/weekly schedule via GitHub Actions or a lightweight cloud instance
