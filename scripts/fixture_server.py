"""CPU-only realistic fixture dataset for UI tests and manual inspection."""

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
store.export(events)
server = create_server(store, port=0)
print(server.server_port, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
    store.close()
