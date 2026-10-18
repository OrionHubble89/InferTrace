import threading
import tracemalloc

import httpx
import pytest

from infertrace.collector import Collector
from infertrace.events import EventType, client_event
from infertrace.stream import observe_completion


def test_disabled_fast_path_never_allocates_event_or_span(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled path called telemetry")

    monkeypatch.setattr("infertrace.stream.inference_request", forbidden)
    monkeypatch.setattr("infertrace.stream.client_event", forbidden)

    def handler(request):
        assert "traceparent" not in request.headers
        assert "x-request-id" not in request.headers
        return httpx.Response(200, text='data: {"choices":[{"text":"x"}]}\n\ndata: [DONE]\n\n')

    chunks = list(
        observe_completion(
            base_url="http://mock",
            model="m",
            prompt="x",
            enabled=False,
            transport=httpx.MockTransport(handler),
        )
    )
    assert chunks[0].text == "x"


def test_queue_memory_bound_with_unique_events():
    entered, release = threading.Event(), threading.Event()

    def blocked(batch):
        entered.set()
        release.wait(10)

    collector = Collector(blocked, capacity=8, batch_size=2, decision_capacity=16)
    collector.emit(client_event(EventType.REQUEST_START, clock_domain="test"))
    assert entered.wait(1)
    tracemalloc.start()
    try:
        for _ in range(3000):
            collector.emit(client_event(EventType.CLIENT_CHUNK, clock_domain="test"))
        current, peak = tracemalloc.get_traced_memory()
        assert collector.stats().pending <= 8
        assert len(collector._decisions) <= 16
        assert current < 2_000_000 and peak < 4_000_000
    finally:
        tracemalloc.stop()
        release.set()
        assert collector.close()


def test_adaptive_decisions_consistent_and_bounded():
    c = Collector(lambda _: None, adaptive=True, decision_capacity=2)
    try:
        first = client_event(EventType.REQUEST_START, clock_domain="t", trace_id="a" * 32)
        c.emit(first)
        decision = c._decisions[first.trace_id]
        for _ in range(10):
            c.emit(first)
            assert c._decisions[first.trace_id] == decision
        for trace_id in ["b" * 32, "c" * 32]:
            c.emit(client_event(EventType.REQUEST_START, clock_domain="t", trace_id=trace_id))
        assert len(c._decisions) == 2
    finally:
        assert c.close()


@pytest.mark.parametrize(
    "options",
    [
        {"capacity": 0},
        {"batch_size": 0},
        {"sample_rate": -1},
        {"interval": 0},
        {"decision_capacity": 0},
    ],
)
def test_invalid_limits(options):
    with pytest.raises(ValueError):
        Collector(lambda _: None, **options)
