"""SQLite schema creation and connection handling.

Every repository function opens and closes its own connection rather than
sharing one across the app, which keeps things safe with how Streamlit
reruns scripts on every interaction.
"""

import sqlite3

from utils.constants import DB_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    """Add a column to an existing table if it isn't there yet. Lets a
    database created by an earlier version of the app pick up new columns
    without the user having to delete and recreate it."""
    existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def initialize_database() -> None:
    """Create tables if they don't exist yet. Safe to call on every app start."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                total_clicks INTEGER,
                total_impressions INTEGER,
                overall_ctr REAL,
                overall_position REAL
            )
            """
        )
        # Site-wide totals from a dimension-less Search Console API call.
        # NULL for CSV-uploaded datasets, which have no such total available.
        _ensure_column(conn, "gsc_datasets", "total_clicks", "INTEGER")
        _ensure_column(conn, "gsc_datasets", "total_impressions", "INTEGER")
        _ensure_column(conn, "gsc_datasets", "overall_ctr", "REAL")
        _ensure_column(conn, "gsc_datasets", "overall_position", "REAL")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_query_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id INTEGER NOT NULL REFERENCES gsc_datasets(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_page_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id INTEGER NOT NULL REFERENCES gsc_datasets(id) ON DELETE CASCADE,
                page TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id INTEGER NOT NULL REFERENCES gsc_datasets(id) ON DELETE CASCADE,
                date TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seo_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_date TEXT NOT NULL,
                page_url TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                target_keyword TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # --- Daily-level tables: the auto-sync analytics model. ---
        # One row per calendar day (plus dimension, where applicable), so any
        # date range can be aggregated on demand instead of needing a
        # separately-fetched dataset per range. gsc_daily_overall is always
        # fetched with no dimensions and is the only source headline KPIs
        # read from, since dimensional breakdowns can undercount vs. it.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_overall (
                date TEXT PRIMARY KEY,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL,
                synced_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_query (
                date TEXT NOT NULL,
                query TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL,
                PRIMARY KEY (date, query)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_page (
                date TEXT NOT NULL,
                page TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL,
                PRIMARY KEY (date, page)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_device (
                date TEXT NOT NULL,
                device TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL,
                PRIMARY KEY (date, device)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_daily_country (
                date TEXT NOT NULL,
                country TEXT NOT NULL,
                clicks INTEGER NOT NULL,
                impressions INTEGER NOT NULL,
                ctr REAL NOT NULL,
                position REAL NOT NULL,
                PRIMARY KEY (date, country)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_synced_at TEXT
            )
            """
        )
        # The newest date Google itself considers fully finalized
        # (dataState="final"), as of the last sync. Deliberately distinct
        # from MAX(date) in gsc_daily_overall, which includes fresh/
        # preliminary days kept around so later syncs can revise them —
        # preset date ranges must anchor to this, not to storage freshness.
        _ensure_column(conn, "sync_state", "latest_complete_date", "TEXT")

        # Manually-curated keywords we want to rank for — distinct from the
        # actual search terms GSC reports in gsc_daily_query.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS target_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
