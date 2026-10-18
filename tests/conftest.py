"""Tests are independent of the host's telemetry sampling policy."""

import pytest


@pytest.fixture(autouse=True)
def deterministic_otel(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)

    # Isolate local mock HTTP tests from host proxy configuration.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
