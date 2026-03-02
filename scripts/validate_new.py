"""Interactive CLI to review and validate newly scraped events.

Reviews events where event.validated = 0, prompts y/s/q per event.
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "events.db"


def validate_new(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run 'task seed' first.")
        return

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("""
        SELECT e.event_id, e.event_date, e.event_day_of_week, e.event_start_time,
               e.event_type, e.event_link, e.is_dating, e.sold_out,
               c.city_name, v.venue_name
        FROM event e
        JOIN city c ON e.city_id = c.city_id
        LEFT JOIN venue v ON e.venue_id = v.venue_id
        WHERE e.validated = 0
        ORDER BY e.event_date
    """)
    events = cur.fetchall()

    if not events:
        print("No unvalidated events.")
        con.close()
        return

    total = len(events)
    validated = skipped = 0

    print(f"\n{total} unvalidated event(s).")
    print("Commands: y = validate  s/Enter = skip  q = quit\n")

    for i, event in enumerate(events, 1):
        print(f"--- Event {i} of {total} ---")
        print(f"  Date:  {event['event_day_of_week']} {event['event_date']}"
              f"{' ' + event['event_start_time'] if event['event_start_time'] else ''}")
        print(f"  City:  {event['city_name']}")
        print(f"  Venue: {event['venue_name'] or '(unknown)'}")
        type_label = event['event_type'] or ('Dating' if event['is_dating'] else 'Regular')
        print(f"  Type:  {type_label}{'  [SOLD OUT]' if event['sold_out'] else ''}")
        print(f"  Link:  {event['event_link']}")

        try:
            choice = input("\n  Validate? [y/s/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if choice == "q":
            print("Quit.")
            break
        elif choice == "y":
            cur.execute("UPDATE event SET validated = 1 WHERE event_id = ?", (event["event_id"],))
            con.commit()
            validated += 1
            print("  Validated.")
        else:
            skipped += 1
            print("  Skipped.")
        print()

    con.close()
    remaining = total - validated - skipped
    print(f"Done. {validated} validated, {skipped} skipped, {remaining} remaining.")


def main():
    validate_new()


if __name__ == "__main__":
    main()
