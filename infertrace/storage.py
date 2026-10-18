"""Atomic SQLite event storage and indexed, ancestry-aware paginated queries."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass

from infertrace.events import Event

_SCOPE_CTE = """
WITH RECURSIVE scope_candidates(trace_id, span_id, session_id, turn_id, request_id) AS (
    SELECT DISTINCT trace_id, span_id, session_id, turn_id, request_id
    FROM events WHERE rowid <= ? AND request_id != ''
      AND trace_id != '00000000000000000000000000000000'
    UNION
    SELECT e.trace_id, e.span_id,
           COALESCE(NULLIF(e.session_id, ''), p.session_id),
           COALESCE(NULLIF(e.turn_id, ''), p.turn_id), p.request_id
    FROM events e JOIN scope_candidates p
      ON e.trace_id = p.trace_id AND e.parent_span_id = p.span_id
    WHERE e.rowid <= ? AND e.request_id = '' AND e.source != 'metrics'
),
scopes AS (
    SELECT trace_id, span_id, MIN(session_id) AS session_id, MIN(turn_id) AS turn_id,
           MIN(request_id) AS request_id
    FROM scope_candidates GROUP BY trace_id, span_id HAVING COUNT(*) = 1
)
"""


@dataclass(frozen=True)
class EventPage:
    events: list[Event]
    total: int
    snapshot: int
    offset: int
    limit: int

    def metadata(self) -> dict[str, int | bool | None]:
        more = self.offset + len(self.events) < self.total
        return {
            "total": self.total,
            "snapshot": self.snapshot,
            "offset": self.offset,
            "limit": self.limit,
            "has_more": more,
            "next_offset": self.offset + len(self.events) if more else None,
        }


class EventStore:
    def __init__(self, path: str = "infertrace.db"):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("BEGIN")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events "
            "(event_id TEXT PRIMARY KEY, trace_id TEXT, session_id TEXT, request_id TEXT, "
            "timestamp_ns INTEGER, body TEXT)"
        )
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(events)")}
        added = False
        for field, declaration in {
            "span_id": "TEXT NOT NULL DEFAULT ''",
            "parent_span_id": "TEXT",
            "turn_id": "TEXT NOT NULL DEFAULT ''",
            "source": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if field not in columns:
                self._db.execute(f"ALTER TABLE events ADD COLUMN {field} {declaration}")
                added = True
        if added:
            # Migrate existing MVP databases, preserving all IDs and original payloads.
            for id, body in self._db.execute("SELECT event_id, body FROM events"):
                e = Event.from_json(body)
                self._db.execute(
                    "UPDATE events SET span_id=?, parent_span_id=?, turn_id=?, source=? "
                    "WHERE event_id=?",
                    (e.span_id, e.parent_span_id, e.turn_id, e.source, id),
                )
        for field in ("trace_id", "session_id", "request_id", "source"):
            self._db.execute(f"CREATE INDEX IF NOT EXISTS idx_{field} ON events({field})")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_span ON events(trace_id, span_id)")
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_parent ON events(trace_id, parent_span_id)"
        )
        self._db.commit()

    @staticmethod
    def _identity(event: Event) -> dict[str, object]:
        # OTLP receipt time describes ingestion, not the immutable upstream span.
        # Exact retries retain the first stored receipt time; content changes still fail.
        ignored = (
            {"observed_unix_ns"}
            if event.event_id.startswith("otlp:")
            and (event.provenance == "otlp-http-json/span-boundary")
            else set()
        )
        return event.model_dump(exclude=ignored)

    def export(self, events: Sequence[Event]) -> None:
        with self._lock, self._db:
            seen: dict[str, Event] = {}
            for event in events:
                if event.event_id in seen and self._identity(
                    seen[event.event_id]
                ) != self._identity(event):
                    raise ValueError("conflicting duplicate event ID")
                seen[event.event_id] = event
                existing = self._db.execute(
                    "SELECT body FROM events WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if existing and self._identity(Event.from_json(existing[0])) != self._identity(
                    event
                ):
                    raise ValueError("conflicting duplicate event ID")
            self._db.executemany(
                "INSERT OR IGNORE INTO events "
                "(event_id,trace_id,session_id,request_id,timestamp_ns,body,"
                "span_id,parent_span_id,turn_id,source) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        e.event_id,
                        e.trace_id,
                        e.session_id,
                        e.request_id,
                        e.timestamp_ns,
                        e.to_json(),
                        e.span_id,
                        e.parent_span_id,
                        e.turn_id,
                        e.source,
                    )
                    for e in events
                ],
            )

    def query_page(
        self,
        *,
        trace_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        source: str | None = None,
        limit: int = 1000,
        offset: int = 0,
        latest: bool = False,
        snapshot: int | None = None,
        resolve: bool = False,
    ) -> EventPage:
        if (
            not 1 <= limit <= 10000
            or not 0 <= offset <= 2**63 - 1
            or (snapshot is not None and not 0 <= snapshot <= 2**63 - 1)
        ):
            raise ValueError("invalid pagination")
        if source is not None and source not in ("client", "engine", "metrics", "collector"):
            raise ValueError("invalid source")
        prefix = _SCOPE_CTE if resolve else ""
        join = (
            "LEFT JOIN scopes s ON e.trace_id=s.trace_id AND e.span_id=s.span_id" if resolve else ""
        )
        scope_fields = {
            field: (
                f"CASE WHEN e.source='metrics' THEN e.{field} "
                f"ELSE COALESCE(NULLIF(e.{field},''),s.{field},'') END"
                if resolve
                else f"e.{field}"
            )
            for field in ("session_id", "turn_id", "request_id")
        }
        filters: list[str] = []
        parameters: list[str | int] = []
        for expression, value in [
            ("e.trace_id", trace_id),
            (scope_fields["session_id"], session_id),
            (scope_fields["request_id"], request_id),
            ("e.source", source),
        ]:
            if value is not None:
                filters.append(expression + "=?")
                parameters.append(value)
        with self._lock:
            if snapshot is None:
                snapshot = self._db.execute("SELECT COALESCE(MAX(rowid),0) FROM events").fetchone()[
                    0
                ]
            filters.append("e.rowid <= ?")
            parameters.append(snapshot)
            # Use positional parameters throughout the recursive CTE.
            prefix_parameters = [snapshot, snapshot] if resolve else []
            where = " AND ".join(filters)
            base = f"FROM events e {join} WHERE {where}"
            total = self._db.execute(
                prefix + f" SELECT COUNT(*) {base}", [*prefix_parameters, *parameters]
            ).fetchone()[0]
            selected = ",".join(scope_fields.values())
            order = "e.rowid DESC" if latest else "e.timestamp_ns, e.event_id"
            rows = self._db.execute(
                prefix + f" SELECT e.body,{selected} {base} ORDER BY {order} LIMIT ? OFFSET ?",
                [*prefix_parameters, *parameters, limit, offset],
            ).fetchall()
        events = []
        for body, session, turn, request in rows:
            event = Event.from_json(body)
            if resolve and not event.request_id and request:
                event = event.model_copy(
                    update={
                        "session_id": session,
                        "turn_id": turn,
                        "request_id": request,
                        "missing": tuple(m for m in event.missing if m != "request-attribution"),
                        "provenance": event.provenance + "/parent-span-join",
                    }
                )
            events.append(event)
        return EventPage(events, total, snapshot, offset, limit)

    def query(
        self,
        *,
        trace_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Event]:
        return self.query_page(
            trace_id=trace_id,
            session_id=session_id,
            request_id=request_id,
            limit=limit,
            offset=offset,
        ).events

    def close(self) -> None:
        with self._lock:
            self._db.close()
