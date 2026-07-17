"""Tests for v2 database functions: upsert_events_v2."""

import sqlite3
from pathlib import Path

import pytest

from stst_dev.database import upsert_events_v2
from stst_dev.models import Event

SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def make_db(tmp_path: Path) -> Path:
    """Create a minimal seeded v2 database for testing."""
    db_path = tmp_path / "test_events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())

    conn.execute(
        "INSERT INTO city (city_id, city_name, loc_abbrev, state, country, has_dedicated_ig)"
        " VALUES (1, 'Denver', 'DEN', 'CO', 'US', 1)"
    )
    conn.execute(
        "INSERT INTO venue (venue_id, city_id, venue_name)"
        " VALUES (1, 1, 'Town Hall Collaborative')"
    )
    conn.execute(
        "INSERT INTO venue_alias (alias, venue_id)"
        " VALUES ('Town Hall Collaborative', 1)"
    )
    conn.execute("INSERT INTO tag (tag_id, tag_name, tag_category) VALUES (1, 'sold out', 'status')")
    conn.execute("INSERT INTO tag (tag_id, tag_name, tag_category) VALUES (2, '20s', 'age_group')")
    conn.commit()
    conn.close()
    return db_path


def make_event(**kwargs) -> Event:
    """Return a minimal valid Event for Denver / Town Hall Collaborative."""
    defaults = dict(
        full_title="Skip the Small Talk Denver",
        date="Saturday, April 5, 2025",
        location="Town Hall Collaborative",
        tags=[],
        is_dating=False,
        sale_status=None,
        link="https://www.skipthesmalltalk.com/events/den-20250405",
        city="Denver",
    )
    defaults.update(kwargs)
    return Event(**defaults)


# ---------------------------------------------------------------------------
# upsert_events_v2 — new event insert
# ---------------------------------------------------------------------------

class TestUpsertEventsV2Insert:
    def test_inserts_event_row(self, tmp_path):
        db = make_db(tmp_path)
        result = upsert_events_v2([make_event()], db_path=db)
        assert result["inserted"] == 1
        assert result["updated"] == 0

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM event").fetchone()
        assert row["event_link"] == "https://www.skipthesmalltalk.com/events/den-20250405"
        assert row["city_id"] == 1
        assert row["venue_id"] == 1
        assert not bool(row["sold_out"])
        conn.close()



# ---------------------------------------------------------------------------
# upsert_events_v2 — sold-out handling
# ---------------------------------------------------------------------------

class TestUpsertEventsV2SoldOut:
    def test_sold_out_flag_set(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event(sale_status="SOLD_OUT")], db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT sold_out FROM event").fetchone()
        assert bool(row[0])
        conn.close()

    def test_sold_out_tag_added(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event(sale_status="SOLD_OUT")], db_path=db)

        conn = sqlite3.connect(str(db))
        count = conn.execute(
            "SELECT COUNT(*) FROM event_tag et JOIN tag t USING(tag_id)"
            " WHERE t.tag_name = 'sold out'"
        ).fetchone()[0]
        assert count == 1
        conn.close()

    def test_sold_out_flip_sets_status_changed_at(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event()], db_path=db)
        result = upsert_events_v2([make_event(sale_status="SOLD_OUT")], db_path=db)
        assert result["sold_out_changed"] == 1

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT status_changed_at FROM event").fetchone()
        assert row[0] is not None
        conn.close()

    def test_sold_out_recovery_clears_flag_and_tag(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event(sale_status="SOLD_OUT")], db_path=db)
        upsert_events_v2([make_event(sale_status=None)], db_path=db)

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT sold_out FROM event").fetchone()
        assert not bool(row[0])
        count = conn.execute(
            "SELECT COUNT(*) FROM event_tag et JOIN tag t USING(tag_id)"
            " WHERE t.tag_name = 'sold out'"
        ).fetchone()[0]
        assert count == 0
        conn.close()


# ---------------------------------------------------------------------------
# upsert_events_v2 — city resolution fallbacks
# ---------------------------------------------------------------------------

class TestUpsertEventsV2CityResolution:
    def test_city_fallback_via_event_city_field(self, tmp_path):
        """When venue alias is unknown, city resolves from event.city."""
        db = make_db(tmp_path)
        event = make_event(
            location="Some New Venue",
            city="Denver",
            link="https://www.skipthesmalltalk.com/events/den-fallback",
        )
        result = upsert_events_v2([event], db_path=db)
        assert result["inserted"] == 1

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT city_id FROM event").fetchone()
        assert row[0] == 1
        conn.close()

    def test_skipped_when_city_unresolvable(self, tmp_path):
        db = make_db(tmp_path)
        event = make_event(
            location="Mystery Venue",
            city=None,
            link="https://www.skipthesmalltalk.com/events/unknown",
        )
        result = upsert_events_v2([event], db_path=db)
        assert result["skipped"] == 1
        assert result["inserted"] == 0


# ---------------------------------------------------------------------------
# upsert_events_v2 — batch behaviour
# ---------------------------------------------------------------------------

class TestUpsertEventsV2Batch:
    def test_multiple_events_batch_insert(self, tmp_path):
        db = make_db(tmp_path)
        events = [
            make_event(
                full_title=f"Event {i}",
                link=f"https://www.skipthesmalltalk.com/events/den-{i}",
            )
            for i in range(3)
        ]
        result = upsert_events_v2(events, db_path=db)
        assert result["inserted"] == 3
        assert result["total"] == 3

        conn = sqlite3.connect(str(db))
        event_count = conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        assert event_count == 3
        conn.close()
