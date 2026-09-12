"""SQLite-backed per-client rate limiting (process-shared, low-traffic demo use)."""

from __future__ import annotations

import os
import sqlite3
import time

from comments_store import _connect


def check_rate_limit(client_key: str, min_interval_s: float) -> bool:
    """
    Return True if the request is allowed, False if inside the cooldown window.

    Uses the same SQLite database as comments so multiple workers on one host
    share limits. This is suitable for low-traffic portfolio hosting, not
    distributed anti-abuse.
    """
    now = time.monotonic()
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limits (
                client_key TEXT PRIMARY KEY,
                last_post REAL NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT last_post FROM rate_limits WHERE client_key = ?",
            (client_key,),
        ).fetchone()
        if row is not None and now - float(row["last_post"]) < min_interval_s:
            return False
        conn.execute(
            "INSERT OR REPLACE INTO rate_limits (client_key, last_post) VALUES (?, ?)",
            (client_key, now),
        )
    return True


def reset_rate_limit(client_key: str) -> None:
    """Test helper: clear cooldown for a client key."""
    with _connect() as conn:
        conn.execute("DELETE FROM rate_limits WHERE client_key = ?", (client_key,))
