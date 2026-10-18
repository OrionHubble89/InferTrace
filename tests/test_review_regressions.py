"""Regression coverage for the nine implementation-review findings."""

import importlib.util
import json
import sqlite3
import threading
from contextlib import contextmanager

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from infertrace.adapters import parse_vllm_metrics, scrape_vllm_metrics
from infertrace.api import create_server
from infertrace.collector import Collector
from infertrace.config import Config
from infertrace.correlation import reconstruct
from infertrace.events import Event, EventType
from infertrace.otlp import parse_otlp_json
from infertrace.storage import EventStore
from infertrace.stream import observe_completion
from infertrace.tracing import (
    current_correlation,
    inference_session,
    inference_tool,
    inference_turn,
    use_provider,
)


def event(id, timestamp=10, kind=EventType.REQUEST_START, **updates):
    data = dict(
        event_id=id,
        event_type=kind,
        trace_id="a" * 32,
        span_id="b" * 16,
        session_id="session",
        turn_id="turn",
        request_id="request",
        source="client",
        clock_domain="test",
        timestamp_ns=timestamp,
        observed_unix_ns=100,
        provenance="regression",
    )
    data.update(updates)
    return Event(**data)


@pytest.fixture
def tracing():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    use_provider(provider)
    yield provider, exporter
    use_provider(None)
    provider.shutdown()


@contextmanager
def running_api(store):
    server = create_server(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def completion():
    return observe_completion(
        base_url="http://mock",
        model="m",
        prompt="x",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                text='data: {"choices":[{"text":"a"}]}\n\n'
                'data: {"choices":[{"text":"b"}]}\n\ndata: [DONE]\n\n',
            )
        ),
    )


@pytest.mark.parametrize("finish", ["exhaust", "close"])
def test_stream_preserves_each_consumers_context(tracing, finish):
    _, exporter = tracing
    with inference_turn("original", "original-turn") as parent:
        stream = completion()
        first = next(stream)
        with inference_turn("consumer", "consumer-turn") as consumer:
            second = next(stream)
            assert trace.get_current_span() is consumer
            assert current_correlation().session_id == "consumer"
            assert second.trace_id == first.trace_id
            assert second.session_id == "original"
            if finish == "close":
                stream.close()
            else:
                assert list(stream) == []
            assert trace.get_current_span() is consumer
            assert current_correlation().turn_id == "consumer-turn"
        assert trace.get_current_span() is parent
    request = next(s for s in exporter.get_finished_spans() if s.name == "infertrace.request")
    assert request.parent.span_id == parent.get_span_context().span_id


def test_stream_can_close_in_another_thread_without_context_token_errors(tracing):
    stream = completion()
    next(stream)
    errors = []

    def close():
        try:
            stream.close()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=close)
    thread.start()
    thread.join()
    assert errors == []
    assert not trace.get_current_span().get_span_context().is_valid


def test_lifecycle_includes_empty_turns_and_error_outcomes(tracing):
    events = []
    collector = Collector(lambda batch: events.extend(batch))
    try:
        with inference_session("session", collector=collector):
            with inference_turn("session", "empty-turn", collector=collector):
                pass
            with (
                pytest.raises(RuntimeError),
                inference_turn("session", "failed-turn", collector=collector),
            ):
                raise RuntimeError("operation failed")
        assert collector.flush()
        assert len(events) == 6
        timeline = reconstruct(events)
        assert len(timeline["intervals"]) == 3
        assert {e.event_type for e in events} == {
            EventType.SESSION_START,
            EventType.SESSION_END,
            EventType.TURN_START,
            EventType.TURN_END,
        }
        failed = next(
            e for e in events if e.turn_id == "failed-turn" and e.event_type == EventType.TURN_END
        )
        assert failed.outcome == "error"
        assert all(e.provenance == "infertrace/application-lifecycle" for e in events)
    finally:
        assert collector.close()


