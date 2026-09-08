"""Auto-sync: pulls recent GSC data into the daily-level tables.

A single sync_gsc_data() entry point, so it can be called from a Streamlit
button today and from a scheduled job later (cron, Task Scheduler, etc.)
without any change to this module — the caller just needs a valid `service`
and `site_url`.
"""

from datetime import date, timedelta

from data_processing import gsc_api_client
from database import gsc_daily_repository

# First-ever sync backfills this far. GSC itself only retains ~16 months.
INITIAL_BACKFILL_DAYS = 90

# Every sync re-fetches at least this many of the most recent days, since
# Search Console can revise "fresh" data for a few days after collection —
# this is what keeps stored totals from silently going stale.
REFETCH_RECENT_DAYS = 3


def determine_sync_range(today: date) -> tuple:
    """What date range to fetch for this sync run."""
    last_synced = gsc_daily_repository.get_latest_synced_date()
    if last_synced is None:
        return today - timedelta(days=INITIAL_BACKFILL_DAYS), today
    start = min(last_synced - timedelta(days=REFETCH_RECENT_DAYS - 1), today)
    return start, today


def sync_gsc_data(service, site_url: str) -> dict:
    """Fetch and upsert overall + query/page/device/country daily data for
    the sync range. Returns a small summary dict for the UI to display."""
    start, end = determine_sync_range(date.today())

    overall_df = gsc_api_client.fetch_daily_breakdown(service, site_url, start, end)
    query_df = gsc_api_client.fetch_daily_breakdown(service, site_url, start, end, extra_dimension="query")
    page_df = gsc_api_client.fetch_daily_breakdown(service, site_url, start, end, extra_dimension="page")
    device_df = gsc_api_client.fetch_daily_breakdown(service, site_url, start, end, extra_dimension="device")
    country_df = gsc_api_client.fetch_daily_breakdown(service, site_url, start, end, extra_dimension="country")

    gsc_daily_repository.upsert_daily_overall(overall_df)
    gsc_daily_repository.upsert_daily_query(query_df)
    gsc_daily_repository.upsert_daily_page(page_df)
    gsc_daily_repository.upsert_daily_device(device_df)
    gsc_daily_repository.upsert_daily_country(country_df)

    latest_complete_date = gsc_api_client.fetch_latest_complete_date(service, site_url)
    if latest_complete_date is not None:
        gsc_daily_repository.set_latest_complete_date(latest_complete_date)

    gsc_daily_repository.set_last_sync_time()

    return {
        "start": start,
        "end": end,
        "days_synced": len(overall_df),
        "total_impressions_in_range": int(overall_df["impressions"].sum()) if not overall_df.empty else 0,
    }
