"""Streamlit dashboard for STST Events."""

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from stst_dev.config import SOCIAL_MEDIA_TASK_TYPES
from stst_dev.database import (
    get_all_events,
    get_event_count,
    get_events_with_incomplete_tasks,
    get_events_with_sale_status,
    get_new_events,
    get_social_media_tasks,
    get_upcoming_events,
    init_db,
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
                "Location": event.location,
                "Tags": ", ".join(tags) if tags else "",
                "Dating": "Yes" if event.is_dating else "No",
                "Status": event.sale_status or "",
                "Link": event.link,
                "Added": event.first_seen_at.strftime("%Y-%m-%d") if event.first_seen_at else "",
            }
        )
    return pd.DataFrame(data)


def render_events_table(df: pd.DataFrame, show_link_column: bool = True) -> None:
    """Render an events dataframe as a table with links."""
    if df.empty:
        st.info("No events found matching the criteria.")
        return

    # Configure columns to display
    display_cols = ["Title", "Date", "Day", "Location", "Tags", "Dating", "Status"]
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
            "Location": st.column_config.TextColumn("Location", width="medium"),
            "Tags": st.column_config.TextColumn("Tags", width="medium"),
            "Dating": st.column_config.TextColumn("Dating", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Added": st.column_config.TextColumn("Added", width="small"),
        },
    )

    # Show links section
    if show_link_column and "Link" in df.columns:
        with st.expander("Event Links"):
            for _, row in df.iterrows():
                if row["Link"]:
                    st.markdown(f"- [{row['Title'][:50]}...]({row['Link']})")


def page_upcoming_events():
    """Render the Upcoming Events page."""
    st.header("Upcoming Events")

    events = get_upcoming_events()
    df = events_to_dataframe(events)

    if df.empty:
        st.info("No upcoming events found. Run 'task refresh' to scrape events.")
        return

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        locations = ["All"] + sorted(df["Location"].unique().tolist())
        selected_location = st.selectbox("Filter by Location", locations)

    with col2:
        # Get unique tags
        all_tags = set()
        for tags_str in df["Tags"]:
            if tags_str:
                for tag in tags_str.split(", "):
                    all_tags.add(tag)
        tags_list = ["All"] + sorted(all_tags)
        selected_tag = st.selectbox("Filter by Tag", tags_list)

    with col3:
        dating_options = ["All", "Yes", "No"]
        selected_dating = st.selectbox("Dating Events", dating_options)

    # Apply filters
    filtered_df = df.copy()
    if selected_location != "All":
        filtered_df = filtered_df[filtered_df["Location"] == selected_location]
    if selected_tag != "All":
        filtered_df = filtered_df[filtered_df["Tags"].str.contains(selected_tag, na=False)]
    if selected_dating != "All":
        filtered_df = filtered_df[filtered_df["Dating"] == selected_dating]

    st.metric("Events Found", len(filtered_df))
    render_events_table(filtered_df)


def page_new_events():
    """Render the Newly Added Events page."""
    st.header("Newly Added Events")

    days = st.slider("Show events added in the last N days", 1, 30, 7)
    events = get_new_events(days=days)
    df = events_to_dataframe(events)

    if df.empty:
        st.info(f"No events added in the last {days} days.")
        return

    st.metric("New Events", len(df))
    render_events_table(df)


def page_sales_status():
    """Render the Low Ticket Sales / Sale Status page."""
    st.header("Sale Status")

    tab1, tab2 = st.tabs(["On Sale", "Sold Out"])

    with tab1:
        sale_events = get_events_with_sale_status("SALE")
        df_sale = events_to_dataframe(sale_events)
        st.metric("Events on Sale", len(df_sale))
        if not df_sale.empty:
            st.info("These events have a SALE tag - may indicate low ticket sales.")
            render_events_table(df_sale)
        else:
            st.success("No events currently on sale.")

    with tab2:
        sold_out_events = get_events_with_sale_status("SOLD_OUT")
        df_sold = events_to_dataframe(sold_out_events)
        st.metric("Sold Out Events", len(df_sold))
        if not df_sold.empty:
            st.success("These events are sold out!")
            render_events_table(df_sold)
        else:
            st.info("No sold out events.")


def page_social_media_checklist():
    """Render the Social Media Checklist page."""
    st.header("Social Media Checklist")

    # Get events with incomplete tasks
    events_with_tasks = get_events_with_incomplete_tasks()

    # Filter options
    show_all = st.checkbox("Show all events (including completed)", value=False)

    if show_all:
        events = get_upcoming_events()
    else:
        # Convert to Event-like objects for display
        events = get_upcoming_events()
        events = [e for e in events if any(
            not task.completed for task in get_social_media_tasks(e.id)
        )]

    if not events:
        st.success("All social media tasks are complete!")
        return

    st.write(f"**{len(events)} events with pending tasks**")

    for event in events:
        tasks = get_social_media_tasks(event.id)
        completed_count = sum(1 for t in tasks if t.completed)
        total_count = len(tasks)

        # Progress indicator
        progress = completed_count / total_count if total_count > 0 else 0

        with st.expander(
            f"{'✅' if progress == 1 else '⏳'} {event.full_title[:60]}... ({completed_count}/{total_count})"
        ):
            st.write(f"**Date:** {event.date}")
            st.write(f"**Location:** {event.location}")
            if event.link:
                st.markdown(f"[View Event]({event.link})")

            st.divider()
            st.write("**Tasks:**")

            # Create checkboxes for each task
            cols = st.columns(len(SOCIAL_MEDIA_TASK_TYPES))
            for idx, task_type in enumerate(SOCIAL_MEDIA_TASK_TYPES):
                task = next((t for t in tasks if t.task_type == task_type), None)
                is_completed = task.completed if task else False

                with cols[idx]:
                    new_value = st.checkbox(
                        task_type.capitalize(),
                        value=is_completed,
                        key=f"task_{event.id}_{task_type}",
                    )

                    # Update if changed
                    if task and new_value != is_completed:
                        mark_task_complete(event.id, task_type, new_value)
                        st.rerun()


def page_stats():
    """Render the Statistics page."""
    st.header("Event Statistics")

    total_events = get_event_count()
    upcoming_events = len(get_upcoming_events())
    new_events_7d = len(get_new_events(days=7))
    sale_events = len(get_events_with_sale_status("SALE"))
    sold_out_events = len(get_events_with_sale_status("SOLD_OUT"))

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Events", total_events)
    col2.metric("Upcoming", upcoming_events)
    col3.metric("New (7 days)", new_events_7d)
    col4.metric("On Sale", sale_events)
    col5.metric("Sold Out", sold_out_events)

    # Events by location
    st.subheader("Events by Location")
    events = get_upcoming_events()
    if events:
        df = events_to_dataframe(events)
        location_counts = df["Location"].value_counts()
        st.bar_chart(location_counts)

    # Events by date (timeline)
    st.subheader("Upcoming Events Timeline")
    if events:
        df = events_to_dataframe(events)
        # Try to parse dates for grouping
        date_counts = df["Date"].value_counts().sort_index()
        st.line_chart(date_counts)


# Main app
def main():
    st.title("Skip the Small Talk Events Dashboard")

    # Sidebar navigation
    st.sidebar.title("Navigation")

    pages = {
        "📅 Upcoming Events": page_upcoming_events,
        "🆕 Newly Added": page_new_events,
        "💰 Sale Status": page_sales_status,
        "📱 Social Media Checklist": page_social_media_checklist,
        "📊 Statistics": page_stats,
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
