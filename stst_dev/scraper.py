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
    EVENT_TYPES,
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
    # Replace all newlines with spaces and collapse multiple spaces
    text = text.replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def _extract_location_from_metadata(metadata_text: str) -> str:
    """Extract venue/location from metadata by finding text before (map).

    The metadata can be separated by newlines or commas, e.g.:
    "Dating,\nMcCarthy's, (map)\nBoston"

    Args:
        metadata_text: Metadata string containing venue before "(map)"

    Returns:
        The venue name, or empty string if not found.
    """
    if "(map)" not in metadata_text.lower():
        return ""

    # Normalize: replace newlines with commas, then split
    normalized = metadata_text.replace("\n", ",")
    parts = [p.strip() for p in normalized.split(",") if p.strip()]

    for i, part in enumerate(parts):
        if "(map)" in part.lower():
            if i > 0:
                return parts[i - 1]
    return ""


def _extract_event_type_from_tag_links(tag_hrefs: list[str]) -> str:
    """Extract event type from tag link URLs.

    Event types are encoded with <br><br> prefix in tag links, e.g.:
    - "<br><br>Dating"
    - "<br><br>Open to Everyone"
    - "<br><br>LGBTQIA+"

    Args:
        tag_hrefs: List of tag link href values

    Returns:
        The event type, or empty string if not found.
    """
    from urllib.parse import unquote

    for href in tag_hrefs:
        if "tag=" not in href:
            continue

        # Extract and decode tag value
        tag_value = unquote(href.split("tag=")[1].split("&")[0])
        tag_value = tag_value.replace("+", " ")

        # Event types have <br><br> prefix
        if tag_value.startswith("<br><br>"):
            event_type = tag_value.replace("<br><br>", "").strip()
            if event_type in EVENT_TYPES:
                return event_type

    return ""


def _extract_venue_from_tag_links(tag_hrefs: list[str]) -> str:
    """Extract venue from tag link URLs.

    Tag links contain URL-encoded values like:
    - "<br><br>Dating" (event type)
    - "<br>McCarthy's" (venue)
    - "(<a href='...'>map</a>)" (map link)

    The venue is the tag that starts with "<br>" (single) but isn't a known event type.

    Args:
        tag_hrefs: List of tag link href values

    Returns:
        The venue name, or empty string if not found.
    """
    from urllib.parse import unquote

    for href in tag_hrefs:
        if "tag=" not in href:
            continue

        # Extract and decode tag value
        tag_value = unquote(href.split("tag=")[1].split("&")[0])

        # Replace + with space (URL encoding)
        tag_value = tag_value.replace("+", " ")

        # Check if it's a venue (starts with single <br> but not an event type)
        if tag_value.startswith("<br>") and not tag_value.startswith("<br><br>"):
            venue = tag_value.replace("<br>", "").strip()
            if venue and venue not in EVENT_TYPES:
                return venue

    return ""


def _parse_event_metadata(text: str, metadata_text: str = "") -> dict:
    """Parse event metadata from a title string and optional metadata.

    Args:
        text: Event title string (e.g., "Skip the Small Talk at Aeronaut: Monday, August 25, 2025")
        metadata_text: Optional metadata string containing venue before "(map)"

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

    # Extract location from metadata (text before "(map)") - works for all event types
    location = ""
    if metadata_text:
        location = _extract_location_from_metadata(metadata_text)

    # Fallback: extract from title (text between "at " and ": ") for backwards compatibility
    if not location and " at " in text:
        location_part = text.split(" at ", 1)[1]
        if ": " in location_part:
            location = location_part.split(": ", 1)[0]
        else:
            location = location_part

    # Extract tags from title text
    tags = []
    for tag in TAG_OPTIONS:
        if tag in text:
            # Normalize tag to standard form
            normalized_tag = tag.capitalize() if tag.islower() else tag
            if normalized_tag not in tags:
                tags.append(normalized_tag)

    # Note: is_dating is determined by event_type in scrape_events()
    is_dating = False

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

        # Find event cards (each .summary-item contains one event)
        event_cards = driver.find_elements(By.CSS_SELECTOR, ".summary-item")
        logger.info(f"Found {len(event_cards)} event cards")

        # Build Event objects from each card
        events = []

        for card in event_cards:
            # Get title and link from the title link element
            try:
                title_elem = card.find_element(
                    By.CLASS_NAME, CSS_SELECTORS["event_title_links"]
                )
                title = title_elem.text.strip()
                link = title_elem.get_attribute("href")
            except Exception:
                continue  # Skip cards without title links

            if not title:
                continue  # Skip empty titles

            # Get metadata text for sale status detection
            try:
                metadata_elem = card.find_element(
                    By.CLASS_NAME, CSS_SELECTORS["event_metadata"]
                )
                metadata_text = _clean_metadata_text(metadata_elem.text)
            except Exception:
                metadata_text = ""

            # Extract info from tag links in this card
            tag_links = card.find_elements(By.CSS_SELECTOR, 'a[href*="/store?tag="]')
            tag_hrefs = [elem.get_attribute("href") for elem in tag_links]
            venue_from_tags = _extract_venue_from_tag_links(tag_hrefs)
            event_type = _extract_event_type_from_tag_links(tag_hrefs)

            # Parse metadata for other fields
            parsed = _parse_event_metadata(title, metadata_text)

            # Use venue from tag links if found, otherwise fall back to parsed location
            location = venue_from_tags if venue_from_tags else parsed["location"]

            # Determine is_dating from event_type
            is_dating = event_type == "Dating"

            # Build tags list - start with tags from title
            tags = parsed["tags"].copy()

            # Add event_type as tag if applicable
            # "Open to Everyone" = regular event, no tag needed
            # (TODO: Consider adding a "Regular" tag for these in the future)
            if event_type and event_type != "Open to Everyone":
                if event_type not in tags:
                    tags.append(event_type)

            event = Event(
                full_title=title,
                date=parsed["date"],
                location=location,
                tags=tags,
                is_dating=is_dating,
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
