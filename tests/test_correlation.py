from dataclasses import replace

import pytest

from infertrace.correlation import ClockAnchor, reconstruct
from infertrace.events import Event, EventType


def e(id, time, kind=EventType.CLIENT_CHUNK, **kwargs):
    values = dict(
        event_id=id,
        event_type=kind,
        trace_id="a" * 32,
        span_id="b" * 16,
        session_id="s",
        turn_id="t",
        request_id="r",
        source="client",
        clock_domain="c1",
        timestamp_ns=time,
        observed_unix_ns=999,
        provenance="fixture",
    )
    values.update(kwargs)
    return Event(**values)


def test_overlapping_requests_and_partial_data():
    events = [
        e("a", 0, EventType.REQUEST_START),
        e("b", 2, EventType.REQUEST_START, request_id="r2"),
        e("c", 8, EventType.REQUEST_END),
        e("d", 10, EventType.REQUEST_END, request_id="r2"),
        e("missing", 12, EventType.REQUEST_START, request_id="r3"),
    ]
    result = reconstruct(events)
    assert [(i["start_ns"], i["end_ns"]) for i in result["intervals"]] == [(0, 8), (2, 10)]
    assert result["warnings"] == ["missing-end:missing"]
    assert reconstruct(list(reversed(events))) == result


def test_explicit_clock_mapping_and_causal_path():
    first = e("a", 10)
    second = e("b", 110, clock_domain="c2", parent_event_id="a")
    result = reconstruct([first, second])
    assert result["critical_path"]["duration_ns"] == 0
    assert result["warnings"] == ["unaligned-causal-edge:b"]
    result = reconstruct(
        [first, second], [ClockAnchor("c1", 0, 1000), ClockAnchor("c2", 100, 1010)]
    )
    assert result["critical_path"]["duration_ns"] == 10
    assert result["critical_path"]["event_ids"] == ["a", "b"]
    uncertain = reconstruct(
        [first, second], [ClockAnchor("c1", 0, 1000, 100), ClockAnchor("c2", 100, 1010, 100)]
    )
    assert uncertain["warnings"] == ["uncertain-causal-edge:b"]


def test_causal_cycle_duplicates_and_cross_trace():
    a = e("a", 1, parent_event_id="b")
    b = e("b", 2, parent_event_id="a")
    with pytest.raises(ValueError, match="cycle"):
        reconstruct([a, b])
    with pytest.raises(ValueError, match="conflicting"):
        reconstruct([a, e("a", 100)])
    assert len(reconstruct([a, a])["events"]) == 1
    other = e("b", 2, trace_id="c" * 32, parent_event_id="a")
    assert "cross-trace-parent:b" in reconstruct([e("a", 1), other])["warnings"]


def test_phase_data_and_unknown_end():
    result = reconstruct(
        [
            e("start", 10, EventType.PHASE_START, phase="prefill"),
            e("end", 20, EventType.PHASE_END, phase="prefill"),
            e("orphan", 30, EventType.REQUEST_END),
        ]
    )
    assert result["intervals"][0]["phase"] == "prefill"
    assert result["warnings"] == ["unmatched-end:orphan"]


def test_uncorrelated_batch_metrics_never_become_request_phases():
    metrics = e("metrics", 5, EventType.RESOURCE, source="metrics", request_id="")
    requests = [e("a", 0, EventType.REQUEST_START), e("b", 10, EventType.REQUEST_END)]
    result = reconstruct([metrics, *requests])
    assert len(result["intervals"]) == 1
    assert result["events"][1]["request_id"] == ""


def test_invalid_clock_anchor():
    with pytest.raises(ValueError):
        replace(ClockAnchor("c", 0, 0), uncertainty_ns=-1)
