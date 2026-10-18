"""Evidence-preserving timelines and explicit causal-path analysis."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from infertrace.events import Event, EventType


@dataclass(frozen=True)
class ClockAnchor:
    domain: str
    timestamp_ns: int
    unix_ns: int
    uncertainty_ns: int = 0

    def __post_init__(self) -> None:
        if self.uncertainty_ns < 0:
            raise ValueError("negative clock uncertainty")


def reconstruct(events: Sequence[Event], anchors: Sequence[ClockAnchor] = ()) -> dict[str, object]:
    """Never align clocks by receipt time. Unknown domains remain separate lanes."""
    clocks = {a.domain: a for a in anchors}
    if len(clocks) != len(anchors):
        raise ValueError("duplicate clock anchors")
    unique: dict[str, Event] = {}
    for event in events:
        if event.event_id in unique and unique[event.event_id] != event:
            raise ValueError("conflicting duplicate event ID")
        unique[event.event_id] = event
    ordered = sorted(unique.values(), key=lambda e: (e.clock_domain, e.timestamp_ns, e.event_id))
    rows: list[dict[str, object]] = []
    warnings: set[str] = set()

    def position(e: Event) -> tuple[str, int, int]:
        anchor = clocks.get(e.clock_domain)
        if anchor:
            return (
                "aligned:unix",
                e.timestamp_ns - anchor.timestamp_ns + anchor.unix_ns,
                anchor.uncertainty_ns,
            )
        return e.clock_domain, e.timestamp_ns, 0

    for e in ordered:
        domain, start, uncertainty = position(e)
        row: dict[str, object] = {
            **e.model_dump(mode="json"),
            "domain": domain,
            "start_ns": start,
            "end_ns": start,
            "uncertainty_ns": uncertainty,
            "annotations": list(e.missing),
        }
        rows.append(row)

    starts = {
        EventType.REQUEST_START: EventType.REQUEST_END,
        EventType.SESSION_START: EventType.SESSION_END,
        EventType.TURN_START: EventType.TURN_END,
        EventType.PHASE_START: EventType.PHASE_END,
    }
    pending: dict[tuple[str, ...], list[Event]] = defaultdict(list)
    intervals: list[dict[str, object]] = []
    reverse = {v: k for k, v in starts.items()}
    for e in ordered:
        kind = reverse.get(e.event_type, e.event_type)
        key = (
            e.trace_id,
            e.session_id,
            e.turn_id,
            e.request_id,
            e.span_id,
            e.source,
            e.clock_domain,
            e.phase or "",
            kind.value,
        )
        if e.event_type in starts:
            pending[key].append(e)
        elif e.event_type in reverse:
            if not pending[key]:
                warnings.add(f"unmatched-end:{e.event_id}")
                continue
            begin = pending[key].pop()
            domain, start, uncertainty = position(begin)
            _, end, _ = position(e)
            intervals.append(
                {
                    "event_id": begin.event_id,
                    "end_event_id": e.event_id,
                    "trace_id": e.trace_id,
                    "session_id": e.session_id,
                    "turn_id": e.turn_id,
                    "request_id": e.request_id,
                    "phase": e.phase or kind.value.split(".")[0],
                    "source": e.source,
                    "domain": domain,
                    "start_ns": start,
                    "end_ns": end,
                    "uncertainty_ns": uncertainty,
                    "provenance": begin.provenance,
                    "annotations": list(set(begin.missing + e.missing)),
                    "outcome": e.outcome,
                }
            )
    for values in pending.values():
        for e in values:
            warnings.add(f"missing-end:{e.event_id}")

    # Longest path uses only explicit causal parent edges, not timeline adjacency.
    visiting: set[str] = set()
    scores: dict[str, tuple[int, list[str]]] = {}

    def path(e: Event) -> tuple[int, list[str]]:
        if e.event_id in scores:
            return scores[e.event_id]
        if e.event_id in visiting:
            raise ValueError("causal cycle")
        visiting.add(e.event_id)
        best = (0, [e.event_id])
        if e.parent_event_id:
            parent = unique.get(e.parent_event_id)
            if not parent:
                warnings.add(f"missing-parent:{e.event_id}")
            elif (parent.trace_id, parent.session_id) != (e.trace_id, e.session_id):
                warnings.add(f"cross-trace-parent:{e.event_id}")
            else:
                score, chain = path(parent)
                pd, pt, pu = position(parent)
                cd, ct, cu = position(e)
                if pd != cd:
                    warnings.add(f"unaligned-causal-edge:{e.event_id}")
                elif ct - pt < pu + cu:
                    warnings.add(f"uncertain-causal-edge:{e.event_id}")
                else:
                    best = (score + ct - pt, chain + [e.event_id])
        visiting.remove(e.event_id)
        scores[e.event_id] = best
        return best

    for e in ordered:
        path(e)
    score, chain = max(scores.values(), key=lambda x: x[0], default=(0, []))
    return {
        "events": rows,
        "intervals": intervals,
        "warnings": sorted(warnings),
        "critical_path": {
            "duration_ns": score,
            "event_ids": chain,
            "basis": "explicit-causal-edges",
        },
        "clocks": [asdict(a) for a in anchors],
    }
