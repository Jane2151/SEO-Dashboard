"""Formats a stored UTC timestamp in the viewer's own browser timezone —
without this, a timestamp always reads in whichever timezone the server
process happens to run in (the user's own PC locally, but UTC on Streamlit
Cloud), which silently disagrees with the viewer's wall clock.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st


def format_local_timestamp(iso_str: str, fmt: str = "%b %d, %Y %I:%M %p") -> str:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        # Pre-migration rows were written naive; treat them as UTC rather
        # than leave them unconvertible.
        dt = dt.replace(tzinfo=timezone.utc)

    viewer_tz = None
    tz_name = st.context.timezone
    if tz_name:
        try:
            viewer_tz = ZoneInfo(tz_name)
        except Exception:
            viewer_tz = None
    if viewer_tz is None:
        offset_minutes = st.context.timezone_offset
        if offset_minutes is not None:
            viewer_tz = timezone(-timedelta(minutes=offset_minutes))

    return dt.astimezone(viewer_tz).strftime(fmt) if viewer_tz else dt.strftime(fmt)
