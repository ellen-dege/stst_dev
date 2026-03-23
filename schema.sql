-- STST Event Database v2 Schema
-- 6 tables: city, facilitator, venue, event, tag, event_tag

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS city (
    city_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    city_name       TEXT    NOT NULL,
    city_abbrev     TEXT,
    state           TEXT,
    country         TEXT    NOT NULL DEFAULT 'US',
    region          TEXT,
    time_zone       TEXT,
    has_dedicated_ig  BOOLEAN NOT NULL DEFAULT 0,
    ig_handle         TEXT,
    website_city_name TEXT,
    drive_folder_url  TEXT
);

CREATE TABLE IF NOT EXISTS facilitator (
    facilitator_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id          INTEGER REFERENCES city(city_id),
    facilitator_name TEXT    NOT NULL,
    facilitator_email_1 TEXT,
    facilitator_email_2 TEXT,
    ig_handle        TEXT,
    tag_on_ig        BOOLEAN NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS venue (
    venue_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id           INTEGER NOT NULL REFERENCES city(city_id),
    venue_name        TEXT    NOT NULL,
    venue_ig_handle_1 TEXT,
    venue_ig_handle_2 TEXT,
    venue_events_site    TEXT,
    venue_address        TEXT,
    venue_fb_name        TEXT,
    venue_contact_emails TEXT,
    venue_TT             TEXT,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS venue_alias (
    alias    TEXT    PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venue(venue_id)
);

CREATE TABLE IF NOT EXISTS event (
    event_id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    city_id            INTEGER  NOT NULL REFERENCES city(city_id),
    venue_id           INTEGER  REFERENCES venue(venue_id),
    facilitator_id     INTEGER  REFERENCES facilitator(facilitator_id),
    event_date         DATE     NOT NULL,
    event_day_of_week  TEXT,
    event_start_time   TIME,
    event_type         TEXT,
    event_link         TEXT     UNIQUE NOT NULL,
    sold_out           BOOLEAN  NOT NULL DEFAULT 0,
    is_dating          BOOLEAN  NOT NULL DEFAULT 0,
    validated          BOOLEAN  NOT NULL DEFAULT 0,
    tickets_sold       INTEGER,
    ticket_threshold   INTEGER,
    num_attended       INTEGER,
    man_tix            INTEGER,
    woman_tix          INTEGER,
    man_tix_understudy INTEGER,
    woman_tix_understudy INTEGER,
    first_scraped_at   DATETIME NOT NULL DEFAULT (datetime('now')),
    last_checked_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    status_changed_at  DATETIME
);

CREATE TABLE IF NOT EXISTS tag (
    tag_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name     TEXT    NOT NULL UNIQUE,
    tag_category TEXT
);

CREATE TABLE IF NOT EXISTS event_tag (
    event_tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES event(event_id),
    tag_id       INTEGER NOT NULL REFERENCES tag(tag_id),
    UNIQUE(event_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_event_date ON event(event_date);
CREATE INDEX IF NOT EXISTS idx_event_link ON event(event_link);
CREATE INDEX IF NOT EXISTS idx_event_city ON event(city_id);
CREATE INDEX IF NOT EXISTS idx_event_tag_event ON event_tag(event_id);
CREATE INDEX IF NOT EXISTS idx_event_tag_tag ON event_tag(tag_id);
