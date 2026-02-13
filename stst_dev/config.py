"""Configuration constants for STST Events Scraper."""

from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "events.db"
VENUE_LOOKUP_PATH = DATA_DIR / "venue_loc_lut.csv"
CITY_STATE_LOOKUP_PATH = DATA_DIR / "city_state_lut.csv"

# Website configuration
TARGET_URL = "https://www.skipthesmalltalk.com/public-events?category=All"

# CSS selectors for scraping
CSS_SELECTORS = {
    "event_title_links": "summary-title-link",
    "event_metadata": "summary-item-record-type-store-item",
}

# Tag options for categorizing events (extracted from title text)
TAG_OPTIONS = [
    "20s",
    "30s",
    "Millennials",
    "Online",
    "BIPOC",
    "LGBTQIA+",
    "Bi & Pan",
    "bi & pan",
    "Poly",
    "poly",
    "Monogamous",
    "monogamous",
    "Ace-Spectrum",
    "ace-spectrum",
]

# Event types (extracted from tag links with <br><br> prefix)
# These determine is_dating and can also become tags
EVENT_TYPES = [
    "Open to Everyone",  # No tag added for this (regular event)
    # TODO: Consider adding a "Regular" tag for these in the future
    "Dating",            # Sets is_dating=True
    "LGBTQIA+",          # Added as tag
    "Women",             # Added as tag (e.g., "All Women's" events)
    "BIPOC",             # Added as tag
]

# Sale status options
SALE_OPTIONS = ["Sale", "sale", "SALE", "SOLD OUT", "Sold Out", "sold out"]

# Social media task types for checklist
SOCIAL_MEDIA_TASK_TYPES = [
    "IG asset created",
    "IG asset to venue (optional)",
    "included in THIS WEEK",
    "2-week-out IG/FB scheduled",
    "1-week-out IG/FB scheduled",
]

# Selenium configuration
SELENIUM_TIMEOUT = 10  # seconds
CHROME_OPTIONS = [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]
