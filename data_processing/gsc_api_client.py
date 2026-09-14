"""Google Search Console API access (OAuth installed-app flow).

Authenticates as the user's own Google account rather than a service
account: the first "Connect" click opens a browser for a one-time consent,
after which the resulting token is cached in the shared database (see
oauth_token_repository) and silently refreshed on later runs — so any
deployment reading that same database is connected without repeating the
consent flow, which needs a real browser and so can only run locally.
`fetch_query_performance` returns the same normalized shape as
`csv_parser.parse_gsc_csv`, so a fetched dataset can be saved with
`gsc_repository.save_dataset()` exactly like a manual upload.
"""

import json
from datetime import date, timedelta

import pandas as pd
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from database import oauth_token_repository
from utils.constants import CLIENT_SECRET_PATH

# Read-only scope: this dashboard only ever reads performance data.
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Search Console API's maximum rows per searchanalytics.query call.
MAX_ROWS_PER_PAGE = 25000

# Without dataState, the API defaults to "final" — excluding not-yet-fully-
# processed data for the most recent day or two. The Search Console UI shows
# "all" (fresh + final) by default, so every fetch here must match that or
# a date range including recent days will silently undercount vs the UI.
DATA_STATE = "all"


class GSCAuthError(RuntimeError):
    """Raised when authentication can't proceed (e.g. missing client secret)."""


def get_credentials(interactive: bool = False):
    """Return valid cached OAuth credentials, or None if not yet connected.

    Only runs the interactive browser consent flow when interactive=True, so
    a Streamlit rerun never pops a browser window on its own. The token is
    read from the shared database (not a local file), so a connection made
    once — locally, since the interactive flow needs a real browser — is
    immediately available to every deployment reading the same database.
    """
    creds = None
    token_json = oauth_token_repository.get_token_json()
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # The refresh token itself is dead (revoked, or a Google Cloud
            # OAuth consent screen still in "Testing" mode expires it after
            # 7 days) — treat this exactly like "never connected" so the app
            # shows the normal Connect button instead of crashing.
            oauth_token_repository.delete_token()
            return None
        _save_token(creds)
        return creds

    if not interactive:
        return None

    if not CLIENT_SECRET_PATH.exists():
        raise GSCAuthError(
            f"Missing OAuth client secret file at {CLIENT_SECRET_PATH}. "
            "Download it from Google Cloud Console (Credentials > OAuth client "
            "ID > Desktop app) and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def is_connected() -> bool:
    return get_credentials(interactive=False) is not None


def disconnect() -> None:
    """Remove the cached token so the next connection re-prompts for consent."""
    oauth_token_repository.delete_token()


def _save_token(creds) -> None:
    oauth_token_repository.save_token_json(creds.to_json())


def build_service(creds):
    """Build the Search Console API client. Kept separate from the fetch
    functions below so tests can pass in a fake service double."""
    return build("searchconsole", "v1", credentials=creds)


def list_verified_sites(service) -> list:
    """Search Console properties this account has verified access to."""
    response = service.sites().list().execute()
    entries = response.get("siteEntry", [])
    return [entry["siteUrl"] for entry in entries if entry.get("permissionLevel") != "siteUnverifiedUser"]


def _fetch_paginated_rows(service, site_url: str, start_date: date, end_date: date, dimensions: list) -> list:
    """Shared pagination helper for a dimensioned searchanalytics.query call,
    walking startRow until a page comes back shorter than the row cap."""
    rows = []
    start_row = 0
    while True:
        request_body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": dimensions,
            "rowLimit": MAX_ROWS_PER_PAGE,
            "startRow": start_row,
            "dataState": DATA_STATE,
        }
        response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
        page_rows = response.get("rows", [])
        rows.extend(page_rows)
        if len(page_rows) < MAX_ROWS_PER_PAGE:
            break
        start_row += MAX_ROWS_PER_PAGE
    return rows


