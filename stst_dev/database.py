"""SQLite database operations for STST Events."""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from .config import (
    DATABASE_PATH,
    EVENT_TYPE_DEFAULT,
    EVENT_TYPE_MAP,
    SOCIAL_MEDIA_TASK_TYPES,
    VENUE_LOOKUP_PATH,
    CITY_STATE_LOOKUP_PATH,
)
from .models import Event, SocialMediaTask

logger = logging.getLogger(__name__)

# Cache for lookup tables
_venue_lookup_cache: Optional[dict[str, str]] = None
_city_state_lookup_cache: Optional[dict[str, str]] = None


def load_venue_lookup() -> dict[str, str]:
    """Load the venue-to-city lookup table from CSV.

    Returns:
        Dictionary mapping venue names to city names.
    """
    global _venue_lookup_cache
    if _venue_lookup_cache is not None:
        return _venue_lookup_cache

    _venue_lookup_cache = {}
    if VENUE_LOOKUP_PATH.exists():
        with open(VENUE_LOOKUP_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and "," in line:
                    # Split on last comma to handle venue names with commas
                    parts = line.rsplit(",", 1)
                    if len(parts) == 2:
                        venue, city = parts
                        _venue_lookup_cache[venue.strip()] = city.strip()
    return _venue_lookup_cache


def lookup_city(location: str) -> Optional[str]:
    """Look up the city for a given venue/location name.

    Args:
        location: Venue or location name from the event.

    Returns:
        City name if found in lookup table, None otherwise.
    """
    if not location:
        return None
    lookup = load_venue_lookup()
    return lookup.get(location)


def load_city_state_lookup() -> dict[str, str]:
    """Load the city-to-state lookup table from CSV.

    Returns:
        Dictionary mapping city names to state abbreviations.
    """
    global _city_state_lookup_cache
    if _city_state_lookup_cache is not None:
        return _city_state_lookup_cache

    _city_state_lookup_cache = {}
    if CITY_STATE_LOOKUP_PATH.exists():
        with open(CITY_STATE_LOOKUP_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line and "," in line:
                    parts = line.rsplit(",", 1)
                    if len(parts) == 2:
                        city, state = parts
                        _city_state_lookup_cache[city.strip()] = state.strip()
    return _city_state_lookup_cache


def lookup_state(city: str) -> Optional[str]:
    """Look up the state for a given city name.

    Args:
        city: City name (may include state disambiguator like "Portland (OR)").

    Returns:
        State abbreviation if found in lookup table, None otherwise.
    """
    if not city:
        return None
    lookup = load_city_state_lookup()
    return lookup.get(city)


def clean_city_name(city: str) -> str:
    """Remove state disambiguator from city name for display.

    Converts "Portland (OR)" to "Portland" while preserving the raw
    form in lookup tables for state resolution.

    Args:
        city: City name, possibly with state disambiguator.

    Returns:
        Clean city name without parenthetical suffix.
    """
    if not city:
        return city
    # Remove parenthetical suffix like " (OR)" or " (ME)"
    if " (" in city and city.endswith(")"):
        return city.rsplit(" (", 1)[0]
    return city


# SQL statements for table creation
CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_title TEXT NOT NULL,
    date TEXT NOT NULL,
    day_of_week TEXT,
    location TEXT,
    city TEXT,
    state TEXT,
    tags TEXT,
    is_dating BOOLEAN,
    sale_status TEXT,
    link TEXT UNIQUE,
    start_time TEXT,
    canva_posted BOOLEAN DEFAULT FALSE,
    venue_placeholder TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SOCIAL_MEDIA_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS social_media_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER REFERENCES events(id),
    task_type TEXT NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP,
    UNIQUE(event_id, task_type)
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_date ON events(date);",
    "CREATE INDEX IF NOT EXISTS idx_events_link ON events(link);",
    "CREATE INDEX IF NOT EXISTS idx_events_first_seen ON events(first_seen_at);",
    "CREATE INDEX IF NOT EXISTS idx_social_media_event_id ON social_media_tasks(event_id);",
]


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a database connection.

    Args:
        db_path: Path to the database file (defaults to DATABASE_PATH from config).

    Returns:
        SQLite connection with row factory set to dict-like access.
    """
    db_path = db_path or DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database with required tables.

    Args:
        db_path: Path to the database file.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(CREATE_EVENTS_TABLE)
        cursor.execute(CREATE_SOCIAL_MEDIA_TASKS_TABLE)
        for index_sql in CREATE_INDEXES:
            cursor.execute(index_sql)

        # Migrations: add columns if they don't exist
        cursor.execute("PRAGMA table_info(events)")
        columns = [row[1] for row in cursor.fetchall()]
        if "state" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN state TEXT")
        if "start_time" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN start_time TEXT")
        if "canva_posted" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN canva_posted BOOLEAN DEFAULT FALSE")
        if "venue_placeholder" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN venue_placeholder TEXT")

        conn.commit()
    finally:
        conn.close()


def upsert_events(events: list[Event], db_path: Optional[Path] = None) -> dict:
    """Insert or update events in the database.

    Uses the link field as a unique identifier. Updates existing events
    and inserts new ones.

    Args:
        events: List of Event objects to upsert.
        db_path: Path to the database file.

    Returns:
        Dictionary with counts: {'inserted': n, 'updated': n, 'total': n}
    """
    conn = get_connection(db_path)
    inserted = 0
    updated = 0

    try:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        for event in events:
            data = event.to_db_dict()

            # Look up city and state from venue if not already set
            if not data.get("city") and data.get("location"):
                raw_city = lookup_city(data["location"])
                if raw_city:
                    # Use raw city (with disambiguator) for state lookup
                    if not data.get("state"):
                        data["state"] = lookup_state(raw_city)
                    # Store clean city name (without disambiguator like "(OR)")
                    data["city"] = clean_city_name(raw_city)
            elif not data.get("state") and data.get("city"):
                # If city was already set, still try to look up state
                data["state"] = lookup_state(data["city"])

            # Check if event already exists (by link)
            cursor.execute("SELECT id FROM events WHERE link = ?", (data["link"],))
            existing = cursor.fetchone()

            if existing:
                # Update existing event
                cursor.execute(
                    """
                    UPDATE events
                    SET full_title = ?, date = ?, day_of_week = ?, location = ?,
                        city = ?, state = ?, tags = ?, is_dating = ?, sale_status = ?,
                        start_time = ?, last_seen_at = ?
                    WHERE link = ?
                    """,
                    (
                        data["full_title"],
                        data["date"],
                        data["day_of_week"],
                        data["location"],
                        data["city"],
                        data["state"],
                        data["tags"],
                        data["is_dating"],
                        data["sale_status"],
                        data.get("start_time"),
                        now,
                        data["link"],
                    ),
                )
                updated += 1
            else:
                # Insert new event
                cursor.execute(
                    """
                    INSERT INTO events
                    (full_title, date, day_of_week, location, city, state, tags,
                     is_dating, sale_status, start_time, link, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["full_title"],
                        data["date"],
                        data["day_of_week"],
                        data["location"],
                        data["city"],
                        data["state"],
                        data["tags"],
                        data["is_dating"],
                        data["sale_status"],
                        data.get("start_time"),
                        data["link"],
                        now,
                        now,
                    ),
                )
                inserted += 1

                # Create social media tasks for new events
                event_id = cursor.lastrowid
                for task_type in SOCIAL_MEDIA_TASK_TYPES:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO social_media_tasks (event_id, task_type)
                        VALUES (?, ?)
                        """,
                        (event_id, task_type),
                    )

        conn.commit()
    finally:
        conn.close()

    return {"inserted": inserted, "updated": updated, "total": len(events)}


def get_all_events(db_path: Optional[Path] = None) -> list[Event]:
    """Get all events from the database.

    Args:
        db_path: Path to the database file.

    Returns:
        List of Event objects.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY date")
        rows = cursor.fetchall()
        return [Event.from_db_row(dict(row)) for row in rows]
    finally:
        conn.close()


