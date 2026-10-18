import json

import pytest
from pydantic import ValidationError

from infertrace.events import Event, EventType, client_event


def example(**updates):
    return Event(
        event_type=EventType.CLIENT_CHUNK,
        trace_id="a" * 32,
        span_id="b" * 16,
        session_id="s",
        turn_id="t",
        request_id="r",
        source="client",
        clock_domain="client:process-1",
        timestamp_ns=12,
        observed_unix_ns=100,
        provenance="fixture",
        **updates,
    )


def test_roundtrip_and_fixture():
    event = example(sequence=1, missing=("engine-token-timing",))
    assert Event.from_json(event.to_json()) == event
    fixture = Event.from_json(open("tests/fixtures/client-chunk.json").read())
    assert fixture.event_type == EventType.CLIENT_CHUNK


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": "2.0"},
        {"unexpected": 1},
        {"trace_id": "bad"},
        {"timestamp_ns": -1},
        {"timestamp_ns": "1"},
        {"value": float("inf")},
        {"event_type": "engine.token"},
        {"source": "engine"},
        {"event_type": "phase.start"},
        {"source": "metrics"},
    ],
)
def test_invalid_envelopes(patch):
    data = json.loads(example().to_json())
    data.update(patch)
    with pytest.raises(ValidationError):
        Event.from_json(json.dumps(data))


def test_client_factory():
    event = client_event(EventType.REQUEST_START, clock_domain="local")
    assert event.timestamp_ns > 0
    assert event.trace_id == "0" * 32  # explicit absence of an active OTel span
