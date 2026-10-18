"""Observe OpenAI-compatible SSE streaming without modifying the engine.

Each observation represents a received HTTP streaming *chunk*, not an engine token.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Iterator

import httpx
from opentelemetry import trace
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
    """Yield client-observed chunks from /v1/completions.

    The request span is scoped to stream consumption. Caller must fully consume
    or close the generator to end the span.
    """
    url = base_url.rstrip("/") + "/v1/completions"
    with inference_request(model) as span:
        headers = {"Accept": "text/event-stream"}
        inject(headers)
        started = time.perf_counter_ns()
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
                    text = choices[0].get("text") or ""
                    if not text:
                        continue
                    observation = ChunkObservation(
                        index=span.attributes.get("infertrace.chunk_count", 0) if False else 0,
                        elapsed_ns=time.perf_counter_ns() - started,
                        text=text,
                    )
                    yield observation
