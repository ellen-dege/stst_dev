"""Web scraper for Skip the Small Talk events."""

import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .config import (
    CHROME_OPTIONS,
    CSS_SELECTORS,
    DATING_INDICATORS,
    SALE_OPTIONS,
    SELENIUM_TIMEOUT,
    TAG_OPTIONS,
    TARGET_URL,
)
from .models import Event

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Custom exception for scraper errors."""

    pass


def get_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    """Create and configure a Chrome WebDriver instance.

    Args:
        headless: Whether to run Chrome in headless mode.

    Returns:
        Configured Chrome WebDriver instance.
    """
    options = Options()

    if headless:
        for opt in CHROME_OPTIONS:
            options.add_argument(opt)

    # Use webdriver-manager to automatically download/manage ChromeDriver
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _clean_metadata_text(text: str) -> str:
    """Clean up metadata text with SALE/SOLD OUT prefixes.

    Args:
        text: Raw text that may contain newlines from SALE/SOLD OUT badges.

    Returns:
        Cleaned text with normalized whitespace.
    """
    if "\n" in text:
        n_count = text.count("\n")
        extras = "\n" * n_count
        text = text.replace(extras, " ")
    return text.strip()


def _parse_event_metadata(text: str) -> dict:
    """Parse event metadata from a title string.

    Args:
        text: Event title string (e.g., "Skip the Small Talk at Aeronaut: Monday, August 25, 2025")

    Returns:
        Dictionary with parsed event components.
    """
    full_title = text

    # Get date from after the colon (present in all strings)
    date = ""
    if ": " in text:
        date = text.rsplit(": ", 1)[1]
    elif ":" in text:
        date = text.rsplit(":", 1)[1].strip()

    # Extract location (text between "at " and ": ")
    location = ""
    if " at " in text:
        location_part = text.split(" at ", 1)[1]
        if ": " in location_part:
            location = location_part.split(": ", 1)[0]
        else:
            location = location_part

    # Extract tags
    tags = []
    for tag in TAG_OPTIONS:
        if tag in text:
            # Normalize tag to standard form
            normalized_tag = tag.capitalize() if tag.islower() else tag
            if normalized_tag not in tags:
                tags.append(normalized_tag)

    # Check if dating event
    is_dating = any(d in text for d in DATING_INDICATORS)

    # Check sale status
    sale_status = None
    text_lower = text.lower()
    if "sold out" in text_lower:
        sale_status = "SOLD_OUT"
    elif "sale" in text_lower:
        sale_status = "SALE"

    return {
        "full_title": full_title,
        "date": date,
        "location": location,
        "tags": tags,
        "is_dating": is_dating,
        "sale_status": sale_status,
    }


def scrape_events(
    url: Optional[str] = None, headless: bool = True, timeout: int = SELENIUM_TIMEOUT
) -> list[Event]:
    """Scrape events from the Skip the Small Talk website.

    Args:
        url: URL to scrape (defaults to TARGET_URL from config).
        headless: Whether to run Chrome in headless mode.
        timeout: Timeout in seconds for page load.

    Returns:
        List of Event objects.

    Raises:
        ScraperError: If scraping fails.
    """
    url = url or TARGET_URL
    driver = None

    try:
        logger.info(f"Starting scrape of {url}")
        driver = get_chrome_driver(headless=headless)

        # Load the page
        driver.get(url)

        # Wait for the body to load
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )

        # Find event elements
        event_elements = driver.find_elements(
            By.CLASS_NAME, CSS_SELECTORS["event_title_links"]
        )
        metadata_elements = driver.find_elements(
            By.CLASS_NAME, CSS_SELECTORS["event_metadata"]
        )

        logger.info(f"Found {len(event_elements)} event elements")
        logger.info(f"Found {len(metadata_elements)} metadata elements")

        # Extract titles and links (filtering out empty entries)
        active_events = []
        for elem in event_elements:
            title = elem.text.strip()
            link = elem.get_attribute("href")
            if title:  # Only include events with non-empty titles
                active_events.append((title, link))

        # Extract metadata (filtering out empty entries)
        metadata_list = [_clean_metadata_text(elem.text) for elem in metadata_elements]
        metadata_list = [m for m in metadata_list if m]

        logger.info(f"Extracted {len(active_events)} active events")
        logger.info(f"Extracted {len(metadata_list)} metadata entries")

        # Build Event objects
        # The metadata has SALE/SOLD OUT prefixes, while titles from links don't
        # We'll use metadata for parsing but link titles for the actual title
        events = []

        for i, (title, link) in enumerate(active_events):
            # Try to find matching metadata (which has sale status)
            metadata_text = None
            for meta in metadata_list:
                # Check if this metadata matches this event (by comparing date portion)
                if ": " in title and ": " in meta:
                    title_date = title.rsplit(": ", 1)[1]
                    meta_date = meta.rsplit(": ", 1)[1]
                    if title_date == meta_date and (
                        title.split(": ")[0] in meta or meta.split(": ")[0] in title
                    ):
                        metadata_text = meta
                        break

            # Parse from the metadata if found, otherwise from the title
            text_to_parse = metadata_text if metadata_text else title
            parsed = _parse_event_metadata(text_to_parse)

            # Use the clean title (from link) as full_title if metadata had sale prefix
            if metadata_text and (
                metadata_text.startswith("SALE")
                or metadata_text.startswith("SOLD OUT")
            ):
                parsed["full_title"] = title

            event = Event(
                full_title=parsed["full_title"],
                date=parsed["date"],
                location=parsed["location"],
                tags=parsed["tags"],
                is_dating=parsed["is_dating"],
                sale_status=parsed["sale_status"],
                link=link or "",
            )
            events.append(event)

        logger.info(f"Successfully scraped {len(events)} events")
        return events

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise ScraperError(f"Failed to scrape events: {e}") from e

    finally:
        if driver:
            driver.quit()
            logger.debug("WebDriver closed")
