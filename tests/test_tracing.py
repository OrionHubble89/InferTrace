from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider


def test_trace_parent_child_relationship():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("user") as parent:
        with tracer.start_as_current_span("request") as child:
            assert child.get_span_context().trace_id == parent.get_span_context().trace_id
            assert child.parent.span_id == parent.get_span_context().span_id
    assert len(exporter.get_finished_spans()) == 2
