"""OTel tracing bootstrap with optional OTLP exporter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter


def configure_tracing(
    service_name: str = "infertrace",
    *,
    otlp_endpoint: str | None = None,
    console: bool = False,
) -> TracerProvider:
    """Configure a process-global provider once, before other OTel setup.

    OTLP export is opt-in. Export occurs in a background batch processor.
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
    trace.set_tracer_provider(provider)
    return provider


@contextmanager
def inference_turn(session_id: str, turn_id: str) -> Iterator[trace.Span]:
    """Create a user-turn span; request spans become its descendants."""
    tracer = trace.get_tracer("infertrace")
    with tracer.start_as_current_span(
        "infertrace.user.turn",
        attributes={"infertrace.session_id": session_id, "infertrace.turn_id": turn_id},
    ) as span:
        yield span


@contextmanager
def inference_request(model: str) -> Iterator[trace.Span]:
    tracer = trace.get_tracer("infertrace")
    with tracer.start_as_current_span(
        "infertrace.request",
        attributes={"gen_ai.request.model": model},
    ) as span:
        yield span
