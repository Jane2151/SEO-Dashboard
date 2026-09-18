"""Daily-level GSC data access — the auto-sync analytics model.

Unlike gsc_repository.py (one row per manually fetched date range), this
stores one row per calendar day, so any date range can be aggregated on
demand via a simple WHERE date BETWEEN ... AND ... All writes are upserts
keyed by date (or date + dimension), so re-syncing never creates duplicates
and always overwrites with Google's latest reported value.
"""

from datetime import date, datetime, timezone

import pandas as pd

from database.db_setup import get_connection


def _upsert_dimension_table(table: str, dimension_column: str, df: pd.DataFrame) -> None:
    """Shared upsert for the four (date, dimension) tables — query/page/
    device/country all have the identical shape and conflict key."""
    if df.empty:
        return
    with get_connection() as conn:
        rows = [
            (row.date, getattr(row, dimension_column), int(row.clicks), int(row.impressions), float(row.ctr), float(row.position))
            for row in df.itertuples(index=False)
        ]
        conn.executemany(
            f"""INSERT INTO {table} (date, {dimension_column}, clicks, impressions, ctr, position)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, {dimension_column}) DO UPDATE SET
                    clicks = excluded.clicks,
                    impressions = excluded.impressions,
                    ctr = excluded.ctr,
                    position = excluded.position""",
            rows,
        )


def upsert_daily_overall(df: pd.DataFrame) -> None:
    """Upsert dimensionless daily totals — the only source headline KPIs
    should ever read from."""
    if df.empty:
        return
    synced_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        rows = [
            (row.date, int(row.clicks), int(row.impressions), float(row.ctr), float(row.position), synced_at)
            for row in df.itertuples(index=False)
        ]
        conn.executemany(
            """INSERT INTO gsc_daily_overall (date, clicks, impressions, ctr, position, synced_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   clicks = excluded.clicks,
                   impressions = excluded.impressions,
                   ctr = excluded.ctr,
                   position = excluded.position,
                   synced_at = excluded.synced_at""",
            rows,
        )


def upsert_daily_query(df: pd.DataFrame) -> None:
    _upsert_dimension_table("gsc_daily_query", "query", df)


def upsert_daily_page(df: pd.DataFrame) -> None:
    _upsert_dimension_table("gsc_daily_page", "page", df)


def upsert_daily_device(df: pd.DataFrame) -> None:
    _upsert_dimension_table("gsc_daily_device", "device", df)


def upsert_daily_country(df: pd.DataFrame) -> None:
    _upsert_dimension_table("gsc_daily_country", "country", df)


