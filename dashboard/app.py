"""Streamlit dashboard for STST Events."""

import calendar
import json
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from stst_dev.config import SOCIAL_MEDIA_TASK_TYPES
from stst_dev.database import (
    get_event_count,
    get_social_media_tasks,
    get_upcoming_events,
    init_db,
    mark_canva_posted,
    mark_task_complete,
)

# Page configuration
st.set_page_config(
    page_title="STST Events Dashboard",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
init_db()


def events_to_dataframe(events) -> pd.DataFrame:
    """Convert list of Event objects to a pandas DataFrame."""
    if not events:
        return pd.DataFrame()

    data = []
    for event in events:
        tags = event.tags if isinstance(event.tags, list) else json.loads(event.tags or "[]")
        data.append(
            {
                "ID": event.id,
                "Title": event.full_title,
                "Date": event.date,
                "Day": event.day_of_week,
                "Time": event.start_time or "",
                "Venue": event.location,
                "City": event.city or "",
                "State": event.state or "",
                "Tags": ", ".join(tags) if tags else "",
                "Dating": "Yes" if event.is_dating else "No",
                "Status": event.sale_status or "",
                "Link": event.link,
                "Added": event.first_seen_at.strftime("%Y-%m-%d") if event.first_seen_at else "",
            }
        )
    return pd.DataFrame(data)


def render_calendar_view(events, year: int, month: int) -> None:
    """Render a calendar view of events for a given month.

    Args:
        events: List of Event objects to display.
        year: Year to display.
        month: Month to display (1-12).
    """
    # Group events by date (ISO format YYYY-MM-DD)
    events_by_date = {}
    for event in events:
        # event.date is stored as ISO format in DB
        event_date = event.date  # YYYY-MM-DD
        if event_date not in events_by_date:
            events_by_date[event_date] = []
        events_by_date[event_date].append(event)

    # Set Monday as first day of week
    cal = calendar.Calendar(firstweekday=0)  # 0 = Monday
    month_days = cal.monthdayscalendar(year, month)

    # Header row with day names
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cols = st.columns(7)
    for i, day_name in enumerate(day_names):
        cols[i].markdown(f"**{day_name}**")

    # Calendar grid
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    st.write("")  # Empty cell for days outside the month
                else:
                    date_str = f"{year}-{month:02d}-{day:02d}"
                    day_events = events_by_date.get(date_str, [])

                    # Day number with event count indicator
                    if day_events:
                        st.markdown(f"**{day}** ({len(day_events)})")
                    else:
                        st.markdown(f"{day}")

                    # List events for this day
                    for event in day_events:
                        city = event.city or ""
                        venue = event.location or ""
                        time = event.start_time or ""
                        dating_label = "Dating" if event.is_dating else ""

                        # Build display string
                        parts = [p for p in [time, city, venue, dating_label] if p]
                        display = ", ".join(parts) if parts else event.full_title[:20]

                        st.caption(display)


def render_events_table(df: pd.DataFrame) -> None:
    """Render an events dataframe as a table with links."""
    if df.empty:
        st.info("No events found matching the criteria.")
        return

    # Configure columns to display
    display_cols = ["Title", "Date", "Day", "Time", "Venue", "City", "State", "Tags", "Dating", "Status", "Link"]
    if "Added" in df.columns:
        display_cols.append("Added")

    # Display as interactive table
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Title": st.column_config.TextColumn("Event Title", width="large"),
            "Date": st.column_config.TextColumn("Date", width="medium"),
            "Day": st.column_config.TextColumn("Day", width="small"),
            "Time": st.column_config.TextColumn("Time", width="small"),
            "Venue": st.column_config.TextColumn("Venue", width="medium"),
            "City": st.column_config.TextColumn("City", width="small"),
            "State": st.column_config.TextColumn("State", width="small"),
            "Tags": st.column_config.TextColumn("Tags", width="medium"),
            "Dating": st.column_config.TextColumn("Dating", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Link": st.column_config.LinkColumn("Link", width="small", display_text="🔗"),
            "Added": st.column_config.TextColumn("Added", width="small"),
        },
    )


def page_upcoming_events():
    """Render the Upcoming Events page."""
    st.header("Upcoming Events")

    events = get_upcoming_events()
    df = events_to_dataframe(events)

    if df.empty:
        st.info("No upcoming events found. Run 'task refresh' to scrape events.")
        return

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cities = ["All"] + sorted([c for c in df["City"].unique().tolist() if c])
        selected_city = st.selectbox("Filter by City", cities)

    with col2:
        states = ["All"] + sorted([s for s in df["State"].unique().tolist() if s])
        selected_state = st.selectbox("Filter by State", states)

    with col3:
        # Get unique tags
        all_tags = set()
        for tags_str in df["Tags"]:
            if tags_str:
                for tag in tags_str.split(", "):
                    all_tags.add(tag)
        tags_list = ["All"] + sorted(all_tags)
        selected_tag = st.selectbox("Filter by Tag", tags_list)

    with col4:
        dating_options = ["All", "Yes", "No"]
        selected_dating = st.selectbox("Dating Events", dating_options)

    # Apply filters
    filtered_df = df.copy()
    if selected_city != "All":
        filtered_df = filtered_df[filtered_df["City"] == selected_city]
    if selected_state != "All":
        filtered_df = filtered_df[filtered_df["State"] == selected_state]
    if selected_tag != "All":
        filtered_df = filtered_df[filtered_df["Tags"].str.contains(selected_tag, na=False)]
    if selected_dating != "All":
        filtered_df = filtered_df[filtered_df["Dating"] == selected_dating]

    st.metric("Events Found", len(filtered_df))
    render_events_table(filtered_df)


