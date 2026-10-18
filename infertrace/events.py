"""Versioned, strict event envelope. Telemetry never contains prompt/token text."""

from __future__ import annotations

import time
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from infertrace.tracing import current_identifiers


class EventType(str, Enum):
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    TURN_START = "turn.start"
    TURN_END = "turn.end"
    REQUEST_START = "request.start"
    REQUEST_END = "request.end"
    CLIENT_CHUNK = "client.chunk"
    ENGINE_TOKEN = "engine.token"
    SCHEDULER = "scheduler"
    KV = "kv"
    RESOURCE = "resource"
    PHASE_START = "phase.start"
    PHASE_END = "phase.end"


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=128)
    event_type: EventType
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    span_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    session_id: str = Field(max_length=128)
    turn_id: str = Field(max_length=128)
    request_id: str = Field(max_length=128)
    source: Literal["client", "engine", "metrics", "collector"]
    clock_domain: str = Field(min_length=1, max_length=128)
    timestamp_ns: int = Field(ge=0)
    observed_unix_ns: int = Field(ge=0)
    provenance: str = Field(min_length=1, max_length=256)
    missing: tuple[str, ...] = ()
    parent_event_id: str | None = Field(default=None, max_length=128)
    phase: Literal["queue", "prefill", "decode", "streaming", "tool"] | None = None
    sequence: int | None = Field(default=None, ge=0)
    value: float | None = Field(default=None, allow_inf_nan=False)
    metric_name: str | None = Field(default=None, max_length=128)
    outcome: Literal["ok", "error", "cancelled", "incomplete"] | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> Event:
        if self.event_type == EventType.ENGINE_TOKEN and self.source != "engine":
            raise ValueError("engine tokens require engine provenance")
        if self.event_type == EventType.CLIENT_CHUNK and self.source != "client":
            raise ValueError("client chunks require client provenance")
        if self.event_type in (EventType.PHASE_START, EventType.PHASE_END) and self.phase is None:
            raise ValueError("phase events require a phase")
        if self.source == "metrics" and self.request_id:
            raise ValueError("aggregate metrics cannot be attributed to a request")
        return self

    @classmethod
    def from_json(cls, data: str | bytes) -> Event:
        return cls.model_validate_json(data)

    def to_json(self) -> str:
        return self.model_dump_json()


def client_event(event_type: EventType, *, clock_domain: str, **fields: object) -> Event:
    data: dict[str, object] = {
        **current_identifiers(),
        "event_type": event_type,
        "source": "client",
        "clock_domain": clock_domain,
        "timestamp_ns": time.perf_counter_ns(),
        "observed_unix_ns": time.time_ns(),
        "provenance": "openai-compatible/http-client",
        **fields,
    }
    return Event.model_validate(data)
