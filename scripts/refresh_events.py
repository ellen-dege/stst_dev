#!/usr/bin/env python3
"""CLI script to refresh events from the STST website."""

import argparse
import logging
import sys

from stst_dev.database import get_event_count_v2, upsert_events_v2
from stst_dev.scraper import ScraperError, scrape_events


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    """Main entry point for the refresh script.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    parser = argparse.ArgumentParser(
        description="Refresh STST events from the website"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run Chrome with GUI (for debugging)",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Get current event count for comparison
        count_before = get_event_count_v2()

        # Scrape events
        logger.info("Scraping events from website...")
        events = scrape_events(headless=not args.no_headless)

        if not events:
            logger.warning("No events scraped from website")
            return 1

        # Upsert events to v2 database
        logger.info(f"Saving {len(events)} events to database...")
        result = upsert_events_v2(events)

        # Get final count
        count_after = get_event_count_v2()

        # Print summary
        print("\n" + "=" * 50)
        print("REFRESH COMPLETE")
        print("=" * 50)
        print(f"Total events scraped:    {result['total']}")
        print(f"New events added:        {result['inserted']}")
        print(f"Existing events updated: {result['updated']}")
        print(f"Sold-out status changed: {result['sold_out_changed']}")
        print(f"Venues auto-created:     {result['venues_created']}")
        print(f"Skipped (no city):       {result['skipped']}")
        print(f"Total events in DB:      {count_after}")
        print("=" * 50)

        # Unresolved venues (no alias match, city unknown — NOT inserted into DB)
        if result["unknown_venues"]:
            print(f"\nUnresolved venues — add aliases to fix ({len(set(result['unknown_venues']))}):")
            for v in sorted(set(result["unknown_venues"])):
                print(f"  - {v}")

        # Summary of sale statuses
        sale_events = [e for e in events if e.sale_status == "SALE"]
        sold_out_events = [e for e in events if e.sale_status == "SOLD_OUT"]
        if sale_events:
            print(f"\nEvents on SALE: {len(sale_events)}")
        if sold_out_events:
            print(f"SOLD OUT events: {len(sold_out_events)}")

        return 0

    except ScraperError as e:
        logger.error(f"Scraping failed: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
