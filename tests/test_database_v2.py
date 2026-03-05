"""Tests for v2 database functions: UTM link generation and upsert_events_v2."""

import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from stst_dev.database import _generate_utm_link, upsert_events_v2
from stst_dev.models import Event

SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def make_db(tmp_path: Path) -> Path:
    """Create a minimal seeded v2 database for testing."""
    db_path = tmp_path / "test_events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())

    conn.execute(
        "INSERT INTO city (city_id, city_name, city_abbrev, state, country, has_dedicated_ig)"
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
# _generate_utm_link
# ---------------------------------------------------------------------------

class TestGenerateUtmLink:
    def test_params_present(self):
        url = _generate_utm_link("https://example.com/event", "DEN", "2025-04-05", "grid")
        qs = parse_qs(urlparse(url).query)
        assert qs["utm_source"] == ["instagram"]
        assert qs["utm_medium"] == ["social"]
        assert qs["utm_content"] == ["grid"]
        assert qs["utm_campaign"] == ["DEN_20250405_grid"]

    def test_story_content_tag(self):
        url = _generate_utm_link("https://example.com/event", "BOS", "2025-06-01", "story_reminder")
        qs = parse_qs(urlparse(url).query)
        assert qs["utm_content"] == ["story"]
        assert qs["utm_campaign"] == ["BOS_20250601_story_reminder"]

    def test_dayof_story_content_tag(self):
        url = _generate_utm_link("https://example.com/event", "NYC", "2025-09-15", "story_dayof")
        qs = parse_qs(urlparse(url).query)
        assert qs["utm_content"] == ["story"]

    def test_existing_query_params_preserved(self):
        url = _generate_utm_link(
            "https://example.com/event?ref=homepage", "DEN", "2025-04-05", "grid"
        )
        qs = parse_qs(urlparse(url).query)
        assert "ref" in qs
        assert qs["utm_source"] == ["instagram"]


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

    def test_creates_market_task_row(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event()], db_path=db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        mt = conn.execute("SELECT * FROM market_task").fetchone()
        assert mt is not None
        assert not bool(mt["validated"])
        conn.close()

    def test_market_task_has_utm_links(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event()], db_path=db)

        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        mt = conn.execute("SELECT * FROM market_task").fetchone()
        assert "utm_source=instagram" in mt["utm_link_grid"]
        assert "utm_source=instagram" in mt["utm_link_story_reminder"]
        assert "utm_source=instagram" in mt["utm_link_story_dayof"]
        conn.close()

    def test_utm_campaign_contains_city_and_date(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event()], db_path=db)

        conn = sqlite3.connect(str(db))
        mt = conn.execute("SELECT utm_link_grid FROM market_task").fetchone()
        assert "DEN" in mt[0]
        assert "20250405" in mt[0]
        conn.close()

    def test_no_duplicate_market_task_on_re_upsert(self, tmp_path):
        db = make_db(tmp_path)
        upsert_events_v2([make_event()], db_path=db)
        result = upsert_events_v2([make_event()], db_path=db)
        assert result["updated"] == 1

        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM market_task").fetchone()[0]
        assert count == 1
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
    def test_multiple_events_each_get_market_task(self, tmp_path):
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
        task_count = conn.execute("SELECT COUNT(*) FROM market_task").fetchone()[0]
        assert event_count == 3
        assert task_count == 3
        conn.close()
