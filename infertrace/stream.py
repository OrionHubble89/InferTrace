"""Observe client chunks, never infer engine tokens from HTTP framing."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from uuid import uuid4

import httpx
from opentelemetry import trace
from opentelemetry.propagate import inject

from infertrace.collector import Collector
from infertrace.events import EventType, client_event
from infertrace.tracing import current_identifiers, inference_request

_CLOCK = f"monotonic:{os.getpid()}:{uuid4().hex}"


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


class StreamProtocolError(ValueError):
    pass


def sse_payloads(lines: Iterator[str], max_event_chars: int = 1_048_576) -> Iterator[str]:
    data: list[str] = []
    size = 0
    for line in lines:
        if not line:
            if data:
                yield "\n".join(data)
                data, size = [], 0
        elif line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            size += len(value)
            if size > max_event_chars:
                raise StreamProtocolError("SSE event exceeds size limit")
            data.append(value)
    if data:
        yield "\n".join(data)


def observe_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int = 32,
    timeout: float = 120.0,
    transport: httpx.BaseTransport | None = None,
    collector: Collector | None = None,
    api_key: str | None = None,
    chat: bool = False,
    enabled: bool = True,
) -> Iterator[ChunkObservation]:
    """Close partially consumed iterators. Export contains no prompt/chunk text."""
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    url += "/chat/completions" if chat else "/completions"

    def emit(event_type: EventType, **fields: object) -> None:
        if enabled and collector is not None and collector.enabled:
            collector.emit(client_event(event_type, clock_domain=_CLOCK, **fields))

    with inference_request(model) if enabled else nullcontext(trace.INVALID_SPAN) as span:
        headers = {"Accept": "text/event-stream"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if enabled:
            inject(headers)
            headers["X-Request-ID"] = current_identifiers()["request_id"]
        started = time.perf_counter_ns()
        count = 0
        outcome = "incomplete"
        emit(EventType.REQUEST_START)
        payload: dict[str, object] = {"model": model, "max_tokens": max_tokens, "stream": True}
        payload.update(
            {"messages": [{"role": "user", "content": prompt}]} if chat else {"prompt": prompt}
        )
        try:
            with httpx.Client(timeout=timeout, transport=transport) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    done = False
                    for data in sse_payloads(response.iter_lines()):
                        if data == "[DONE]":
                            done = True
                            break
                        try:
                            event = json.loads(data)
                            if not isinstance(event, dict) or "error" in event:
                                raise StreamProtocolError("invalid streaming response")
                            choices = event.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            content = (
                                (choice.get("delta") or {}).get("content")
                                if chat
                                else choice.get("text")
                            )
                            if not content:
                                continue
                            if not isinstance(content, str):
                                raise StreamProtocolError("chunk content must be a string")
                        except (ValueError, KeyError, TypeError, AttributeError) as exc:
                            raise StreamProtocolError("malformed SSE payload") from exc
                        count += 1
                        emit(
                            EventType.CLIENT_CHUNK, sequence=count, missing=("engine-token-timing",)
                        )
                        yield ChunkObservation(
                            index=count,
                            elapsed_ns=time.perf_counter_ns() - started,
                            text=content,
                            **(current_identifiers() if enabled else {}),
                        )
                    if not done:
                        raise StreamProtocolError("stream ended before [DONE]")
            outcome = "ok"
        except GeneratorExit:
            outcome = "cancelled"
            raise
        except BaseException:
            outcome = "error"
            raise
        finally:
            span.set_attribute("infertrace.stream.chunk_count", count)
            emit(EventType.REQUEST_END, outcome=outcome)
