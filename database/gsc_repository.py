"""CRUD access for uploaded Google Search Console datasets.

A "dataset" is one uploaded CSV export covering a specific date range. Storing
every upload (instead of only "current" and "previous") lets every dashboard
section pick whichever periods it needs from the same history.
"""

from datetime import date, datetime

import pandas as pd

from database.db_setup import get_connection


def _insert_query_rows(conn, dataset_id: int, query_df: pd.DataFrame) -> None:
    rows = [
        (dataset_id, row.query, int(row.clicks), int(row.impressions), float(row.ctr), float(row.position))
        for row in query_df.itertuples(index=False)
    ]
    conn.executemany(
        """INSERT INTO gsc_query_rows (dataset_id, query, clicks, impressions, ctr, position)
           VALUES (?, ?, ?, ?, ?, ?)""",
        rows,
    )


def save_dataset(query_df: pd.DataFrame, label: str, period_start: date, period_end: date) -> int:
    """Persist an uploaded, already-normalized GSC query export. Returns the new dataset id."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO gsc_datasets (label, period_start, period_end, uploaded_at) VALUES (?, ?, ?, ?)",
            (label, period_start.isoformat(), period_end.isoformat(), datetime.now().isoformat()),
        )
        dataset_id = cursor.lastrowid
        _insert_query_rows(conn, dataset_id, query_df)
        return dataset_id


def find_dataset_by_period(period_start: date, period_end: date):
    """Return the id of the dataset covering exactly this period_start/
    period_end, or None if no dataset covers exactly that period yet."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM gsc_datasets WHERE period_start = ? AND period_end = ?",
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchone()
        return row["id"] if row else None


def upsert_dataset(query_df: pd.DataFrame, label: str, period_start: date, period_end: date):
    """Save a dataset for period_start/period_end, replacing any existing
    dataset that already covers the exact same period instead of creating a
    duplicate. Used by the Search Console API fetch flow, where re-fetching
    the same range (e.g. once GSC's data finalizes a few days later) is
    expected and shouldn't clutter the dataset history.

    Returns (dataset_id, was_replaced). On replace, the old query/daily rows
    and overall totals are cleared — callers must re-save overall totals and
    daily rows afterward, as the fetch flow does.
    """
    existing_id = find_dataset_by_period(period_start, period_end)
    if existing_id is None:
        return save_dataset(query_df, label, period_start, period_end), False

    with get_connection() as conn:
        conn.execute("DELETE FROM gsc_query_rows WHERE dataset_id = ?", (existing_id,))
        conn.execute("DELETE FROM gsc_daily_rows WHERE dataset_id = ?", (existing_id,))
        conn.execute("DELETE FROM gsc_page_rows WHERE dataset_id = ?", (existing_id,))
        conn.execute(
            """UPDATE gsc_datasets
               SET label = ?, uploaded_at = ?, total_clicks = NULL, total_impressions = NULL,
                   overall_ctr = NULL, overall_position = NULL
               WHERE id = ?""",
            (label, datetime.now().isoformat(), existing_id),
        )
        _insert_query_rows(conn, existing_id, query_df)
        return existing_id, True


def list_datasets() -> pd.DataFrame:
    """All uploaded datasets, most recent period first. total_clicks /
    total_impressions / overall_ctr / overall_position are populated only for
    datasets fetched via the Search Console API (NULL for CSV uploads)."""
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT id, label, period_start, period_end, uploaded_at,
                      total_clicks, total_impressions, overall_ctr, overall_position
               FROM gsc_datasets ORDER BY period_end DESC""",
            conn,
        )


def get_dataset_rows(dataset_id: int) -> pd.DataFrame:
    """Query-level rows for one dataset."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT query, clicks, impressions, ctr, position FROM gsc_query_rows WHERE dataset_id = ?",
            conn,
            params=(int(dataset_id),),
        )


def save_overall_totals(dataset_id: int, clicks: int, impressions: int, ctr: float, position: float) -> None:
    """Store the site-wide totals for a dataset, from a dimension-less
    Search Console API call. Only ever called for API-fetched datasets."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE gsc_datasets
               SET total_clicks = ?, total_impressions = ?, overall_ctr = ?, overall_position = ?
               WHERE id = ?""",
            (int(clicks), int(impressions), float(ctr), float(position), int(dataset_id)),
        )


