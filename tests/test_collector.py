import threading

import httpx
import pytest

from infertrace.adapters import HTTPExporter, parse_vllm_metrics
from infertrace.api import create_server
from infertrace.collector import Collector
from infertrace.events import Event, EventType, client_event
from infertrace.storage import EventStore
from infertrace.stream import StreamProtocolError, observe_completion, sse_payloads


def event():
    return client_event(EventType.REQUEST_START, clock_domain="test")


def test_persistence_idempotency_and_query(tmp_path):
    path = str(tmp_path / "events.db")
    e = event()
    store = EventStore(path)
    store.export([e, e])
    assert store.query(request_id=e.request_id) == [e]
    assert store.query(trace_id="' OR 1=1 --") == []
    store.close()
    store = EventStore(path)
    assert store.query() == [e]
    store.close()


def test_backpressure_and_hung_export():
    entered, release = threading.Event(), threading.Event()

    def blocked(batch):
        entered.set()
        release.wait(3)

    collector = Collector(blocked, capacity=2, batch_size=1)
    assert collector.emit(event())
    assert entered.wait(1)
    for _ in range(100):
        collector.emit(event())
    assert collector.stats().pending == 2
    assert collector.stats().dropped == 98
    assert not collector.close(timeout=0.01)
    assert not collector.emit(event())
    release.set()
    assert collector.close(timeout=1)


def test_failure_sampling_disabled():
    def broken(batch):
        raise ConnectionError("collector unavailable")

    collector = Collector(broken)
    collector.emit(event())
    assert collector.flush()
    assert collector.stats().export_errors == 1
    assert collector.stats().dropped == 1
    assert collector.close()
    collector = Collector(broken, sample_rate=0)
    assert not collector.emit(event())
    assert collector.stats().sampled_out == 1
    assert collector.close()
    disabled = Collector(broken, enabled=False)
    assert not disabled.emit(event())
    assert disabled._thread is None


def test_real_local_http_ingestion_query_and_outage(tmp_path):
    store = EventStore(str(tmp_path / "api.db"))
    server = create_server(store, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        exporter = HTTPExporter(base + "/events", timeout=0.2)
        e = event()
        exporter([e])
        with httpx.Client() as client:
            assert Event.from_json(client.get(base + "/events").text[1:-1]) == e
            assert client.post(base + "/events", json=[{"bad": 1}]).status_code == 400
            assert client.get(base + "/events?limit=-1").status_code == 400
            assert client.get(base + "/health").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        worker.join(1)
        store.close()
    collector = Collector(exporter)
    collector.emit(e)
    assert collector.flush()
    assert collector.stats().export_errors == 1
    assert collector.close()


@pytest.mark.parametrize(
    "body",
    [
        "data: {bad}\n\n",
        "data: []\n\n",
        'data: {"error":"oops"}\n\n',
        'data: {"choices":[{"text":"x"}]}\n\n',
    ],
)
def test_malformed_or_disconnected_stream(body):
    with pytest.raises(StreamProtocolError):
        list(
            observe_completion(
                base_url="http://mock/v1",
                model="m",
                prompt="private",
                transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body)),
            )
        )


def test_chat_stream_and_private_export():
    events = []
    c = Collector(lambda batch: events.extend(batch))

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer private-key"
        return httpx.Response(
            200,
            text=(
                ': heartbeat\n\ndata: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"private-response"}}]}\n\n'
                'data: {"usage":{}}\n\ndata: [DONE]\n\n'
            ),
        )

    chunks = list(
        observe_completion(
            base_url="http://mock/v1",
            model="m",
            prompt="private-prompt",
            chat=True,
            api_key="private-key",
            transport=httpx.MockTransport(handler),
            collector=c,
        )
    )
    assert c.flush()
    assert c.close()
    assert chunks[0].text == "private-response"
    assert [e.event_type for e in events] == [
        EventType.REQUEST_START,
        EventType.CLIENT_CHUNK,
        EventType.REQUEST_END,
    ]
    assert all("private" not in e.to_json() for e in events)
    assert events[-1].outcome == "ok"


def test_multiline_sse_and_limits():
    assert list(sse_payloads(iter(["data: {", 'data: "choices": []}', ""]))) == [
        '{\n"choices": []}'
    ]
    with pytest.raises(StreamProtocolError):
        list(sse_payloads(iter(["data: too big"]), max_event_chars=2))


def test_metrics_are_aggregate():
    events = parse_vllm_metrics(
        '# TYPE vllm:num_requests_running gauge\nvllm:num_requests_running{model_name="m"} 2\n',
        instance="mock",
    )
    assert len(events) == 1
    assert events[0].value == 2
    assert events[0].request_id == ""
    assert "request-attribution" in events[0].missing
