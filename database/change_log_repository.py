"""CRUD access for manually recorded SEO change log entries."""

from datetime import date, datetime

import pandas as pd

from database.db_setup import get_connection


def add_change(
    change_date: date,
    page_url: str,
    category: str,
    description: str,
    target_keyword: str,
    notes: str,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO seo_changes
               (change_date, page_url, category, description, target_keyword, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                change_date.isoformat(),
                page_url,
                category,
                description,
                target_keyword,
                notes,
                datetime.now().isoformat(),
            ),
        )
        return cursor.fetchone()["id"]


def list_changes() -> pd.DataFrame:
    """All change log entries, most recent first."""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM seo_changes ORDER BY change_date DESC", conn)


def update_change(
    change_id: int,
    change_date: date,
    page_url: str,
    category: str,
    description: str,
    target_keyword: str,
    notes: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE seo_changes
               SET change_date = ?, page_url = ?, category = ?, description = ?, target_keyword = ?, notes = ?
               WHERE id = ?""",
            (change_date.isoformat(), page_url, category, description, target_keyword, notes, int(change_id)),
        )


def get_changes_in_range(start_date: date, end_date: date) -> pd.DataFrame:
    """SEO changes within a date range, for plotting as markers on the
    Overview trend graph. Ordered by date so same-day entries stay adjacent
    when the caller groups them into one marker."""
    with get_connection() as conn:
        return pd.read_sql_query(
            """SELECT change_date, category, description FROM seo_changes
               WHERE change_date BETWEEN ? AND ? ORDER BY change_date""",
            conn,
            params=(start_date.isoformat(), end_date.isoformat()),
        )


def delete_change(change_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM seo_changes WHERE id = ?", (int(change_id),))
