from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class AccessStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id INTEGER PRIMARY KEY,
                    expires_at TEXT NOT NULL,
                    note TEXT DEFAULT ''
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    playlist_url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS permanent_users (
                    user_id INTEGER PRIMARY KEY,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )

    def has_active_subscription(self, user_id: int) -> bool:
        now = datetime.now(UTC)
        with self._connect() as db:
            row = db.execute(
                "SELECT expires_at FROM subscriptions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return False
        return datetime.fromisoformat(row[0]) > now

    def grant_days(self, user_id: int, days: int, note: str = "") -> datetime:
        expires_at = datetime.now(UTC) + timedelta(days=days)
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO subscriptions (user_id, expires_at, note)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    note = excluded.note
                """,
                (user_id, expires_at.isoformat(), note),
            )
        return expires_at

    def revoke(self, user_id: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))

    def allow_forever(self, user_id: int, note: str = "") -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO permanent_users (user_id, note, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET note = excluded.note
                """,
                (user_id, note, datetime.now(UTC).isoformat()),
            )

    def unallow_forever(self, user_id: int) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM permanent_users WHERE user_id = ?", (user_id,))

    def is_allowed_forever(self, user_id: int) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT 1 FROM permanent_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row is not None

    def record_download(self, user_id: int, source_url: str, playlist_url: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO downloads (user_id, source_url, playlist_url, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, source_url, playlist_url, datetime.now(UTC).isoformat()),
            )


class AccessPolicy:
    def __init__(
        self,
        store: AccessStore,
        admin_user_ids: set[int],
        permanent_allowed_user_ids: set[int],
    ) -> None:
        self.store = store
        self.admin_user_ids = admin_user_ids
        self.permanent_allowed_user_ids = permanent_allowed_user_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids

    def can_use(self, user_id: int) -> bool:
        return (
            user_id in self.permanent_allowed_user_ids
            or self.is_admin(user_id)
            or self.store.is_allowed_forever(user_id)
            or self.store.has_active_subscription(user_id)
        )