def get_daily_overall_range(start_date: date, end_date: date) -> pd.DataFrame:
    """Daily overall rows for a date range — powers KPI cards and trend
    charts. Aggregate with data_processing.metrics (SUM/SUM CTR,
    impression-weighted position), never a plain average."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT date, clicks, impressions, ctr, position FROM gsc_daily_overall WHERE date BETWEEN ? AND ? ORDER BY date",
            conn,
            params=(start_date.isoformat(), end_date.isoformat()),
        )


def _get_dimension_breakdown(table: str, dimension_column: str, start_date: date, end_date: date, limit: int) -> pd.DataFrame:
    """Shared range-aggregation query for query/page/device/country —
    correctly SUMs clicks/impressions, derives CTR as SUM/SUM (never
    AVG(daily_ctr)), and position as impression-weighted."""
    with get_connection() as conn:
        return pd.read_sql_query(
            f"""SELECT {dimension_column},
                       SUM(clicks) AS clicks,
                       SUM(impressions) AS impressions,
                       CASE WHEN SUM(impressions) > 0 THEN SUM(clicks) * 1.0 / SUM(impressions) ELSE 0 END AS ctr,
                       CASE WHEN SUM(impressions) > 0 THEN SUM(position * impressions) * 1.0 / SUM(impressions) ELSE 0 END AS position
                FROM {table}
                WHERE date BETWEEN ? AND ?
                GROUP BY {dimension_column}
                ORDER BY clicks DESC
                LIMIT ?""",
            conn,
            params=(start_date.isoformat(), end_date.isoformat(), limit),
        )


def get_query_breakdown(start_date: date, end_date: date, limit: int = 20) -> pd.DataFrame:
    return _get_dimension_breakdown("gsc_daily_query", "query", start_date, end_date, limit)


def get_page_breakdown(start_date: date, end_date: date, limit: int = 20) -> pd.DataFrame:
    return _get_dimension_breakdown("gsc_daily_page", "page", start_date, end_date, limit)


def get_device_breakdown(start_date: date, end_date: date, limit: int = 10) -> pd.DataFrame:
    return _get_dimension_breakdown("gsc_daily_device", "device", start_date, end_date, limit)


def get_country_breakdown(start_date: date, end_date: date, limit: int = 20) -> pd.DataFrame:
    return _get_dimension_breakdown("gsc_daily_country", "country", start_date, end_date, limit)


def get_query_stats(query_text: str, start_date: date, end_date: date) -> dict:
    """Aggregate clicks/impressions/ctr/position for one exact query (case-
    insensitive) over a date range. Powers target keyword cards — a target
    keyword's stats come from the same daily rows as the query breakdown
    table, just filtered to one query instead of grouped by all of them."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                      CASE WHEN SUM(impressions) > 0 THEN SUM(clicks) * 1.0 / SUM(impressions) ELSE 0 END AS ctr,
                      CASE WHEN SUM(impressions) > 0 THEN SUM(position * impressions) * 1.0 / SUM(impressions) ELSE 0 END AS position
               FROM gsc_daily_query
               WHERE LOWER(query) = LOWER(?) AND date BETWEEN ? AND ?""",
            (query_text.strip(), start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
        return {
            "clicks": int(row["clicks"] or 0),
            "impressions": int(row["impressions"] or 0),
            "ctr": float(row["ctr"] or 0.0),
            "position": float(row["position"] or 0.0),
        }


def get_query_daily_position(query_text: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Day-by-day position for one exact query (case-insensitive) — powers
    the per-target-keyword lines on the Overview position chart. Sparse: a
    day the query had no impressions simply has no row here, same as GSC
    itself omits it from the API response that day."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT date, position FROM gsc_daily_query WHERE LOWER(query) = LOWER(?) AND date BETWEEN ? AND ? ORDER BY date",
            conn,
            params=(query_text.strip(), start_date.isoformat(), end_date.isoformat()),
        )


def get_latest_synced_date():
    """Most recent date with any daily-overall data, or None if never synced."""
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(date) AS max_date FROM gsc_daily_overall").fetchone()
        return date.fromisoformat(row["max_date"]) if row and row["max_date"] else None


def get_earliest_synced_date():
    """Oldest date with any daily-overall data, or None if never synced."""
    with get_connection() as conn:
        row = conn.execute("SELECT MIN(date) AS min_date FROM gsc_daily_overall").fetchone()
        return date.fromisoformat(row["min_date"]) if row and row["min_date"] else None


def get_last_sync_time():
    """ISO timestamp of the last successful sync, or None if never synced."""
    with get_connection() as conn:
        row = conn.execute("SELECT last_synced_at FROM sync_state WHERE id = 1").fetchone()
        return row["last_synced_at"] if row else None


def get_latest_complete_date():
    """Latest date GSC itself considers fully finalized (dataState="final"),
    as of the last sync. NOT the same as get_latest_synced_date() (MAX(date)
    in our own storage), which includes fresh/preliminary days on purpose —
    preset date ranges must anchor to this instead, or they silently include
    a day GSC's own standard reporting doesn't consider complete yet.
    Returns None if no sync has recorded one yet."""
    with get_connection() as conn:
        row = conn.execute("SELECT latest_complete_date FROM sync_state WHERE id = 1").fetchone()
        if row is None or row["latest_complete_date"] is None:
            return None
        return date.fromisoformat(row["latest_complete_date"])


def set_latest_complete_date(complete_date: date) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sync_state (id, latest_complete_date) VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET latest_complete_date = excluded.latest_complete_date""",
            (complete_date.isoformat(),),
        )


def set_last_sync_time() -> None:
    """Records the sync time in UTC (unambiguous regardless of which
    timezone the server process happens to run in — local dev machine or
    Streamlit Cloud's container) — callers convert to the viewer's own
    timezone for display via utils.time_format."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sync_state (id, last_synced_at) VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET last_synced_at = excluded.last_synced_at""",
            (datetime.now(timezone.utc).isoformat(),),
        )
