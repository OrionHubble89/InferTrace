"""Optional public-interface adapters. Aggregate metrics remain unattributed."""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx
from prometheus_client.parser import text_string_to_metric_families

from infertrace.events import Event, EventType


class HTTPExporter:
    def __init__(self, endpoint: str, *, timeout: float = 2.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def __call__(self, events: Sequence[Event]) -> None:
        with httpx.Client(timeout=self.timeout) as client:
            batch: list[bytes] = []
            size = 2
            for event in events:
                encoded = event.to_json().encode()
                if (size + len(encoded) + 1 > 1_048_576 or len(batch) >= 1000) and batch:
                    self._send(client, batch)
                    batch, size = [], 2
                if len(encoded) + 2 > 1_048_576:
                    raise ValueError("event exceeds ingest limit")
                batch.append(encoded)
                size += len(encoded) + 1
            if batch:
                self._send(client, batch)

    def _send(self, client: httpx.Client, batch: list[bytes]) -> None:
        response = client.post(
            self.endpoint,
            content=b"[" + b",".join(batch) + b"]",
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()


def parse_vllm_metrics(payload: str, *, instance: str) -> list[Event]:
    """Parse public Prometheus exposition; no per-request/token inference."""
    now = time.time_ns()
    events = []
    for family in text_string_to_metric_families(payload):
        for sample in family.samples:
            if not sample.name.startswith("vllm:"):
                continue
            events.append(
                Event(
                    event_type=EventType.RESOURCE,
                    trace_id="0" * 32,
                    span_id="0" * 16,
                    session_id="",
                    turn_id="",
                    request_id="",
                    source="metrics",
                    clock_domain="unix:collector",
                    timestamp_ns=now,
                    observed_unix_ns=now,
                    provenance=f"vllm-prometheus:{instance}",
                    missing=("request-attribution", "engine-token-timing", "metric-labels"),
                    metric_name=sample.name,
                    value=float(sample.value),
                )
            )
    return events


def scrape_vllm_metrics(
    base_url: str,
    *,
    instance: str,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> list[Event]:
    with httpx.Client(timeout=timeout, transport=transport) as client:
        response = client.get(base_url.rstrip("/") + "/metrics")
        response.raise_for_status()
        if len(response.content) > 4_194_304:
            raise ValueError("metrics response exceeds limit")
        return parse_vllm_metrics(response.text, instance=instance)
