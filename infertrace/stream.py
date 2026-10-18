"""Observe OpenAI-compatible SSE streaming without engine modifications.

Observations are client-received chunks, not necessarily model tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Iterator

import httpx
from opentelemetry.propagate import inject

from infertrace.tracing import inference_request


@dataclass(frozen=True)
class ChunkObservation:
    index: int
    elapsed_ns: int
    text: str


def observe_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 32,
    timeout: float = 120.0,
) -> Iterator[ChunkObservation]:
    """Yield received chunks; close/consume iterator to finish the span."""
    url = base_url.rstrip("/") + "/v1/completions"
    with inference_request(model) as span:
        headers = {"Accept": "text/event-stream"}
        inject(headers)
        started = time.perf_counter_ns()
        count = 0
        with httpx.Client(timeout=timeout) as client:
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
                    )
        span.set_attribute("infertrace.stream.chunk_count", count)
