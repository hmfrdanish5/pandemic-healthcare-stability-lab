"""SQLite + JSON-backed public comments (no accounts)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone

MAX_NAME_LEN = 60
MAX_COMMENT_LEN = 500

_DIR = os.path.join(os.path.dirname(__file__), "data")
_DB_NAME = "comments.db"
_JSON_NAME = "comments.json"


def _db_path() -> str:
    os.makedirs(_DIR, exist_ok=True)
    return os.path.join(_DIR, _DB_NAME)


def _json_path() -> str:
    os.makedirs(_DIR, exist_ok=True)
    return os.path.join(_DIR, _JSON_NAME)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                comment_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                owner_token_hash TEXT
            )
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(comments)").fetchall()}
        if "updated_at" not in cols:
            conn.execute("ALTER TABLE comments ADD COLUMN updated_at TEXT")
        if "owner_token_hash" not in cols:
            conn.execute("ALTER TABLE comments ADD COLUMN owner_token_hash TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                client_key TEXT PRIMARY KEY,
                last_post REAL NOT NULL
            )
        """)
    _restore_from_json_if_empty()
    _write_json_backup()


def _restore_from_json_if_empty() -> None:
    path = _json_path()
    if not os.path.isfile(path):
        return
    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        if n:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return
        rows = payload.get("comments") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO comments (id, display_name, comment_text, created_at, updated_at, owner_token_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row.get("id"),
                    row.get("display_name") or "anonymous",
                    row.get("comment_text") or "",
                    row.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    row.get("updated_at"),
                    row.get("owner_token_hash"),
                ),
            )


def _write_json_backup() -> None:
    """Durable copy so comments survive if the SQLite file is wiped or gitignored."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, display_name, comment_text, created_at, updated_at, owner_token_hash "
            "FROM comments ORDER BY id ASC"
        ).fetchall()
    payload = {
        "comments": [dict(r) for r in rows],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _json_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def _public_row(row: sqlite3.Row | dict, owned: bool = False) -> dict:
    item = dict(row)
    item.pop("owner_token_hash", None)
    item["owned"] = owned
    return item


def list_comments(limit: int = 100, owner_hashes: list[str] | None = None) -> list[dict]:
    hashes = set(owner_hashes or [])
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, display_name, comment_text, created_at, updated_at, owner_token_hash "
            "FROM comments ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        owned = bool(r["owner_token_hash"] and r["owner_token_hash"] in hashes)
        out.append(_public_row(r, owned=owned))
    return out


def add_comment(display_name: str, comment_text: str) -> dict:
    name = display_name.strip()
    text = comment_text.strip()

    if not name:
        raise ValueError("Display name is required.")
    if not text:
        raise ValueError("Comment text is required.")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"Display name must be at most {MAX_NAME_LEN} characters.")
    if len(text) > MAX_COMMENT_LEN:
        raise ValueError(f"Comment must be at most {MAX_COMMENT_LEN} characters.")

    created = datetime.now(timezone.utc).isoformat()
    token = secrets.token_urlsafe(18)
    token_hash = _hash_token(token)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO comments (display_name, comment_text, created_at, updated_at, owner_token_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, text, created, created, token_hash),
        )
        comment_id = cur.lastrowid
    _write_json_backup()
    return {
        "id": comment_id,
        "display_name": name,
        "comment_text": text,
        "created_at": created,
        "updated_at": created,
        "owner_token": token,
        "owned": True,
        "note": "Keep this token to edit or delete this comment. It is shown once.",
    }


def _require_owner(comment_id: int, token: str) -> sqlite3.Row:
    if not token or not str(token).strip():
        raise PermissionError("Owner token is required.")
    token_hash = _hash_token(str(token).strip())
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM comments WHERE id = ?", (comment_id,)
        ).fetchone()
    if row is None:
        raise KeyError("Comment not found.")
    stored = row["owner_token_hash"]
    if not stored or not hmac.compare_digest(stored, token_hash):
        raise PermissionError("Invalid owner token.")
    return row


def update_comment(comment_id: int, token: str, comment_text: str) -> dict:
    text = comment_text.strip()
    if not text:
        raise ValueError("Comment text is required.")
    if len(text) > MAX_COMMENT_LEN:
        raise ValueError(f"Comment must be at most {MAX_COMMENT_LEN} characters.")
    _require_owner(comment_id, token)
    updated = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE comments SET comment_text = ?, updated_at = ? WHERE id = ?",
            (text, updated, comment_id),
        )
        row = conn.execute(
            "SELECT id, display_name, comment_text, created_at, updated_at FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone()
    _write_json_backup()
    out = dict(row)
    out["owned"] = True
    return out


def delete_own_comment(comment_id: int, token: str) -> bool:
    _require_owner(comment_id, token)
    with _connect() as conn:
        cur = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        ok = cur.rowcount > 0
    if ok:
        _write_json_backup()
    return ok


def delete_comment(comment_id: int) -> bool:
    """Admin delete (no owner token)."""
    with _connect() as conn:
        cur = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        ok = cur.rowcount > 0
    if ok:
        _write_json_backup()
    return ok


def hashes_from_tokens(tokens: list[str]) -> list[str]:
    return [_hash_token(t) for t in tokens if t]


def add_feedback(display_name: str, message_text: str) -> dict:
    name = display_name.strip()
    text = message_text.strip()

    if not name:
        raise ValueError("Name is required.")
    if not text:
        raise ValueError("Message is required.")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"Name must be at most {MAX_NAME_LEN} characters.")
    if len(text) > MAX_COMMENT_LEN:
        raise ValueError(f"Message must be at most {MAX_COMMENT_LEN} characters.")

    created = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO feedback (display_name, message_text, created_at) VALUES (?, ?, ?)",
            (name, text, created),
        )
        feedback_id = cur.lastrowid
    return {"id": feedback_id, "status": "sent", "created_at": created}
