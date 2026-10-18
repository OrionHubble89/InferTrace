"""CPU-only realistic fixture dataset for UI tests and manual inspection."""

import os

from infertrace.api import create_server
from infertrace.events import Event, EventType
from infertrace.storage import EventStore

store = EventStore(":memory:")
events = []
for n in range(2):
    for id, ts, kind, source, phase in [
        ("start", 0, EventType.REQUEST_START, "client", None),
        ("prefill-start", 1, EventType.PHASE_START, "engine", "prefill"),
        ("prefill-end", 3, EventType.PHASE_END, "engine", "prefill"),
        ("chunk", 4, EventType.CLIENT_CHUNK, "client", None),
        ("token", 5, EventType.ENGINE_TOKEN, "engine", None),
        ("end", 10, EventType.REQUEST_END, "client", None),
    ]:
        events.append(
            Event(
                event_id=f"{n}-{id}",
                event_type=kind,
                trace_id="a" * 32,
                span_id="b" * 16,
                session_id="session-demo",
                turn_id=f"turn-{n}",
                request_id=f"request-{n}",
                source=source,
                clock_domain="fixture-clock",
                timestamp_ns=(ts + n * 2) * 1_000_000,
                observed_unix_ns=0,
                provenance="synthetic-fixture",
                phase=phase,
                missing=("engine-token-timing",) if source == "client" else (),
            )
        )
if os.getenv("UI_LARGE_FIXTURE") == "1":
    store.export(
        [
            Event(
                event_id=f"historical-{i}",
                event_type=EventType.CLIENT_CHUNK,
                trace_id="d" * 32,
                span_id="e" * 16,
                session_id="historical-session",
                turn_id="historical-turn",
                request_id="historical-request",
                source="client",
                clock_domain="fixture-clock",
                timestamp_ns=i,
                observed_unix_ns=0,
                provenance="synthetic-fixture",
            )
            for i in range(10005)
        ]
    )
for kind, ts, span in [
    (EventType.SESSION_START, 0, "1" * 16),
    (EventType.SESSION_END, 15_000_000, "1" * 16),
]:
    events.append(
        Event(
            event_id=kind.value,
            event_type=kind,
            trace_id="a" * 32,
            span_id=span,
            session_id="session-demo",
            turn_id="",
            request_id="",
            source="client",
            clock_domain="fixture-clock",
            timestamp_ns=ts,
            observed_unix_ns=0,
            provenance="synthetic-fixture",
        )
    )
for n in range(2):
    for kind, ts in [
        (EventType.TURN_START, n * 2_000_000),
        (EventType.TURN_END, 12_000_000 + n * 2_000_000),
    ]:
        events.append(
            Event(
                event_id=f"turn-{n}-{kind.value}",
                event_type=kind,
                trace_id="a" * 32,
                span_id=str(n + 2) * 16,
                session_id="session-demo",
                turn_id=f"turn-{n}",
                request_id="",
                source="client",
                clock_domain="fixture-clock",
                timestamp_ns=ts,
                observed_unix_ns=0,
                provenance="synthetic-fixture",
            )
        )
store.export(events)
server = create_server(store, port=0)
print(server.server_port, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    store.close()
