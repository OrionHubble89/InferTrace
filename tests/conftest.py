"""Tests are independent of the host's telemetry sampling policy."""

import pytest


@pytest.fixture(autouse=True)
def deterministic_otel(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_SAMPLER", "always_on")
    monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)
