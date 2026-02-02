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


def render_events_table(df: pd.DataFrame, show_link_column: bool = True) -> None:
    """Render an events dataframe as a table with links."""
    if df.empty:
        st.info("No events found matching the criteria.")
        return

    # Configure columns to display
    display_cols = ["Title", "Date", "Day", "Venue", "City", "State", "Tags", "Dating", "Status"]
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
            "Venue": st.column_config.TextColumn("Venue", width="medium"),
            "City": st.column_config.TextColumn("City", width="small"),
            "State": st.column_config.TextColumn("State", width="small"),
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

    # Filter options
    show_all = st.checkbox("Show all events (including completed)", value=False)

    if show_all:
        events = get_upcoming_events()
    else:
        events = get_upcoming_events()
        events = [e for e in events if any(
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

    # Events by city
    st.subheader("Events by City")
    events = get_upcoming_events()
    if events:
        df = events_to_dataframe(events)
        city_counts = df["City"].value_counts()
        st.bar_chart(city_counts)

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