def get_upcoming_events(db_path: Optional[Path] = None) -> list[Event]:
    """Get upcoming events (date >= today).

    Args:
        db_path: Path to the database file.

    Returns:
        List of upcoming Event objects, sorted by date.
    """
    conn = get_connection(db_path)
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE date >= ? ORDER BY date", (today,)
        )
        rows = cursor.fetchall()
        return [Event.from_db_row(dict(row)) for row in rows]
    finally:
        conn.close()


def get_new_events(
    days: int = 7, db_path: Optional[Path] = None
) -> list[Event]:
    """Get events added within the specified number of days.

    Args:
        days: Number of days to look back.
        db_path: Path to the database file.

    Returns:
        List of recently added Event objects.
    """
    conn = get_connection(db_path)
    try:
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE first_seen_at >= ? ORDER BY first_seen_at DESC",
            (since,),
        )
        rows = cursor.fetchall()
        return [Event.from_db_row(dict(row)) for row in rows]
    finally:
        conn.close()


def get_events_with_sale_status(
    status: str, db_path: Optional[Path] = None
) -> list[Event]:
    """Get events with a specific sale status.

    Args:
        status: Sale status to filter by ('SALE' or 'SOLD_OUT').
        db_path: Path to the database file.

    Returns:
        List of Event objects with the specified sale status.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM events WHERE sale_status = ? ORDER BY date",
            (status,),
        )
        rows = cursor.fetchall()
        return [Event.from_db_row(dict(row)) for row in rows]
    finally:
        conn.close()


def get_social_media_tasks(
    event_id: int, db_path: Optional[Path] = None
) -> list[SocialMediaTask]:
    """Get social media tasks for an event.

    Args:
        event_id: ID of the event.
        db_path: Path to the database file.

    Returns:
        List of SocialMediaTask objects.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM social_media_tasks WHERE event_id = ?", (event_id,)
        )
        rows = cursor.fetchall()
        tasks = []
        for row in rows:
            tasks.append(
                SocialMediaTask(
                    id=row["id"],
                    event_id=row["event_id"],
                    task_type=row["task_type"],
                    completed=bool(row["completed"]),
                    completed_at=datetime.fromisoformat(row["completed_at"])
                    if row["completed_at"]
                    else None,
                )
            )
        return tasks
    finally:
        conn.close()


