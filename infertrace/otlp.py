"""OTLP/HTTP JSON trace adapter. Drops span content and retains correlation only."""

from __future__ import annotations

import time
from collections.abc import Mapping

from infertrace.events import Event, EventType


def parse_otlp_json(payload: Mapping[str, object]) -> list[Event]:
    """Read OTLP JSON's hex IDs/string nanoseconds. No token/phase inference.

    Only explicit infertrace correlation attributes are trusted for joins. vLLM
    spans lacking them remain trace-correlated but request attribution is missing.
    """
    events: list[Event] = []
    resources = payload.get("resourceSpans", [])
    if not isinstance(resources, list):
        raise ValueError("resourceSpans must be an array")
    for resource in resources:
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                if len(events) >= 2000:
                    raise ValueError("trace batch exceeds limit")
                attrs = {
                    a["key"]: a.get("value", {}).get("stringValue", "")
                    for a in span.get("attributes", [])
                    if a.get("key", "").startswith("infertrace.")
                }
                trace_id, span_id = span["traceId"], span["spanId"]
                missing = ["engine-token-timing", "engine-phase-timing"]
                request_id = attrs.get("infertrace.request_id", "")
                if not request_id:
                    missing.append("request-attribution")
                # Preserve each producer's clock domain, never align by trace ID.
                clock = attrs.get("infertrace.clock_domain", f"otlp:span:{trace_id}:{span_id}")
                for kind, timestamp in [
                    (EventType.REQUEST_START, int(span["startTimeUnixNano"])),
                    (EventType.REQUEST_END, int(span["endTimeUnixNano"])),
                ]:
                    events.append(
                        Event(
                            event_id=f"otlp:{trace_id}:{span_id}:{kind.value}",
                            event_type=kind,
                            trace_id=trace_id,
                            span_id=span_id,
                            parent_span_id=span.get("parentSpanId") or None,
                            session_id=attrs.get("infertrace.session_id", ""),
                            turn_id=attrs.get("infertrace.turn_id", ""),
                            request_id=request_id,
                            source="engine",
                            clock_domain=clock,
                            timestamp_ns=timestamp,
                            observed_unix_ns=time.time_ns(),
                            provenance="otlp-http-json/span-boundary",
                            missing=tuple(missing),
                        )
                    )
    return events
