"""Shared date-range picker for pages built on the daily-synced GSC data.

Used by both Overview and Keyword Performance so "Last 7/28 Days" etc. means
the same thing everywhere, without duplicating the range math on each page.
"""

from datetime import date, timedelta

import streamlit as st

RANGE_OPTIONS = ["Last 7 Days", "Last 28 Days", "Last 3 Months", "Custom Date Range"]


def select_range(latest_synced_date: date, earliest_synced_date: date, key_prefix: str, latest_complete_date: date = None) -> tuple:
    """Render the radio (+ custom date inputs when needed) and return
    (range_start, range_end), clamped so range_start never predates the
    earliest synced day. key_prefix keeps widget keys unique per page.

    Preset ranges (Last 7/28/90 Days) anchor to latest_complete_date — the
    newest day GSC itself considers finalized — not latest_synced_date,
    which includes fresh/preliminary days kept on purpose so later syncs can
    revise them. Falls back to latest_synced_date if no complete date has
    been recorded yet (e.g. before the first sync under this logic ran).
    Custom Date Range still allows picking up to latest_synced_date, since a
    user may deliberately want to include a preliminary day.
    """
    preset_end_date = latest_complete_date or latest_synced_date
    selected_range = st.radio("Date range", RANGE_OPTIONS, horizontal=True, key=f"{key_prefix}_range")

    if selected_range == "Last 7 Days":
        range_end, range_start = preset_end_date, preset_end_date - timedelta(days=6)
    elif selected_range == "Last 28 Days":
        range_end, range_start = preset_end_date, preset_end_date - timedelta(days=27)
    elif selected_range == "Last 3 Months":
        range_end, range_start = preset_end_date, preset_end_date - timedelta(days=89)
    else:
        custom_col1, custom_col2 = st.columns(2)
        range_start = custom_col1.date_input(
            "Start date", value=latest_synced_date - timedelta(days=27), max_value=latest_synced_date, key=f"{key_prefix}_start"
        )
        range_end = custom_col2.date_input("End date", value=latest_synced_date, max_value=latest_synced_date, key=f"{key_prefix}_end")

    range_start = max(range_start, earliest_synced_date)

    if latest_complete_date is None:
        st.caption(
            "The latest GSC-finalized date isn't known yet — sync again on the main page to determine it. "
            "Until then, presets fall back to the freshest synced date, which may still be preliminary."
        )
    elif range_end > latest_complete_date:
        st.caption("Recent dates may still be preliminary and can change after Google Search Console finalizes them.")

    return range_start, range_end
