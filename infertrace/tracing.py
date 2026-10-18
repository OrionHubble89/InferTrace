"""Explicit OTel lifecycle and correlation contexts; no import-time side effects."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from infertrace.collector import Collector

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode


@dataclass(frozen=True)
class Correlation:
    session_id: str = ""
    turn_id: str = ""
    request_id: str = ""


_correlation: ContextVar[Correlation | None] = ContextVar("infertrace.correlation", default=None)
_provider: trace.TracerProvider | None = None
CLOCK_DOMAIN = f"monotonic:{os.getpid()}:{uuid4().hex}"


def configure_tracing(
    service_name: str = "infertrace",
    *,
    otlp_endpoint: str | None = None,
    console: bool = False,
    install_global: bool = True,
) -> TracerProvider:
    """Return an owned provider. Caller must shutdown it on application exit.

    Never silently replace an application's global provider. For embedded use,
    pass install_global=False; InferTrace uses the returned provider internally.
    """
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=otlp_endpoint, insecure=otlp_endpoint.startswith("http://")
                )
            )
        )
    if console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    use_provider(provider)
    if install_global:
        trace.set_tracer_provider(provider)
    return provider


def use_provider(provider: trace.TracerProvider | None) -> None:
    """Use an application-owned provider, or None to use the global provider."""
    global _provider
    _provider = provider


def current_correlation() -> Correlation:
    return _correlation.get() or Correlation()


def current_identifiers() -> dict[str, str]:
    context = trace.get_current_span().get_span_context()
    c = current_correlation()
    return {
        "trace_id": format(context.trace_id, "032x"),
        "span_id": format(context.span_id, "016x"),
        "session_id": c.session_id,
        "turn_id": c.turn_id,
        "request_id": c.request_id,
    }


@contextmanager
def _span(name: str, correlation: Correlation, **attributes: str) -> Iterator[trace.Span]:
    token = _correlation.set(correlation)
    tracer = trace.get_tracer("infertrace", tracer_provider=_provider)
    attrs = {f"infertrace.{k}": v for k, v in vars(correlation).items() if v}
    attrs.update(attributes)
    try:
        with tracer.start_as_current_span(name, attributes=attrs) as span:
            try:
                yield span
            except GeneratorExit:
                span.set_attribute("infertrace.cancelled", True)
                raise
            except BaseException as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
    finally:
        _correlation.reset(token)


@contextmanager
def inference_session(session_id: str | None = None) -> Iterator[trace.Span]:
    with _span("infertrace.user.session", Correlation(session_id or uuid4().hex)) as span:
        yield span


@contextmanager
def inference_turn(session_id: str, turn_id: str) -> Iterator[trace.Span]:
    with _span("infertrace.user.turn", Correlation(session_id, turn_id)) as span:
        yield span


@contextmanager
def inference_request(model: str, request_id: str | None = None) -> Iterator[trace.Span]:
    c = replace(current_correlation(), request_id=request_id or uuid4().hex)
    with _span("infertrace.request", c, **{"gen_ai.request.model": model}) as span:
        yield span


@contextmanager
def consumer_context(context: otel_context.Context, correlation: Correlation) -> Iterator[None]:
    """Suspend instrumentation context while a streaming caller consumes a chunk."""
    token = otel_context.attach(context)
    correlation_token = _correlation.set(correlation)
    try:
        yield
    finally:
        _correlation.reset(correlation_token)
        otel_context.detach(token)


@contextmanager
def inference_tool(name: str, collector: Collector | None = None) -> Iterator[trace.Span]:
    """Observe a caller-selected tool operation without recording inputs/outputs."""
    from infertrace.events import EventType, client_event

    c = replace(current_correlation(), request_id=uuid4().hex)
    clock = CLOCK_DOMAIN

    def emit(kind: EventType, outcome: str | None = None) -> None:
        if collector is not None and collector.enabled:
            try:
                collector.emit(
                    client_event(
                        kind,
                        clock_domain=clock,
                        phase="tool",
                        request_kind="tool",
                        operation_name=name,
                        outcome=outcome,
                    )
                )
            except (ValueError, TypeError):
                collector.record_drop()

    with _span("infertrace.tool", c, **{"infertrace.tool.name": name}) as span:
        outcome = "error"
        emit(EventType.PHASE_START)
        try:
            yield span
            outcome = "ok"
        finally:
            emit(EventType.PHASE_END, outcome)
