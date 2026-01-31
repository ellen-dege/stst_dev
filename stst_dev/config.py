"""Configuration constants for STST Events Scraper."""

from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "events.db"

# Website configuration
TARGET_URL = "https://www.skipthesmalltalk.com/public-events?category=All"

# CSS selectors for scraping
CSS_SELECTORS = {
    "event_title_links": "summary-title-link",
    "event_metadata": "summary-item-record-type-store-item",
}

# Tag options for categorizing events
TAG_OPTIONS = [
    "20s",
    "30s",
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

# Dating event indicators
DATING_INDICATORS = ["Dating", "dating"]

# Sale status options
SALE_OPTIONS = ["Sale", "sale", "SALE", "SOLD OUT", "Sold Out", "sold out"]

# Social media task types for checklist
SOCIAL_MEDIA_TASK_TYPES = [
    "instagram",
    "facebook",
    "newsletter",
    "twitter",
    "linkedin",
]

# Selenium configuration
SELENIUM_TIMEOUT = 10  # seconds
CHROME_OPTIONS = [
    "--headless",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]
