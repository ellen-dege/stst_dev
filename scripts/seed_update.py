"""Update the v2 database from seed_data.yaml without wiping existing event data.

Upserts cities, venues, venue_aliases, facilitators, and tags.
Existing event rows are never touched.
"""

import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "data" / "seed_data.yaml"
DB_PATH = ROOT / "data" / "events.db"


def seed_update(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run 'task seed' first.")
        return

    with open(SEED_PATH) as f:
        data = yaml.safe_load(f)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    city_insert = city_update = 0
    venue_insert = venue_update = 0
    alias_insert = 0
    facilitator_insert = facilitator_update = 0
    tag_insert = tag_update = 0

    # --- Cities, Venues & Facilitators ---
    for city in data["cities"]:
        cur.execute("SELECT city_id FROM city WHERE city_name = ?", (city["city_name"],))
        row = cur.fetchone()
        if row:
            city_id = row["city_id"]
            cur.execute(
                """UPDATE city SET city_abbrev=?, state=?, country=?, region=?,
                   time_zone=?, has_dedicated_ig=?, ig_handle=?, website_city_name=?
                   WHERE city_id=?""",
                (
                    city.get("city_abbrev"),
                    city.get("state"),
                    city.get("country", "US"),
                    city.get("region"),
                    city.get("time_zone"),
                    city.get("has_dedicated_ig", False),
                    city.get("ig_handle"),
                    city.get("website_city_name"),
                    city_id,
                ),
            )
            city_update += 1
        else:
            cur.execute(
                """INSERT INTO city
                   (city_name, city_abbrev, state, country, region, time_zone,
                    has_dedicated_ig, ig_handle, website_city_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    city["city_name"],
                    city.get("city_abbrev"),
                    city.get("state"),
                    city.get("country", "US"),
                    city.get("region"),
                    city.get("time_zone"),
                    city.get("has_dedicated_ig", False),
                    city.get("ig_handle"),
                    city.get("website_city_name"),
                ),
            )
            city_id = cur.lastrowid
            city_insert += 1

        for venue in city.get("venues", []):
            cur.execute(
                "SELECT venue_id FROM venue WHERE city_id=? AND venue_name=?",
                (city_id, venue["venue_name"]),
            )
            row = cur.fetchone()
            if row:
                venue_id = row["venue_id"]
                cur.execute(
                    """UPDATE venue SET venue_ig_handle_1=?, venue_ig_handle_2=?,
                       venue_events_site=?, venue_address=?, venue_fb_name=?,
                       venue_contact_emails=?, venue_TT=?, notes=?
                       WHERE venue_id=?""",
                    (
                        venue.get("venue_ig_handle_1"),
                        venue.get("venue_ig_handle_2"),
                        venue.get("venue_events_site"),
                        venue.get("venue_address"),
                        venue.get("venue_fb_name"),
                        venue.get("venue_contact_emails"),
                        venue.get("venue_TT"),
                        venue.get("notes"),
                        venue_id,
                    ),
                )
                venue_update += 1
            else:
                cur.execute(
                    """INSERT INTO venue
                       (city_id, venue_name, venue_ig_handle_1, venue_ig_handle_2,
                        venue_events_site, venue_address, venue_fb_name, venue_contact_emails, venue_TT, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        city_id,
                        venue["venue_name"],
                        venue.get("venue_ig_handle_1"),
                        venue.get("venue_ig_handle_2"),
                        venue.get("venue_events_site"),
                        venue.get("venue_address"),
                        venue.get("venue_fb_name"),
                        venue.get("venue_contact_emails"),
                        venue.get("venue_TT"),
                        venue.get("notes"),
                    ),
                )
                venue_id = cur.lastrowid
                venue_insert += 1

            # Aliases: insert new ones, never remove existing ones
            aliases = venue.get("aliases", [venue["venue_name"]])
            if venue["venue_name"] not in aliases:
                aliases.append(venue["venue_name"])
            for alias in aliases:
                cur.execute(
                    "INSERT OR IGNORE INTO venue_alias (alias, venue_id) VALUES (?, ?)",
                    (alias, venue_id),
                )
                if cur.rowcount > 0:
                    alias_insert += 1

        for facilitator in city.get("facilitators", []):
            cur.execute(
                "SELECT facilitator_id FROM facilitator WHERE city_id=? AND facilitator_name=?",
                (city_id, facilitator["facilitator_name"]),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """UPDATE facilitator SET facilitator_email_1=?, facilitator_email_2=?,
                       ig_handle=?, tag_on_ig=?, is_active=?
                       WHERE facilitator_id=?""",
                    (
                        facilitator.get("facilitator_email_1"),
                        facilitator.get("facilitator_email_2"),
                        facilitator.get("ig_handle"),
                        facilitator.get("tag_on_ig", False),
                        facilitator.get("is_active", True),
                        row["facilitator_id"],
                    ),
                )
                facilitator_update += 1
            else:
                cur.execute(
                    """INSERT INTO facilitator
                       (city_id, facilitator_name, facilitator_email_1, facilitator_email_2,
                        ig_handle, tag_on_ig, is_active)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        city_id,
                        facilitator["facilitator_name"],
                        facilitator.get("facilitator_email_1"),
                        facilitator.get("facilitator_email_2"),
                        facilitator.get("ig_handle"),
                        facilitator.get("tag_on_ig", False),
                        facilitator.get("is_active", True),
                    ),
                )
                facilitator_insert += 1

    # --- Tags ---
    for tag in data.get("tags", []):
        cur.execute("SELECT tag_id FROM tag WHERE tag_name=?", (tag["tag_name"],))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE tag SET tag_category=? WHERE tag_name=?",
                (tag.get("tag_category"), tag["tag_name"]),
            )
            tag_update += 1
        else:
            cur.execute(
                "INSERT INTO tag (tag_name, tag_category) VALUES (?, ?)",
                (tag["tag_name"], tag.get("tag_category")),
            )
            tag_insert += 1

    con.commit()
    con.close()

    print(f"Updated {db_path}:")
    print(f"  cities:        {city_insert} inserted, {city_update} updated")
    print(f"  venues:        {venue_insert} inserted, {venue_update} updated")
    print(f"  venue_aliases: {alias_insert} inserted")
    print(f"  facilitators:  {facilitator_insert} inserted, {facilitator_update} updated")
    print(f"  tags:          {tag_insert} inserted, {tag_update} updated")


def main():
    seed_update()


if __name__ == "__main__":
    main()
