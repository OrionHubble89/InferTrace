"""SQLite event log: atomic idempotent batches and bounded parameterized queries."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence

from infertrace.events import Event


class EventStore:
    def __init__(self, path: str = "infertrace.db"):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events "
            "(event_id TEXT PRIMARY KEY, trace_id TEXT, session_id TEXT, request_id TEXT, "
            "timestamp_ns INTEGER, body TEXT)"
        )
        for field in ("trace_id", "session_id", "request_id"):
            self._db.execute(f"CREATE INDEX IF NOT EXISTS idx_{field} ON events({field})")
        self._db.commit()

    def export(self, events: Sequence[Event]) -> None:
        with self._lock, self._db:
            seen: dict[str, str] = {}
            for event in events:
                body = event.to_json()
                if event.event_id in seen and seen[event.event_id] != body:
                    raise ValueError("conflicting duplicate event ID")
                seen[event.event_id] = body
                existing = self._db.execute(
                    "SELECT body FROM events WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if existing and existing[0] != body:
                    raise ValueError("conflicting duplicate event ID")
            self._db.executemany(
                "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        e.event_id,
                        e.trace_id,
                        e.session_id,
                        e.request_id,
                        e.timestamp_ns,
                        e.to_json(),
                    )
                    for e in events
                ],
            )

    def query(
        self,
        *,
        trace_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Event]:
        if not 1 <= limit <= 10000 or offset < 0:
            raise ValueError("invalid pagination")
        filters = {
            k: v
            for k, v in {
                "trace_id": trace_id,
                "session_id": session_id,
                "request_id": request_id,
            }.items()
            if v is not None
        }
        where = " AND ".join(f"{k}=?" for k in filters) or "1=1"
        with self._lock:
            rows = self._db.execute(
                f"SELECT body FROM events WHERE {where} "
                "ORDER BY timestamp_ns, event_id LIMIT ? OFFSET ?",
                [*filters.values(), limit, offset],
            ).fetchall()
        return [Event.from_json(row[0]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
