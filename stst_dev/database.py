"""SQLite database operations for STST Events."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import DATABASE_PATH, SOCIAL_MEDIA_TASK_TYPES
from .models import Event, SocialMediaTask

# SQL statements for table creation
CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_title TEXT NOT NULL,
    date TEXT NOT NULL,
    day_of_week TEXT,
    location TEXT,
    city TEXT,
    tags TEXT,
    is_dating BOOLEAN,
    sale_status TEXT,
    link TEXT UNIQUE,
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

            # Check if event already exists (by link)
            cursor.execute("SELECT id FROM events WHERE link = ?", (data["link"],))
            existing = cursor.fetchone()

            if existing:
                # Update existing event
                cursor.execute(
                    """
                    UPDATE events
                    SET full_title = ?, date = ?, day_of_week = ?, location = ?,
                        city = ?, tags = ?, is_dating = ?, sale_status = ?,
                        last_seen_at = ?
                    WHERE link = ?
                    """,
                    (
                        data["full_title"],
                        data["date"],
                        data["day_of_week"],
                        data["location"],
                        data["city"],
                        data["tags"],
                        data["is_dating"],
                        data["sale_status"],
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
                    (full_title, date, day_of_week, location, city, tags,
                     is_dating, sale_status, link, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data["full_title"],
                        data["date"],
                        data["day_of_week"],
                        data["location"],
                        data["city"],
                        data["tags"],
                        data["is_dating"],
                        data["sale_status"],
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
