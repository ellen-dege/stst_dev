# STST Dev — To-Do

## Priority 1: Fix seed_data.yaml update mechanics
- `drive_folder_url` is in the schema but never written by `seed_update.py` — add it to the city upsert block
- Renaming a venue or facilitator in the YAML inserts a new row instead of updating the existing one (name-only matching is fragile)
- Decide on stable key strategy (e.g. optional `seed_id` field in YAML entries)

## Priority 2: Connect facilitator table to event table
- `event.facilitator_id` exists in the schema but is never populated — `upsert_events_v2()` omits it entirely
- Facilitator names aren't scraped from the website, so assignment needs another source
- Design decision needed — pick one:
  - (a) Auto-assign from city when only one active facilitator
  - (b) Add facilitator selection step to `validate_new.py` CLI
  - (c) Add facilitator assignment UI to the Streamlit dashboard

## UTM links
- UTM generation is handled in Google Sheets from a DB export, not in code
- `_generate_utm_link()` and its tests were removed; `load_loc_abbrev_lookup_v2()` is retained for potential future use
- If UTM generation is ever brought back into code, use `loc_abbrev` as the campaign prefix (metro-area label matching `website_city_name`)

## Priority 3: Auto-run the scraper on a schedule
- Set up scheduled execution of `task refresh` (macOS: launchd plist or cron)
- Decide on frequency (daily?), working directory, and failure notification behavior
