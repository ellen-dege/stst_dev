"""Data models for STST Events."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class Event:
    """Represents a Skip the Small Talk event."""

    full_title: str
    date: str  # Raw date string from website (e.g., "Monday, August 25, 2025")
    location: str
    tags: list[str] = field(default_factory=list)
    is_dating: bool = False
    sale_status: Optional[str] = None  # 'SALE', 'SOLD_OUT', or None
    link: str = ""
    city: Optional[str] = None
    day_of_week: Optional[str] = None

    # Database fields (set when loaded from DB)
    id: Optional[int] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    def __post_init__(self):
        """Parse date components after initialization."""
        if self.date and not self.day_of_week:
            self._parse_date_components()

    def _parse_date_components(self):
        """Extract day of week from the date string."""
        if "," in self.date:
            parts = self.date.split(",")
            if len(parts) >= 1:
                self.day_of_week = parts[0].strip()

    @property
    def parsed_date(self) -> Optional[datetime]:
        """Parse the date string into a datetime object."""
        try:
            # Handle format: "Monday, August 25, 2025"
            if "," in self.date:
                # Remove day of week and parse
                date_parts = self.date.split(", ", 1)
                if len(date_parts) > 1:
                    date_str = date_parts[1]
                else:
                    date_str = self.date
                return datetime.strptime(date_str, "%B %d, %Y")
            # Handle format: "October 29, 2025" (no day of week)
            return datetime.strptime(self.date, "%B %d, %Y")
        except ValueError:
            return None

    @property
    def date_iso(self) -> Optional[str]:
        """Return the date in ISO format (YYYY-MM-DD)."""
        parsed = self.parsed_date
        return parsed.strftime("%Y-%m-%d") if parsed else None

    @property
    def tags_json(self) -> str:
        """Return tags as JSON string for database storage."""
        return json.dumps(self.tags)

    @classmethod
    def from_db_row(cls, row: dict) -> "Event":
        """Create an Event from a database row dictionary."""
        tags = json.loads(row.get("tags", "[]")) if row.get("tags") else []
        return cls(
            id=row.get("id"),
            full_title=row.get("full_title", ""),
            date=row.get("date", ""),
            day_of_week=row.get("day_of_week"),
            location=row.get("location", ""),
            city=row.get("city"),
            tags=tags,
            is_dating=bool(row.get("is_dating", False)),
            sale_status=row.get("sale_status"),
            link=row.get("link", ""),
            first_seen_at=datetime.fromisoformat(row["first_seen_at"])
            if row.get("first_seen_at")
            else None,
            last_seen_at=datetime.fromisoformat(row["last_seen_at"])
            if row.get("last_seen_at")
            else None,
        )

    def to_db_dict(self) -> dict:
        """Convert Event to dictionary for database insertion."""
        return {
            "full_title": self.full_title,
            "date": self.date_iso or self.date,
            "day_of_week": self.day_of_week,
            "location": self.location,
            "city": self.city,
            "tags": self.tags_json,
            "is_dating": self.is_dating,
            "sale_status": self.sale_status,
            "link": self.link,
        }


@dataclass
class SocialMediaTask:
    """Represents a social media task for an event."""

    event_id: int
    task_type: str
    completed: bool = False
    completed_at: Optional[datetime] = None
    id: Optional[int] = None
