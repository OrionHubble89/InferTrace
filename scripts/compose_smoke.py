"""Validate the CPU-only Compose install, event pipeline and exported Jaeger trace."""

import time

import httpx

with httpx.Client(timeout=5) as client:
    response = client.get("http://127.0.0.1:8080/timeline")
    response.raise_for_status()
    data = response.json()
    kinds = {e["event_type"] for e in data["events"]}
    assert {
        "session.start",
        "session.end",
        "turn.start",
        "turn.end",
        "request.start",
        "request.end",
        "client.chunk",
    } <= kinds
    assert {i["phase"] for i in data["intervals"]} >= {"session", "turn", "request"}
    assert data["pagination"]["total"] >= 8
    request_ids = {e["request_id"] for e in data["events"]}
    assert len(request_ids) >= 1
    assert any(e["event_type"] == "client.chunk" for e in data["events"])
    assert all(e["event_type"] != "engine.token" for e in data["events"])
    trace = data["events"][-1]["trace_id"]
    for _ in range(30):
        result = client.get(f"http://127.0.0.1:16686/api/traces/{trace}")
        if result.is_success and result.json().get("data"):
            spans = result.json()["data"][0]["spans"]
            assert {"infertrace.user.session", "infertrace.user.turn", "infertrace.request"} <= {
                s["operationName"] for s in spans
            }
            print("Compose: event pipeline, UI/API, mock endpoint and Jaeger passed")
            break
        time.sleep(1)
    else:
        raise AssertionError("trace did not reach Jaeger")
