import httpx
import pytest
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from infertrace.stream import observe_completion
from infertrace.tracing import (
    current_correlation,
    inference_session,
    inference_turn,
    use_provider,
)


@pytest.fixture
def tracing():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    use_provider(provider)
    yield provider, exporter
    use_provider(None)
    provider.shutdown()


def test_actual_api_continuity(tracing):
    provider, exporter = tracing

    def handler(request):
        parent = extract(dict(request.headers))
        with provider.get_tracer("server").start_as_current_span("server", context=parent):
            return httpx.Response(200, text='data: {"choices":[{"text":"Hi"}]}\n\ndata: [DONE]\n\n')

    with inference_session("s") as session, inference_turn("s", "t"):
        chunks = list(
            observe_completion(
                base_url="http://mock",
                model="m",
                prompt="secret",
                transport=httpx.MockTransport(handler),
            )
        )
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert len(spans) == 4
    assert spans["infertrace.user.turn"].parent.span_id == session.get_span_context().span_id
    assert (
        spans["infertrace.request"].parent.span_id == spans["infertrace.user.turn"].context.span_id
    )
    assert spans["server"].parent.span_id == spans["infertrace.request"].context.span_id
    assert {s.context.trace_id for s in spans.values()} == {int(chunks[0].trace_id, 16)}
    assert (chunks[0].session_id, chunks[0].turn_id) == ("s", "t")
    assert chunks[0].request_id
    assert current_correlation().session_id == ""
    assert all("secret" not in str(s.attributes) for s in spans.values())


def test_http_error_marks_request(tracing):
    _, exporter = tracing
    with pytest.raises(httpx.HTTPStatusError):
        list(
            observe_completion(
                base_url="http://mock",
                model="m",
                prompt="x",
                transport=httpx.MockTransport(lambda _: httpx.Response(503)),
            )
        )
    assert exporter.get_finished_spans()[0].status.status_code == StatusCode.ERROR
    assert not trace.get_current_span().get_span_context().is_valid


def test_close_records_cancellation_and_restores_context(tracing):
    _, exporter = tracing
    stream = observe_completion(
        base_url="http://mock",
        model="m",
        prompt="x",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text='data: {"choices":[{"text":"Hi"}]}\n\n')
        ),
    )
    next(stream)
    stream.close()
    span = exporter.get_finished_spans()[0]
    assert span.attributes["infertrace.cancelled"] is True
    assert current_correlation().request_id == ""
