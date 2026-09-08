"""CRUD for manually-curated target keywords.

A target keyword is one we intentionally want to rank for, chosen by hand —
not to be confused with gsc_daily_query, which holds whatever people actually
searched for. This table just tracks the watchlist; performance stats for
each keyword are looked up from gsc_daily_query at display time.
"""

from datetime import datetime

import pandas as pd

from database.db_setup import get_connection


def add_target_keyword(keyword: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO target_keywords (keyword, created_at) VALUES (?, ?)
               ON CONFLICT(keyword) DO NOTHING""",
            (keyword.strip(), datetime.now().isoformat()),
        )


def list_target_keywords() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("SELECT id, keyword, created_at FROM target_keywords ORDER BY keyword", conn)


def delete_target_keyword(keyword_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM target_keywords WHERE id = ?", (int(keyword_id),))
