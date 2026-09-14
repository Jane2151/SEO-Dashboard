"""Cached Google OAuth token for the Search Console API, stored in the
shared database instead of a local file — a hosted deployment has no
persistent local disk, so the one-time interactive "Connect" flow (run
locally, since it needs a real browser) saves its result here, and every
deployment reads/refreshes it from the same place.
"""

from database.db_setup import get_connection


def get_token_json() -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT token_json FROM oauth_tokens WHERE id = 1").fetchone()
        return row["token_json"] if row else None


def save_token_json(token_json: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO oauth_tokens (id, token_json) VALUES (1, ?)
               ON CONFLICT (id) DO UPDATE SET token_json = excluded.token_json""",
            (token_json,),
        )


def delete_token() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM oauth_tokens WHERE id = 1")
