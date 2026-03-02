"""Seed the v2 database from schema.sql and data/seed_data.yaml."""

import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.sql"
SEED_PATH = ROOT / "data" / "seed_data.yaml"
DB_PATH = ROOT / "data" / "events.db"


def seed(db_path: Path = DB_PATH) -> None:
    # Read inputs
    schema_sql = SCHEMA_PATH.read_text()
    with open(SEED_PATH) as f:
        data = yaml.safe_load(f)

    # Create database and tables
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(schema_sql)

    cur = con.cursor()

    # --- Cities & Venues ---
    city_count = 0
    venue_count = 0
    alias_count = 0

    for city in data["cities"]:
        cur.execute(
            """INSERT INTO city
               (city_name, city_abbrev, state, country, region, time_zone,
                has_dedicated_ig, ig_handle)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                city["city_name"],
                city.get("city_abbrev"),
                city.get("state"),
                city.get("country", "US"),
                city.get("region"),
                city.get("time_zone"),
                city.get("has_dedicated_ig", False),
                city.get("ig_handle"),
            ),
        )
        city_id = cur.lastrowid
        city_count += 1

        for venue in city.get("venues", []):
            cur.execute(
                """INSERT INTO venue
                   (city_id, venue_name, venue_ig_handle_1, venue_ig_handle_2,
                    venue_website, venue_address, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    city_id,
                    venue["venue_name"],
                    venue.get("venue_ig_handle_1"),
                    venue.get("venue_ig_handle_2"),
                    venue.get("venue_website"),
                    venue.get("venue_address"),
                    venue.get("notes"),
                ),
            )
            venue_id = cur.lastrowid
            venue_count += 1

            # Build alias list: explicit aliases, or just the canonical name
            aliases = venue.get("aliases", [venue["venue_name"]])
            # Always include the canonical name as an alias
            if venue["venue_name"] not in aliases:
                aliases.append(venue["venue_name"])

            for alias in aliases:
                cur.execute(
                    "INSERT INTO venue_alias (alias, venue_id) VALUES (?, ?)",
                    (alias, venue_id),
                )
                alias_count += 1

    # --- Tags ---
    tag_count = 0
    for tag in data.get("tags", []):
        cur.execute(
            "INSERT INTO tag (tag_name, tag_category) VALUES (?, ?)",
            (tag["tag_name"], tag.get("tag_category")),
        )
        tag_count += 1

    con.commit()
    con.close()

    print(f"Seeded {db_path}:")
    print(f"  cities:        {city_count}")
    print(f"  venues:        {venue_count}")
    print(f"  venue_aliases: {alias_count}")
    print(f"  tags:          {tag_count}")


def main():
    if DB_PATH.exists():
        print(f"Removing existing database: {DB_PATH}")
        DB_PATH.unlink()
    seed()


if __name__ == "__main__":
    main()
