# Correlation
`reconstruct(events, anchors=())` returns individual observations, intervals,
warnings and a longest explicit causal path. Keys include trace, session, turn,
request, span, source, phase and clock domain; simultaneous requests retain their
overlap. Repeated starts pair in stack order, unmatched starts/ends are annotated.
Duplicate IDs are idempotent; conflicting duplicates and causal cycles are errors.

Unknown clocks remain separate domains. Optional explicit ClockAnchor offsets
map to a common Unix axis and carry uncertainty. Receipt wall time alone never
aligns clocks. No drift estimate is assumed; re-anchor data before analysis when
needed. Edges with unaligned/uncertain timing are excluded from duration sums.
Cross-trace parents are rejected with annotations.

Critical paths use only parent_event_id causal edges. Without such edges no
critical-path claim is possible. Metrics/chunk timing cannot prove engine phases,
token timing, GPU ownership or batch costs. Missing observations remain missing.
