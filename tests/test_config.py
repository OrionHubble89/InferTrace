import json
import threading

import httpx
import pytest
from pydantic import ValidationError

from infertrace.adapters import HTTPExporter
from infertrace.api import create_server
from infertrace.collector import Collector
from infertrace.config import Config, discover, load_config
from infertrace.storage import EventStore
from infertrace.stream import observe_completion
from infertrace.tracing import configure_tracing, inference_session, inference_turn, use_provider


def test_config_env_and_validation(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"base_url": "http://mock/v1"}))
    monkeypatch.setenv("INFERTRACE_CONFIG", str(path))
    assert load_config().base_url == "http://mock/v1"
    for data in [{"base_url": "file:///secret"}, {"unknown": True}, {"capacity": 0}]:
        with pytest.raises(ValidationError):
            Config.model_validate(data)
    with pytest.raises(ValueError):
        Config(api_key_env="MISSING_SECRET").api_key()


def test_discovery_does_not_claim_engine_tokens():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "mock-model"}]})
        return httpx.Response(200, text="vllm:num_requests_running 1")

    import os

    os.environ["INFERTRACE_TEST_KEY"] = "test-key"
    try:
        result = discover(
            Config(base_url="http://mock/v1", api_key_env="INFERTRACE_TEST_KEY"),
            transport=httpx.MockTransport(handler),
        )
    finally:
        del os.environ["INFERTRACE_TEST_KEY"]
    assert result["models"] == ["mock-model"]
    assert result["metrics"] is True
    assert result["engine_tokens"] is False
    assert result["streaming"] == "configured-not-probed"


def test_discovery_degrades():
    result = discover(Config(), transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    assert result["metrics"] is False
    assert result["models_error"] == "unavailable-or-invalid"


def test_simulated_installation_end_to_end(tmp_path):
    store = EventStore(str(tmp_path / "installed.db"))
    server = create_server(store, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    collector = Collector(HTTPExporter(f"http://127.0.0.1:{server.server_port}/events"))
    provider = configure_tracing(install_global=False)
    try:
        with inference_session("session"), inference_turn("session", "turn"):
            chunks = list(
                observe_completion(
                    base_url="http://mock",
                    model="mock",
                    prompt="private",
                    collector=collector,
                    transport=httpx.MockTransport(
                        lambda _: httpx.Response(
                            200, text=('data: {"choices":[{"text":"x"}]}\n\ndata: [DONE]\n\n')
                        )
                    ),
                )
            )
        assert collector.flush()
        with httpx.Client() as client:
            timeline = client.get(f"http://127.0.0.1:{server.server_port}/timeline").json()
        assert len(timeline["events"]) == 3
        assert len(timeline["intervals"]) == 1
        assert {e["trace_id"] for e in timeline["events"]} == {chunks[0].trace_id}
        assert {e["request_id"] for e in timeline["events"]} == {chunks[0].request_id}
    finally:
        collector.close()
        server.shutdown()
        server.server_close()
        thread.join()
        store.close()
        use_provider(None)
        provider.shutdown()
