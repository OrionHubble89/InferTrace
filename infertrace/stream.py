"""Observe OpenAI-compatible SSE streaming without engine modifications.

Observations are client-received chunks, not necessarily model tokens.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
from opentelemetry.propagate import inject

from infertrace.tracing import current_identifiers, inference_request


@dataclass(frozen=True)
class ChunkObservation:
    index: int
    elapsed_ns: int
    text: str
    trace_id: str = ""
    span_id: str = ""
    session_id: str = ""
    turn_id: str = ""
    request_id: str = ""


def observe_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 32,
    timeout: float = 120.0,
    transport: httpx.BaseTransport | None = None,
) -> Iterator[ChunkObservation]:
    """Yield received chunks; close/consume iterator to finish the span."""
    url = base_url.rstrip("/") + "/v1/completions"
    with inference_request(model) as span:
        headers = {"Accept": "text/event-stream"}
        inject(headers)
        started = time.perf_counter_ns()
        count = 0
        with httpx.Client(timeout=timeout, transport=transport) as client:
            with client.stream(
                "POST",
                url,
                headers=headers,
                json={"model": model, "prompt": prompt, "max_tokens": max_tokens, "stream": True},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    content = choices[0].get("text") or ""
                    if not content:
                        continue
                    count += 1
                    yield ChunkObservation(
                        index=count,
                        elapsed_ns=time.perf_counter_ns() - started,
                        text=content,
                        **current_identifiers(),
                    )
        span.set_attribute("infertrace.stream.chunk_count", count)
