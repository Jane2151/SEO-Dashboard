"""Entry point: connect to Search Console and sync daily performance data.

The dashboard (Overview, Keyword Performance, SEO Change Log — under pages/)
reads entirely from the daily-level tables this page syncs into. There's no
manual per-date-range dataset step anymore: connect once, then Sync.
"""

import streamlit as st

from data_processing import gsc_api_client, gsc_sync
from database import gsc_daily_repository
from database.db_setup import initialize_database
from utils.constants import TARGET_SITE_URL
from utils.text_style import styled_caption
from utils.time_format import format_local_timestamp

st.set_page_config(page_title="SEO Performance Dashboard", layout="wide")
initialize_database()

st.title("SEO Performance Dashboard")
st.write(
    "start from Aug 27 2026"
)

st.header("Google Search Console Connection")

creds = gsc_api_client.get_credentials(interactive=False)

if creds is None:
    st.write("Not connected to Google Search Console yet.")
    if st.button("Connect to Google Search Console"):
        try:
            with st.spinner("Waiting for Google sign-in in your browser..."):
                gsc_api_client.get_credentials(interactive=True)
            st.rerun()
        except gsc_api_client.GSCAuthError as exc:
            st.error(str(exc))
    st.stop()

st.success("Connected to Google Search Console.")
if st.button("Disconnect"):
    gsc_api_client.disconnect()
    st.rerun()

service = gsc_api_client.build_service(creds)
try:
    sites = gsc_api_client.list_verified_sites(service)
except Exception as exc:
    st.error(f"Could not list Search Console properties: {exc}")
    sites = []

if TARGET_SITE_URL not in sites:
    st.error(
        f"This dashboard is locked to '{TARGET_SITE_URL}', but that property "
        "isn't in this account's verified Search Console sites. "
        f"Verified sites found: {sites or 'none'}."
    )
    st.stop()

site_url = TARGET_SITE_URL
st.caption(f"Property: **{site_url}**")

st.header("Sync GSC Data")
st.caption(
    "Pulls daily performance into the database. "
)

last_synced_at = gsc_daily_repository.get_last_sync_time()
if last_synced_at:
    formatted_sync_time = format_local_timestamp(last_synced_at)
    styled_caption(f"Last synced: {formatted_sync_time}")
else:
    styled_caption("Never synced yet. First sync backfills the last 90 days.")

if st.button("Sync GSC Data", type="primary"):
    with st.spinner("Syncing daily data from Search Console..."):
        summary = gsc_sync.sync_gsc_data(service, site_url)
    st.success(
        f"Synced {summary['start']} to {summary['end']} — "
        f"{summary['days_synced']} days, {summary['total_impressions_in_range']:,} impressions in that range."
    )
    st.rerun()
