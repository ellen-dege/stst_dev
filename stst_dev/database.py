"""SQLite database operations for STST Events."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import DATABASE_PATH, SOCIAL_MEDIA_TASK_TYPES, VENUE_LOOKUP_PATH, CITY_STATE_LOOKUP_PATH
from .models import Event, SocialMediaTask

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