def mark_task_complete(
    event_id: int, task_type: str, completed: bool = True, db_path: Optional[Path] = None
) -> bool:
    """Mark a social media task as complete or incomplete.

    Args:
        event_id: ID of the event.
        task_type: Type of task (e.g., 'instagram', 'facebook').
        completed: Whether the task is completed.
        db_path: Path to the database file.

    Returns:
        True if the task was updated, False if not found.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        completed_at = datetime.now().isoformat() if completed else None
        cursor.execute(
            """
            UPDATE social_media_tasks
            SET completed = ?, completed_at = ?
            WHERE event_id = ? AND task_type = ?
            """,
            (completed, completed_at, event_id, task_type),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_canva_posted(
    event_id: int, posted: bool = True, db_path: Optional[Path] = None
) -> bool:
    """Mark an event as posted (or not) to Canva.

    Args:
        event_id: ID of the event.
        posted: Whether the event has been added to Canva.
        db_path: Path to the database file.

    Returns:
        True if the event was updated, False if not found.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET canva_posted = ? WHERE id = ?",
            (posted, event_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_events_with_incomplete_tasks(db_path: Optional[Path] = None) -> list[dict]:
    """Get events that have incomplete social media tasks.

    Args:
        db_path: Path to the database file.

    Returns:
        List of dicts with event data and incomplete task counts.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.*, COUNT(t.id) as incomplete_tasks
            FROM events e
            JOIN social_media_tasks t ON e.id = t.event_id
            WHERE t.completed = FALSE
            GROUP BY e.id
            ORDER BY e.date
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_event_count(db_path: Optional[Path] = None) -> int:
    """Get the total number of events in the database.

    Args:
        db_path: Path to the database file.

    Returns:
        Total event count.
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        return cursor.fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# v2 database functions (write to normalized schema from schema.sql)
# ---------------------------------------------------------------------------


def get_v2_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a v2 database connection with foreign keys enabled.

    Args:
        db_path: Path to the database file (defaults to DATABASE_PATH).

    Returns:
        SQLite connection with row factory and foreign keys ON.
    """
    db_path = db_path or DATABASE_PATH
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_venue_alias_lookup_v2(
    conn: sqlite3.Connection,
) -> dict[str, tuple[int, int]]:
    """Load venue alias → (venue_id, city_id) mapping from the database.

    Args:
        conn: Active database connection.

    Returns:
        Dict mapping alias string → (venue_id, city_id).
    """
    cur = conn.execute(
        """SELECT va.alias, va.venue_id, v.city_id
           FROM venue_alias va
           JOIN venue v USING (venue_id)"""
    )
    return {row["alias"]: (row["venue_id"], row["city_id"]) for row in cur}


def load_tag_lookup_v2(conn: sqlite3.Connection) -> dict[str, int]:
    """Load tag_name → tag_id mapping from the database.

    Args:
        conn: Active database connection.

    Returns:
        Dict mapping tag_name → tag_id.
    """
    cur = conn.execute("SELECT tag_id, tag_name FROM tag")
    return {row["tag_name"]: row["tag_id"] for row in cur}


def load_city_name_lookup_v2(conn: sqlite3.Connection) -> dict[str, int]:
    """Load lowercased city name → city_id mapping from the database.

    Indexes both city_name and website_city_name (where set), so scraped city
    strings match even when the website uses a different label than the canonical
    city name (e.g. "Edinburgh" on the website vs "Edinburgh (UK)" in the DB).

    Used as a fallback when a venue alias is not found.

    Args:
        conn: Active database connection.

    Returns:
        Dict mapping lowercase city name → city_id.
    """
    cur = conn.execute("SELECT city_id, city_name, website_city_name FROM city")
    result = {}
    for row in cur:
        result[row["city_name"].lower()] = row["city_id"]
        if row["website_city_name"]:
            result[row["website_city_name"].lower()] = row["city_id"]
    return result


def load_city_abbrev_lookup_v2(conn: sqlite3.Connection) -> dict[int, str]:
    """Load city_id → city_abbrev mapping from the database.

    Args:
        conn: Active database connection.

    Returns:
        Dict mapping city_id → city_abbrev.
    """
    cur = conn.execute("SELECT city_id, city_abbrev FROM city WHERE city_abbrev IS NOT NULL")
    return {row["city_id"]: row["city_abbrev"] for row in cur}


def _generate_utm_link(
    event_link: str, city_abbrev: str, event_date_iso: str, post_type: str
) -> str:
    """Generate a UTM-tagged link for an event.

    Args:
        event_link: Original event URL.
        city_abbrev: City abbreviation (e.g., "BOS").
        event_date_iso: Event date in ISO format (YYYY-MM-DD).
        post_type: One of "grid", "story_reminder", "story_dayof".

    Returns:
        URL with UTM parameters appended.
    """
    date_compact = event_date_iso.replace("-", "")
    utm_content = "story" if post_type.startswith("story") else "grid"
    params = {
        "utm_source": "instagram",
        "utm_medium": "social",
        "utm_content": utm_content,
        "utm_campaign": f"{city_abbrev}_{date_compact}_{post_type}",
    }

    parsed = urlparse(event_link)
    # Preserve any existing query params
    existing = parse_qs(parsed.query, keep_blank_values=True)
    existing.update(params)
    new_query = urlencode(existing, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _sync_event_tags(
    cursor: sqlite3.Cursor,
    event_id: int,
    scraped_tags: list[str],
    tag_lookup: dict[str, int],
    sold_out_tag_id: int | None,
) -> None:
    """Sync event_tag rows for an event (excluding sold_out, managed separately).

    Adds missing tags, removes stale ones.

    Args:
        cursor: Active database cursor.
        event_id: The event's ID.
        scraped_tags: Tag names from the scraper.
        tag_lookup: tag_name → tag_id mapping.
        sold_out_tag_id: tag_id for "sold out" (excluded from sync).
    """
    # Resolve scraped tag names → tag_ids
    desired_ids: set[int] = set()
    for tag_name in scraped_tags:
        tid = tag_lookup.get(tag_name)
        if tid is not None:
            desired_ids.add(tid)
        else:
            logger.debug(f"Unknown tag '{tag_name}' — skipping")

    # Current tags in DB (excluding sold_out)
    cursor.execute(
        "SELECT tag_id FROM event_tag WHERE event_id = ?", (event_id,)
    )
    current_ids = {row[0] for row in cursor.fetchall()}
    if sold_out_tag_id is not None:
        current_ids.discard(sold_out_tag_id)

    # Insert missing
    for tid in desired_ids - current_ids:
        cursor.execute(
            "INSERT OR IGNORE INTO event_tag (event_id, tag_id) VALUES (?, ?)",
            (event_id, tid),
        )

    # Remove stale
    for tid in current_ids - desired_ids:
        cursor.execute(
            "DELETE FROM event_tag WHERE event_id = ? AND tag_id = ?",
            (event_id, tid),
        )


def upsert_events_v2(
    events: list[Event], db_path: Optional[Path] = None
) -> dict:
    """Insert or update events into the v2 normalized schema.

    Args:
        events: List of scraped Event objects.
        db_path: Path to the database file.

    Returns:
        Summary dict with keys: inserted, updated, sold_out_changed,
        unknown_venues, skipped, total.
    """
    conn = get_v2_connection(db_path)
    venue_alias_lookup = load_venue_alias_lookup_v2(conn)
    tag_lookup = load_tag_lookup_v2(conn)
    city_name_lookup = load_city_name_lookup_v2(conn)
    sold_out_tag_id = tag_lookup.get("sold out")

    inserted = 0
    updated = 0
    sold_out_changed = 0
    unknown_venues: list[str] = []
    venues_created = 0
    skipped = 0

    try:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        for event in events:
            # --- 1. Resolve venue → (venue_id, city_id) ---
            venue_id: int | None = None
            city_id: int | None = None
            location = event.location or ""

            if location and location in venue_alias_lookup:
                venue_id, city_id = venue_alias_lookup[location]
            elif location:
                # Unknown venue — try to auto-create using city from metadata
                logger.warning(f"Unknown venue: '{location}' — attempting auto-create")

                # Try to resolve city_id from event.city (scraped from metadata)
                auto_city_id = None
                if event.city:
                    auto_city_id = city_name_lookup.get(event.city.lower())

                if auto_city_id is not None:
                    # Auto-create venue
                    cursor.execute(
                        """INSERT INTO venue (city_id, venue_name, notes)
                           VALUES (?, ?, 'auto-created')""",
                        (auto_city_id, location),
                    )
                    new_venue_id = cursor.lastrowid
                    # Auto-create alias
                    cursor.execute(
                        "INSERT INTO venue_alias (alias, venue_id) VALUES (?, ?)",
                        (location, new_venue_id),
                    )
                    # Update in-memory lookup so duplicates in this batch reuse it
                    venue_alias_lookup[location] = (new_venue_id, auto_city_id)
                    venue_id = new_venue_id
                    city_id = auto_city_id
                    venues_created += 1
                    logger.info(
                        f"Auto-created venue '{location}' (venue_id={new_venue_id}, "
                        f"city_id={auto_city_id})"
                    )
                else:
                    # city couldn't be resolved — venue skipped, event may be incomplete
                    unknown_venues.append(location)
                    logger.warning(
                        f"Could not resolve city for unknown venue '{location}' — skipping auto-create"
                    )

            # Special case: "Online" tag → use Online city
            if "Online" in event.tags:
                online_city_id = city_name_lookup.get("online")
                if online_city_id is not None:
                    city_id = online_city_id

            # City name fallback: try matching event.city against city_name_lookup
            if city_id is None and event.city:
                city_id = city_name_lookup.get(event.city.lower())

            if city_id is None:
                logger.error(
                    f"Cannot resolve city for event '{event.full_title}' "
                    f"(location='{location}') — skipping"
                )
                skipped += 1
                continue

            # --- 2. Normalize event_type ---
            event_type = EVENT_TYPE_MAP.get(
                event.event_type or "", EVENT_TYPE_DEFAULT
            )

            # --- 3. Determine sold_out ---
            sold_out = event.sale_status == "SOLD_OUT"

            # --- 4. Date ---
            event_date = event.date_iso or event.date

            # --- 5. Check existence ---
            cursor.execute(
                "SELECT event_id, sold_out FROM event WHERE event_link = ?",
                (event.link,),
            )
            existing = cursor.fetchone()

            if existing is None:
                # --- INSERT new event ---
                cursor.execute(
                    """INSERT INTO event
                       (city_id, venue_id, event_date, event_day_of_week,
                        event_start_time, event_type, event_link,
                        sold_out, is_dating, first_scraped_at, last_checked_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        city_id,
                        venue_id,
                        event_date,
                        event.day_of_week,
                        event.start_time,
                        event_type,
                        event.link,
                        sold_out,
                        event.is_dating,
                        now,
                        now,
                    ),
                )
                new_event_id = cursor.lastrowid

                # Insert event_tag rows
                for tag_name in event.tags:
                    tid = tag_lookup.get(tag_name)
                    if tid is not None:
                        cursor.execute(
                            "INSERT OR IGNORE INTO event_tag (event_id, tag_id) VALUES (?, ?)",
                            (new_event_id, tid),
                        )

                # If sold out, add "sold out" tag
                if sold_out and sold_out_tag_id is not None:
                    cursor.execute(
                        "INSERT OR IGNORE INTO event_tag (event_id, tag_id) VALUES (?, ?)",
                        (new_event_id, sold_out_tag_id),
                    )

                inserted += 1

            else:
                # --- UPDATE existing event ---
                existing_event_id = existing["event_id"]
                was_sold_out = bool(existing["sold_out"])

                update_fields = {
                    "city_id": city_id,
                    "venue_id": venue_id,
                    "event_date": event_date,
                    "event_day_of_week": event.day_of_week,
                    "event_start_time": event.start_time,
                    "event_type": event_type,
                    "sold_out": sold_out,
                    "is_dating": event.is_dating,
                    "last_checked_at": now,
                }
                # Don't overwrite manually-corrected DB values with NULL from scraper.
                # Booleans (sold_out, is_dating) and always-set fields are unaffected.
                update_fields = {k: v for k, v in update_fields.items() if v is not None}

                # If sold_out changed, also update status_changed_at
                if sold_out != was_sold_out:
                    update_fields["status_changed_at"] = now
                    sold_out_changed += 1

                    # Toggle sold_out tag
                    if sold_out and sold_out_tag_id is not None:
                        cursor.execute(
                            "INSERT OR IGNORE INTO event_tag (event_id, tag_id) VALUES (?, ?)",
                            (existing_event_id, sold_out_tag_id),
                        )
                    elif not sold_out and sold_out_tag_id is not None:
                        cursor.execute(
                            "DELETE FROM event_tag WHERE event_id = ? AND tag_id = ?",
                            (existing_event_id, sold_out_tag_id),
                        )

                set_clause = ", ".join(f"{k} = ?" for k in update_fields)
                values = list(update_fields.values()) + [event.link]
                cursor.execute(
                    f"UPDATE event SET {set_clause} WHERE event_link = ?",
                    values,
                )

                # Sync tags (excluding sold_out)
                _sync_event_tags(
                    cursor,
                    existing_event_id,
                    event.tags,
                    tag_lookup,
                    sold_out_tag_id,
                )

                updated += 1

        conn.commit()
    finally:
        conn.close()

    return {
        "inserted": inserted,
        "updated": updated,
        "sold_out_changed": sold_out_changed,
        "unknown_venues": unknown_venues,
        "venues_created": venues_created,
        "skipped": skipped,
        "total": len(events),
    }


def get_event_count_v2(db_path: Optional[Path] = None) -> int:
    """Get total event count from the v2 event table.

    Args:
        db_path: Path to the database file.

    Returns:
        Total event count.
    """
    conn = get_v2_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM event")
        return cursor.fetchone()[0]
    finally:
        conn.close()