def test_disabled_lifecycle_allocates_no_spans_or_events(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled instrumentation executed")

    monkeypatch.setattr("infertrace.tracing._span", forbidden)
    monkeypatch.setattr("infertrace.tracing._emit_lifecycle", forbidden)
    with inference_session(enabled=False), inference_turn("s", "t", enabled=False):
        with inference_tool("search", enabled=False):
            pass


def test_disabled_example_never_configures_or_exports_tracing(monkeypatch):
    spec = importlib.util.spec_from_file_location("plug_example", "examples/plug_and_play.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_config", lambda _: Config(enabled=False))

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled example configured telemetry")

    monkeypatch.setattr(module, "configure_tracing", forbidden)
    monkeypatch.setattr(module, "inference_session", forbidden)
    monkeypatch.setattr(module, "inference_turn", forbidden)
    calls = []

    def observe(**kwargs):
        assert not kwargs["enabled"] and not kwargs["collector"].enabled
        calls.append(kwargs)
        yield from ()

    monkeypatch.setattr(module, "observe_completion", observe)
    monkeypatch.setattr("sys.argv", ["plug_and_play.py"])
    module.main()
    assert len(calls) == 1


def otlp_payload(end="200"):
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a" * 32,
                                "spanId": "c" * 16,
                                "parentSpanId": "b" * 16,
                                "startTimeUnixNano": "100",
                                "endTimeUnixNano": end,
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_otlp_retries_keep_first_receipt_but_reject_changed_span(tmp_path, monkeypatch):
    store = EventStore(str(tmp_path / "retry.db"))
    try:
        with running_api(store) as base, httpx.Client() as client:
            monkeypatch.setattr("infertrace.otlp.time.time_ns", lambda: 123)
            assert client.post(base + "/v1/traces", json=otlp_payload()).status_code == 200
            monkeypatch.setattr("infertrace.otlp.time.time_ns", lambda: 456)
            assert client.post(base + "/v1/traces", json=otlp_payload()).status_code == 200
            saved = store.query()
            assert len(saved) == 2 and all(e.observed_unix_ns == 123 for e in saved)
            assert client.post(base + "/v1/traces", json=otlp_payload("999")).status_code == 400
            assert store.query() == saved
    finally:
        store.close()


def test_parent_correlation_precedes_filters_and_page_selection(tmp_path):
    store = EventStore(str(tmp_path / "joins.db"))
    try:
        # Children arrive before their client parent; query-time resolution is arrival-independent.
        store.export(parse_otlp_json(otlp_payload()))
        store.export([event("parent")])
        with running_api(store) as base, httpx.Client() as client:
            for query in [
                "request_id=request",
                "session_id=session",
                "source=engine&request_id=request",
            ]:
                result = client.get(base + "/timeline?" + query + "&limit=1&order=latest").json()
                if "source=engine" in query:
                    assert result["pagination"]["total"] == 2
                    row = result["events"][0]
                    assert row["source"] == "engine" and row["request_id"] == "request"
                    assert "request-attribution" not in row["missing"]
                else:
                    assert result["pagination"]["total"] == 3
            result = client.get(base + "/timeline?request_id=request").json()
            assert sum(e["source"] == "engine" for e in result["events"]) == 2
    finally:
        store.close()


def test_conflicting_parent_scope_does_not_guess_request():
    store = EventStore(":memory:")
    try:
        store.export([event("p1"), event("p2", request_id="different")])
        store.export(parse_otlp_json(otlp_payload()))
        page = store.query_page(request_id="request", resolve=True)
        assert [e.event_id for e in page.events] == ["p1"]
    finally:
        store.close()


@pytest.mark.parametrize(
    "start,end,phase",
    [
        (EventType.REQUEST_START, EventType.REQUEST_END, None),
        (EventType.PHASE_START, EventType.PHASE_END, "prefill"),
        (EventType.SESSION_START, EventType.SESSION_END, None),
        (EventType.TURN_START, EventType.TURN_END, None),
    ],
)
def test_equal_timestamp_boundaries_pair_before_id_tiebreak(start, end, phase):
    events = [event("z-start", kind=start, phase=phase), event("a-end", kind=end, phase=phase)]
    for ordered in (events, list(reversed(events))):
        result = reconstruct(ordered)
        assert len(result["intervals"]) == 1
        assert result["intervals"][0]["start_ns"] == result["intervals"][0]["end_ns"]
        assert result["warnings"] == []


def test_latest_pagination_and_server_filters_beyond_ten_thousand(tmp_path):
    store = EventStore(str(tmp_path / "pages.db"))
    try:
        store.export(
            [event(f"old-{i}", timestamp=i, kind=EventType.CLIENT_CHUNK) for i in range(10001)]
        )
        store.export([event("new", timestamp=10002, session_id="new-session")])
        with running_api(store) as base, httpx.Client() as client:
            latest = client.get(base + "/timeline?order=latest&limit=2").json()
            assert latest["events"][-1]["event_id"] == "new"
            page = latest["pagination"]
            assert page["total"] == 10002 and page["has_more"]
            store.export([event("newer", timestamp=10003)])
            older = client.get(
                base + "/timeline",
                params={
                    "order": "latest",
                    "limit": 2,
                    "offset": 2,
                    "snapshot": page["snapshot"],
                },
            ).json()
            assert older["pagination"]["total"] == 10002
            assert not (
                {e["event_id"] for e in older["events"]} & {e["event_id"] for e in latest["events"]}
            )
            filtered = client.get(base + "/timeline?session_id=new-session").json()
            assert [e["event_id"] for e in filtered["events"]] == ["new"]
            assert any("partial-page" in w for w in latest["warnings"])
    finally:
        store.close()


def test_old_database_migrates_without_losing_payloads(tmp_path):
    path = str(tmp_path / "old.db")
    original = event("old")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, trace_id TEXT, session_id TEXT,"
            "request_id TEXT,timestamp_ns INTEGER,body TEXT)"
        )
        db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?)",
            (
                original.event_id,
                original.trace_id,
                original.session_id,
                original.request_id,
                original.timestamp_ns,
                original.to_json(),
            ),
        )
    store = EventStore(path)
    try:
        assert store.query() == [original]
        assert store.query_page(resolve=True).events == [original]
    finally:
        store.close()