def save_daily_rows(dataset_id: int, daily_df: pd.DataFrame) -> None:
    """Persist day-by-day performance for a dataset (API-fetched only)."""
    with get_connection() as conn:
        rows = [
            (int(dataset_id), row.date, int(row.clicks), int(row.impressions), float(row.ctr), float(row.position))
            for row in daily_df.itertuples(index=False)
        ]
        conn.executemany(
            "INSERT INTO gsc_daily_rows (dataset_id, date, clicks, impressions, ctr, position) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )


def get_all_daily_rows() -> pd.DataFrame:
    """Daily rows across every dataset that has them, for the daily trend
    chart. Empty when no dataset has been fetched via the API yet."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT date, clicks, impressions, ctr, position FROM gsc_daily_rows ORDER BY date",
            conn,
        )


def save_page_rows(dataset_id: int, page_df: pd.DataFrame) -> None:
    """Persist page-level performance for a dataset (API-fetched only). Used
    by the Page Performance page to track a page's history across periods."""
    with get_connection() as conn:
        rows = [
            (int(dataset_id), row.page, int(row.clicks), int(row.impressions), float(row.ctr), float(row.position))
            for row in page_df.itertuples(index=False)
        ]
        conn.executemany(
            "INSERT INTO gsc_page_rows (dataset_id, page, clicks, impressions, ctr, position) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )


def get_page_rows(dataset_id: int) -> pd.DataFrame:
    """Page-level rows for one dataset. Empty for a dataset with no
    page-level data (e.g. a CSV upload, which never captures this)."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT page, clicks, impressions, ctr, position FROM gsc_page_rows WHERE dataset_id = ?",
            conn,
            params=(int(dataset_id),),
        )


def list_known_pages() -> list:
    """Distinct page URLs with any saved page-level data, across every
    dataset. Powers the Page Performance page's page selector."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT page FROM gsc_page_rows ORDER BY page").fetchall()
        return [row["page"] for row in rows]


def get_page_history(page_url: str) -> pd.DataFrame:
    """All saved page-level rows for one exact page URL, joined with each
    dataset's period info, ordered oldest to newest by period end. Powers
    the Page Performance page's current-metrics snapshot and trend chart —
    independent of any before/after pairing."""
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT d.id AS dataset_id, d.label, d.period_start, d.period_end,
                      p.clicks, p.impressions, p.ctr, p.position
               FROM gsc_page_rows p
               JOIN gsc_datasets d ON d.id = p.dataset_id
               WHERE p.page = ?
               ORDER BY d.period_end ASC""",
            conn,
            params=(page_url,),
        )


def get_latest_two_datasets():
    """Return (current, previous) dataset metadata as pandas Series, sorted by
    period end date. `previous` is None when fewer than two datasets exist."""
    datasets = list_datasets()
    if datasets.empty:
        return None, None
    if len(datasets) == 1:
        return datasets.iloc[0], None
    return datasets.iloc[0], datasets.iloc[1]


def get_dataset_before_and_after(change_date: date):
    """Find the dataset ending closest before change_date ("before") and the
    dataset starting closest after change_date ("after"). Either can be None
    if no such dataset has been uploaded yet."""
    datasets = list_datasets()
    if datasets.empty:
        return None, None

    datasets = datasets.copy()
    datasets["period_start"] = pd.to_datetime(datasets["period_start"])
    datasets["period_end"] = pd.to_datetime(datasets["period_end"])
    change_ts = pd.Timestamp(change_date)

    before_candidates = datasets[datasets["period_end"] < change_ts].sort_values("period_end", ascending=False)
    after_candidates = datasets[datasets["period_start"] >= change_ts].sort_values("period_start", ascending=True)

    before = before_candidates.iloc[0] if not before_candidates.empty else None
    after = after_candidates.iloc[0] if not after_candidates.empty else None
    return before, after


def delete_dataset(dataset_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM gsc_datasets WHERE id = ?", (int(dataset_id),))
