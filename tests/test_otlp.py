import pytest

from infertrace.correlation import reconstruct
from infertrace.otlp import parse_otlp_json


def payload(attributes=()):
    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a" * 32,
                                "spanId": "b" * 16,
                                "startTimeUnixNano": "100",
                                "endTimeUnixNano": "200",
                                "attributes": attributes,
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_otlp_span_boundaries_no_content_or_fake_tokens():
    events = parse_otlp_json(
        payload(
            [
                {"key": "infertrace.request_id", "value": {"stringValue": "request"}},
                {"key": "gen_ai.prompt", "value": {"stringValue": "secret"}},
            ]
        )
    )
    assert len(events) == 2
    assert all(e.request_id == "request" for e in events)
    assert all("secret" not in e.to_json() for e in events)
    assert reconstruct(events)["intervals"][0]["end_ns"] == 200


def test_uncorrelated_otlp_and_invalid():
    events = parse_otlp_json(payload())
    assert "request-attribution" in events[0].missing
    with pytest.raises((ValueError, TypeError)):
        parse_otlp_json({"resourceSpans": "invalid"})
