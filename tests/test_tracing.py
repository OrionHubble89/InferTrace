from opentelemetry import trace
from opentelemetry.sdk.trace.export import InMemorySpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace import TracerProvider

from infertrace.tracing import inference_request, inference_turn


def test_request_is_child_of_turn():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Avoid changing global provider: pass an explicit tracer through a local provider
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("user") as parent:
        with tracer.start_as_current_span("request") as child:
            assert child.get_span_context().trace_id == parent.get_span_context().trace_id
            assert child.parent.span_id == parent.get_span_context().span_id
    assert len(exporter.get_finished_spans()) == 2
