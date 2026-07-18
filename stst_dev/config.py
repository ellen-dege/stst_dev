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
    "event_detail_excerpt": "ProductItem-details-excerpt",
}

# Tag options for categorizing events (extracted from title text)
TAG_OPTIONS = [
    "20s",
    "30s",
    "Millennials",
    "Millennial",
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

# Maps title strings to their canonical tag names (handles singular/plural and case variants)
TAG_NORMALIZE = {
    "Millennial": "Millennials",
    "bi & pan": "Bi & Pan",
    "poly": "Poly",
    "monogamous": "Monogamous",
    "ace-spectrum": "Ace-Spectrum",
}

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

# Event type mapping (scraped event_type → normalized value for v2 DB)
EVENT_TYPE_MAP = {
    "Open to Everyone": "Regular",
    "Dating": "Dating",
    "LGBTQIA+": "LGBTQIA+",
    "Women": "Women",
    "BIPOC": "BIPOC",
}
EVENT_TYPE_DEFAULT = "Regular"

# Titles to skip (non-event listings like gift cards)
SKIP_TITLES = ["gift card"]

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
SELENIUM_TIMEOUT = 10       # seconds — WebDriverWait element-presence timeout
PAGE_LOAD_TIMEOUT = 60      # seconds — max time to wait for a full page load
CHROME_OPTIONS = [
    "--headless=new",                          # replaces deprecated --headless in Chrome 112+
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-background-timer-throttling",   # prevent JS timer stalls in headless
    "--disable-renderer-backgrounding",
    "--blink-settings=imagesEnabled=false",    # skip image downloads, speeds up rendering
]
