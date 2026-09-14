"""Shared Postgres (Supabase) schema creation and connection handling.

Every repository function opens and closes its own connection rather than
sharing one across the app, which keeps things safe with how Streamlit
reruns scripts on every interaction. Local dev and every hosted deployment
all point at the same Supabase database via the DATABASE_URL secret, so
there's exactly one copy of the data no matter who's viewing it or where
the app is running.
"""

import psycopg2
import psycopg2.extras
import streamlit as st


class _CursorProxy:
    """Translates SQLite-style `?` placeholders to psycopg2's `%s` so the
    repository modules can keep the SQL they already had, and forwards
    everything else (fetchone, fetchall, description, ...) straight to the
    real psycopg2 cursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        translated = sql.replace("?", "%s")
        if params is None:
            return self._cursor.execute(translated)
        return self._cursor.execute(translated, params)

    def executemany(self, sql, seq_of_params):
        return self._cursor.executemany(sql.replace("?", "%s"), seq_of_params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class Connection:
    """Wraps a psycopg2 connection so repository code can keep using
    sqlite3-style conn.execute()/conn.executemany() with dict-like row
    access (row["column"]) instead of every call site needing its own
    cursor. `cursor()` — what pandas.read_sql_query calls internally —
    returns plain tuple rows, since that's the shape pandas expects;
    execute()/executemany() use dict rows instead, matching the
    sqlite3.Row behavior the repository code was originally written
    against.
    """

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def cursor(self, *args, **kwargs):
        return _CursorProxy(self._conn.cursor(*args, **kwargs))

    def execute(self, sql, params=()):
        cur = _CursorProxy(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = _CursorProxy(self._conn.cursor())
        cur.executemany(sql, seq_of_params)
        return cur

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()


def get_connection() -> Connection:
    return Connection(psycopg2.connect(st.secrets["DATABASE_URL"]))


def _ensure_column(conn: Connection, table: str, column: str, column_type: str) -> None:
    """Add a column to an existing table if it isn't there yet. Lets a
    database created by an earlier version of the app pick up new columns
    without anyone having to drop and recreate it."""
    existing_columns = {
        row["column_name"]
        for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)).fetchall()
    }
    if column not in existing_columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def initialize_database() -> None:
    """Create tables if they don't exist yet. Safe to call on every app start."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gsc_datasets (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                keyword TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )

        # Cached Google OAuth token for the Search Console API. A hosted
        # deployment has no persistent local disk, so the one-time "Connect"
        # flow (still run locally — it needs a real browser) saves its
        # result here instead of a local file, and every deployment
        # (including this same local machine) reads/refreshes it from here.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                token_json TEXT NOT NULL
            )
            """
        )