@pytest.mark.parametrize("value", ["NaN", "+Inf", "-Inf"])
def test_non_finite_sample_preserves_valid_metrics_and_marks_missing(value):
    result = parse_vllm_metrics(f"vllm:valid 1\nvllm:unknown {value}\n", instance="test")
    assert result[0].value == 1
    assert result[1].value is None
    assert "non-finite-value" in result[1].missing
    assert json.loads(result[1].to_json())["value"] is None


class OversizedMetrics(httpx.SyncByteStream):
    def __init__(self):
        self.bytes_read = 0
        self.closed = False

    def __iter__(self):
        for _ in range(320):
            chunk = b"x" * 65536
            self.bytes_read += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


def test_metrics_limit_stops_reading_and_closes_response():
    stream = OversizedMetrics()
    with pytest.raises(ValueError, match="exceeds limit"):
        scrape_vllm_metrics(
            "http://mock",
            instance="test",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
        )
    assert stream.bytes_read <= 4_194_304 + 65536
    assert stream.closed


def test_exact_metrics_limit_is_accepted():
    # A large Prometheus comment is legal, so exercise an exactly-at-limit response.
    payload = b"#" + b"x" * (4_194_304 - 1)
    assert (
        scrape_vllm_metrics(
            "http://mock",
            instance="test",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload)),
        )
        == []
    )


def test_aggregate_metrics_never_inherit_request_scope():
    store = EventStore(":memory:")
    try:
        parent = event("client")
        metrics = event(
            "aggregate",
            kind=EventType.RESOURCE,
            source="metrics",
            request_id="",
            session_id="",
            turn_id="",
            span_id="c" * 16,
            parent_span_id=parent.span_id,
        )
        store.export([parent, metrics])
        rows = reconstruct([parent, metrics])["events"]
        assert next(e for e in rows if e["event_id"] == "aggregate")["request_id"] == ""
        resolved = store.query_page(resolve=True)
        aggregate = next(e for e in resolved.events if e.event_id == "aggregate")
        assert aggregate.request_id == ""
        filtered = store.query_page(resolve=True, request_id="request")
        assert [e.event_id for e in filtered.events] == ["client"]
    finally:
        store.close()


def test_deep_parent_ancestry_and_snapshot_do_not_mix_later_parents():
    store = EventStore(":memory:")
    try:
        parent = event("parent")
        child = event(
            "child",
            request_id="",
            session_id="",
            turn_id="",
            span_id="c" * 16,
            parent_span_id=parent.span_id,
            source="engine",
        )
        grandchild = event(
            "grandchild",
            request_id="",
            session_id="",
            turn_id="",
            span_id="d" * 16,
            parent_span_id=child.span_id,
            source="engine",
        )
        store.export([child, grandchild])
        old = store.query_page(resolve=True)
        store.export([parent])
        assert all(
            e.request_id == "" for e in store.query_page(resolve=True, snapshot=old.snapshot).events
        )
        page = store.query_page(resolve=True, request_id="request")
        assert {e.event_id for e in page.events} == {"parent", "child", "grandchild"}
    finally:
        store.close()


def test_abandoned_stream_finalizes_inside_its_own_context(tracing):
    import gc

    _, exporter = tracing
    with inference_turn("s", "t") as parent:
        stream = completion()
        next(stream)
        del stream
        gc.collect()
        assert trace.get_current_span() is parent
    request = next(s for s in exporter.get_finished_spans() if s.name == "infertrace.request")
    assert request.attributes["infertrace.cancelled"] is True


def test_disabled_stream_skips_context_copy(monkeypatch):
    def forbidden():
        raise AssertionError("disabled path copied context")

    monkeypatch.setattr("infertrace.iteration.copy_context", forbidden)
    stream = observe_completion(
        base_url="http://mock",
        model="m",
        prompt="x",
        enabled=False,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="data: [DONE]\n\n")),
    )
    assert list(stream) == []


def test_query_api_rejects_invalid_paging_parameters():
    store = EventStore(":memory:")
    try:
        with running_api(store) as base, httpx.Client() as client:
            for query in [
                "offset=999999999999999999999999",
                "snapshot=-1",
                "source=unknown",
                "order=unknown",
            ]:
                assert client.get(base + "/timeline?" + query).status_code == 400
    finally:
        store.close()