def fetch_query_performance(service, site_url: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Query-level clicks/impressions/ctr/position for one site and date range.

    For the Keyword Performance table only. Search Console omits some
    low-volume/anonymized queries from this breakdown, so summing this
    DataFrame understates true site totals — use fetch_overall_performance()
    for KPI-level totals instead.
    """
    rows = _fetch_paginated_rows(service, site_url, start_date, end_date, dimensions=["query"])

    if not rows:
        return pd.DataFrame(columns=["query", "clicks", "impressions", "ctr", "position"])

    return pd.DataFrame(
        {
            "query": [row["keys"][0] for row in rows],
            "clicks": [int(row["clicks"]) for row in rows],
            "impressions": [int(row["impressions"]) for row in rows],
            "ctr": [float(row["ctr"]) for row in rows],
            "position": [float(row["position"]) for row in rows],
        }
    )


def fetch_page_performance(service, site_url: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Page-level clicks/impressions/ctr/position for one site and date range.

    Used for Before/After Analysis: a change log entry targets one specific
    page, and sitewide totals alone can't show whether that page's own
    performance actually moved. Same low-volume-omission caveat as
    fetch_query_performance applies here too.
    """
    rows = _fetch_paginated_rows(service, site_url, start_date, end_date, dimensions=["page"])

    if not rows:
        return pd.DataFrame(columns=["page", "clicks", "impressions", "ctr", "position"])

    return pd.DataFrame(
        {
            "page": [row["keys"][0] for row in rows],
            "clicks": [int(row["clicks"]) for row in rows],
            "impressions": [int(row["impressions"]) for row in rows],
            "ctr": [float(row["ctr"]) for row in rows],
            "position": [float(row["position"]) for row in rows],
        }
    )


def fetch_overall_performance(service, site_url: str, start_date: date, end_date: date) -> dict:
    """Site-wide totals for one date range, with no dimension breakdown.

    This is the number that matches what Search Console's own overview
    chart shows. Query-level rows (fetch_query_performance) omit some
    low-volume/anonymized queries, so summing those would undercount —
    KPI cards must read totals from here instead.
    """
    request_body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dataState": DATA_STATE,
    }
    response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
    rows = response.get("rows", [])

    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}

    row = rows[0]
    return {
        "clicks": int(row.get("clicks", 0)),
        "impressions": int(row.get("impressions", 0)),
        "ctr": float(row.get("ctr", 0.0)),
        "position": float(row.get("position", 0.0)),
    }


def fetch_latest_complete_date(service, site_url: str, lookback_days: int = 14):
    """The newest date Google Search Console itself considers fully
    finalized. Unlike every other fetch here, this deliberately queries
    dataState="final" instead of the module-wide "all" — a day that's still
    preliminary simply doesn't appear in the response at all under "final",
    so MAX(date) over that response is an authoritative signal, not a guess.

    This is what preset date ranges (Last 7/28/90 Days) should anchor to —
    MAX(date) in our own storage includes fresh/preliminary days we keep on
    purpose so later syncs can revise them, which is a different thing.
    Returns None if no finalized data exists yet at all (e.g. a brand-new
    site with zero processed days).
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)
    request_body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "dimensions": ["date"],
        "dataState": "final",
    }
    response = service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
    rows = response.get("rows", [])
    if not rows:
        return None
    return date.fromisoformat(max(row["keys"][0] for row in rows))


def fetch_daily_breakdown(service, site_url: str, start_date: date, end_date: date, extra_dimension: str = None) -> pd.DataFrame:
    """Day-by-day performance for one site and date range, optionally broken
    down by one more dimension ("query", "page", "device", or "country").

    This is what gsc_sync.py uses for every table it syncs: extra_dimension
    =None gives the dimensionless daily total (for gsc_daily_overall);
    passing a dimension gives (date, dimension) pairs for the matching
    gsc_daily_* table. One function covers all five, since the API call
    shape is identical apart from the dimensions list.
    """
    dimensions = ["date"] if extra_dimension is None else ["date", extra_dimension]
    rows = _fetch_paginated_rows(service, site_url, start_date, end_date, dimensions=dimensions)

    columns = ["date", "clicks", "impressions", "ctr", "position"]
    if extra_dimension is not None:
        columns.insert(1, extra_dimension)

    if not rows:
        return pd.DataFrame(columns=columns)

    data = {
        "date": [row["keys"][0] for row in rows],
        "clicks": [int(row["clicks"]) for row in rows],
        "impressions": [int(row["impressions"]) for row in rows],
        "ctr": [float(row["ctr"]) for row in rows],
        "position": [float(row["position"]) for row in rows],
    }
    if extra_dimension is not None:
        data[extra_dimension] = [row["keys"][1] for row in rows]

    return pd.DataFrame(data, columns=columns)


def fetch_daily_performance(service, site_url: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Day-by-day site-wide clicks/impressions/ctr/position, for daily trend
    charts. Sourced from the API's `date` dimension directly — never derived
    by aggregating query-level rows, for the same undercount reason as above.
    """
    rows = _fetch_paginated_rows(service, site_url, start_date, end_date, dimensions=["date"])

    if not rows:
        return pd.DataFrame(columns=["date", "clicks", "impressions", "ctr", "position"])

    return pd.DataFrame(
        {
            "date": [row["keys"][0] for row in rows],
            "clicks": [int(row["clicks"]) for row in rows],
            "impressions": [int(row["impressions"]) for row in rows],
            "ctr": [float(row["ctr"]) for row in rows],
            "position": [float(row["position"]) for row in rows],
        }
    )