def page_social_media_checklist():
    """Render the Social Media Checklist page."""
    st.header("Social Media Checklist")

    # Get all upcoming events for both views
    all_upcoming = get_upcoming_events()

    # Calendar View Section
    st.subheader("Calendar View")

    # Month navigation
    today = datetime.now()
    col1, col2 = st.columns([1, 3])

    with col1:
        # Default to current month, allow selecting future months
        available_months = []
        for i in range(6):  # Show 6 months ahead
            month_date = datetime(today.year + (today.month + i - 1) // 12,
                                  ((today.month + i - 1) % 12) + 1, 1)
            available_months.append(month_date.strftime("%B %Y"))

        selected_month_str = st.selectbox("Select Month", available_months)
        selected_date = datetime.strptime(selected_month_str, "%B %Y")

    # Render calendar
    render_calendar_view(all_upcoming, selected_date.year, selected_date.month)

    st.divider()

    # Task Checklist Section
    st.subheader("Task Checklist")

    # Filter options
    show_all = st.checkbox("Show all events (including completed)", value=False)

    if show_all:
        events = all_upcoming
    else:
        events = [e for e in all_upcoming if any(
            not task.completed for task in get_social_media_tasks(e.id)
        )]

    if not events:
        st.success("All social media tasks are complete!")
        return

    st.write(f"**{len(events)} events**")

    # Build dataframe with event info and task checkboxes
    rows = []
    for event in events:
        tasks = get_social_media_tasks(event.id)
        task_status = {t.task_type: t.completed for t in tasks}

        row = {
            "ID": event.id,
            "Title": event.full_title,
            "Date": event.date,
            "Day": event.day_of_week or "",
            "Venue": event.location or "",
            "City": event.city or "",
            "State": event.state or "",
            "Dating": "Y" if event.is_dating else "N",
        }
        # Add task columns
        for task_type in SOCIAL_MEDIA_TASK_TYPES:
            row[task_type] = task_status.get(task_type, False)

        rows.append(row)

    df = pd.DataFrame(rows)

    # Configure which columns are editable (only task checkboxes)
    column_config = {
        "ID": None,  # Hide ID column
        "Title": st.column_config.TextColumn("Title", width="large", disabled=True),
        "Date": st.column_config.TextColumn("Date", width="medium", disabled=True),
        "Day": st.column_config.TextColumn("Day", width="small", disabled=True),
        "Venue": st.column_config.TextColumn("Venue", width="medium", disabled=True),
        "City": st.column_config.TextColumn("City", width="small", disabled=True),
        "State": st.column_config.TextColumn("State", width="small", disabled=True),
        "Dating": st.column_config.TextColumn("Dating", width="small", disabled=True),
    }
    for task_type in SOCIAL_MEDIA_TASK_TYPES:
        column_config[task_type] = st.column_config.CheckboxColumn(
            task_type, width="small"
        )

    # Display editable table
    edited_df = st.data_editor(
        df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        key="social_media_tasks_editor",
    )

    # Check for changes and update database
    for idx, row in edited_df.iterrows():
        event_id = df.iloc[idx]["ID"]
        for task_type in SOCIAL_MEDIA_TASK_TYPES:
            old_value = df.iloc[idx][task_type]
            new_value = row[task_type]
            if old_value != new_value:
                mark_task_complete(event_id, task_type, new_value)
                st.rerun()


