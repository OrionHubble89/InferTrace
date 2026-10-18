"""Evidence-preserving timelines and explicit causal-path analysis."""

from __future__ import annotations

from collections import defaultdict, deque
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
    # Resolve explicit parent-span ancestry; never join by time proximity.
    by_parent: dict[tuple[str, str], list[Event]] = defaultdict(list)
    known: dict[tuple[str, str], set[tuple[str, str, str]]] = defaultdict(set)
    for event in unique.values():
        if event.trace_id == "0" * 32:
            continue
        if event.request_id:
            known[(event.trace_id, event.span_id)].add(
                (event.session_id, event.turn_id, event.request_id)
            )
        elif event.parent_span_id:
            by_parent[(event.trace_id, event.parent_span_id)].append(event)
    scopes = {key: next(iter(values)) for key, values in known.items() if len(values) == 1}
    todo = deque(scopes)
    while todo:
        scope_key = todo.popleft()
        for child in by_parent.get(scope_key, []):
            session, turn, request = scopes[scope_key]
            unique[child.event_id] = child.model_copy(
                update={
                    "session_id": child.session_id or session,
                    "turn_id": child.turn_id or turn,
                    "request_id": request,
                    "missing": tuple(m for m in child.missing if m != "request-attribution"),
                    "provenance": child.provenance + "/parent-span-join",
                }
            )
            child_key = child.trace_id, child.span_id
            if child_key not in scopes:
                scopes[child_key] = session, turn, request
                todo.append(child_key)
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
                    "model": begin.model,
                    "request_kind": begin.request_kind,
                    "operation_name": begin.operation_name,
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
    children: dict[str, list[Event]] = defaultdict(list)
    indegree = dict.fromkeys(unique, 0)
    for e in ordered:
        if not e.parent_event_id:
            continue
        parent = unique.get(e.parent_event_id)
        if parent is None:
            warnings.add(f"missing-parent:{e.event_id}")
        elif (parent.trace_id, parent.session_id) != (e.trace_id, e.session_id):
            warnings.add(f"cross-trace-parent:{e.event_id}")
        else:
            children[parent.event_id].append(e)
            indegree[e.event_id] += 1
    ready = deque(sorted(key for key, degree in indegree.items() if degree == 0))
    # Store predecessor pointers, not every prefix: linear memory on long traces.
    duration: dict[str, int] = dict.fromkeys(unique, 0)
    predecessor: dict[str, str] = {}
    visited = 0
    while ready:
        id = ready.popleft()
        parent = unique[id]
        visited += 1
        for e in children[id]:
            pd, pt, pu = position(parent)
            cd, ct, cu = position(e)
            if pd != cd:
                warnings.add(f"unaligned-causal-edge:{e.event_id}")
            elif ct - pt < pu + cu:
                warnings.add(f"uncertain-causal-edge:{e.event_id}")
            else:
                duration[e.event_id] = duration[id] + ct - pt
                predecessor[e.event_id] = id
            indegree[e.event_id] -= 1
            if indegree[e.event_id] == 0:
                ready.append(e.event_id)
    if visited != len(unique):
        raise ValueError("causal cycle")
    scores: dict[str, tuple[int, list[str]]] = {}
    if duration:
        best = max(sorted(duration), key=lambda key: duration[key])
        chain = [best]
        cursor = best
        while cursor in predecessor:
            cursor = predecessor[cursor]
            chain.append(cursor)
        scores[best] = duration[best], list(reversed(chain))
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