def _parse_event_date(date_str: str):
    """Parse event date from ISO or long format."""
    for fmt in ("%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _get_event_type_label(event) -> str:
    """Derive a display label for the event type."""
    tags = event.tags if isinstance(event.tags, list) else json.loads(event.tags or "[]")
    if event.is_dating:
        for tag in tags:
            if tag in ("20s", "30s", "Millennials"):
                return f"{tag} speed-dating"
        return "Speed-dating"
    for tag in ("LGBTQIA+", "BIPOC", "Women", "20s", "30s", "Millennials"):
        if tag in tags:
            return tag
    return "Regular"


def _format_canva_text(event) -> str:
    """Format event info as multi-line text for Canva copy-paste."""
    parsed = _parse_event_date(event.date)
    if parsed:
        month_abbr = parsed.strftime("%b")
        day_num = str(parsed.day)
    else:
        month_abbr = ""
        day_num = ""

    day_of_week = event.day_of_week or ""
    start_time = event.start_time or ""
    venue = event.location or ""
    city = event.city or ""
    state = event.state or ""
    city_state = f"{city}, {state}" if city and state else city or state or ""

    lines = [
        f"{day_of_week},",
        f"{month_abbr} {day_num},",
        f"{start_time},",
        f"{venue},",
        city_state,
    ]
    return "\n".join(lines)


def _render_week_section(events, label, monday, sunday, key_prefix):
    """Render a labeled week section with event rows."""
    date_range = f"{monday.strftime('%b %d')} \u2013 {sunday.strftime('%b %d, %Y')}"
    st.markdown(
        f'<div class="week-header">{label} &middot; {date_range}</div>',
        unsafe_allow_html=True,
    )

    if not events:
        st.info("No events this week.")
        return

    # Column headers
    header_cols = st.columns([5, 2, 2, 1])
    header_cols[0].markdown(
        '<div class="col-header">Post Text</div>', unsafe_allow_html=True
    )
    header_cols[1].markdown(
        '<div class="col-header">Event Type</div>', unsafe_allow_html=True
    )
    header_cols[2].markdown(
        '<div class="col-header">Venue Placeholder</div>', unsafe_allow_html=True
    )
    header_cols[3].markdown(
        '<div class="col-header">Added to Canva</div>', unsafe_allow_html=True
    )

    for event in events:
        cols = st.columns([5, 2, 2, 1])
        with cols[0]:
            st.code(_format_canva_text(event), language=None)
        with cols[1]:
            type_label = _get_event_type_label(event)
            st.markdown(
                f'<span class="event-type-pill">{type_label}</span>',
                unsafe_allow_html=True,
            )
        with cols[2]:
            st.caption(event.venue_placeholder or "")
        with cols[3]:
            posted = st.checkbox(
                "Done",
                value=event.canva_posted,
                key=f"{key_prefix}_{event.id}",
                label_visibility="collapsed",
            )
            if posted != event.canva_posted:
                mark_canva_posted(event.id, posted)
                st.rerun()


def page_weekly_posts():
    """Render the Weekly Posts page for Canva content creation."""
    st.markdown(
        """
        <style>
        .weekly-title {
            color: #920c4f;
            font-size: 2rem;
            font-weight: 800;
            margin-bottom: 0.5rem;
        }
        .week-header {
            color: #920c4f;
            font-size: 1.4rem;
            font-weight: 700;
            border-bottom: 3px solid #920c4f;
            padding-bottom: 8px;
            margin-top: 2rem;
            margin-bottom: 1.5rem;
        }
        .col-header {
            color: #920c4f;
            font-weight: 700;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(146, 12, 79, 0.2);
        }
        .event-type-pill {
            background: linear-gradient(135deg, #fce4ef, #f8d0e3);
            color: #920c4f;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-block;
            margin-top: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="weekly-title">Weekly Posts</div>', unsafe_allow_html=True)

    events = get_upcoming_events()
    today = datetime.now().date()

    # Week boundaries (weeks start on Monday)
    if today.weekday() == 6:  # Sunday — upcoming week is tomorrow
        upcoming_monday = today + timedelta(days=1)
    else:
        upcoming_monday = today - timedelta(days=today.weekday())
    upcoming_sunday = upcoming_monday + timedelta(days=6)
    next_monday = upcoming_monday + timedelta(days=7)
    next_sunday = next_monday + timedelta(days=6)

    # Categorize events by week
    upcoming_week = []
    next_week = []

    for event in events:
        event_date = _parse_event_date(event.date)
        if not event_date:
            continue
        d = event_date.date()
        if upcoming_monday <= d <= upcoming_sunday:
            upcoming_week.append(event)
        elif next_monday <= d <= next_sunday:
            next_week.append(event)

    upcoming_week.sort(key=lambda e: (e.date, e.start_time or ""))
    next_week.sort(key=lambda e: (e.date, e.start_time or ""))

    _render_week_section(
        upcoming_week, "Upcoming Week",
        upcoming_monday, upcoming_sunday, "upcoming"
    )
    _render_week_section(
        next_week, "Next Week",
        next_monday, next_sunday, "next"
    )


# Main app
def main():
    st.title("Skip the Small Talk Events Dashboard")

    # Sidebar navigation
    st.sidebar.title("Navigation")

    pages = {
        "📅 Upcoming Events": page_upcoming_events,
        "🎨 Weekly Posts": page_weekly_posts,
        "📱 Social Media Checklist": page_social_media_checklist,
    }

    selection = st.sidebar.radio("Go to", list(pages.keys()))

    # Info in sidebar
    st.sidebar.divider()
    st.sidebar.info(
        "Run `task refresh` to update events from the website."
    )
    st.sidebar.write(f"Total events: {get_event_count()}")

    # Render selected page
    pages[selection]()


if __name__ == "__main__":
    main()
