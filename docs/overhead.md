# Bounded telemetry, not a zero-cost claim
`observe_completion(enabled=False)` skips tracing, propagation, event allocation
and collection. A disabled Collector creates no worker thread and emit returns
immediately. Enabled producers do no network/disk export. Queue capacity and batch
size bound retained work; schema string/tuple bounds limit event payload size.
Sampling-decision LRU memory is capped by decision_capacity.

Adaptive sampling is opt-in: pressure lowers admission probability for new
traces. Decisions remain consistent while in the bounded LRU; long/evicted traces
may get a new decision. Queue overflow can still create partial traces. Always
inspect drop, sampled_out and export_errors counters. Export failures drop their
batch. There are no unbounded retries. This is best-effort telemetry.

CPU benchmark reproduction:
```sh
PYTHONPATH=. python scripts/cpu_benchmark.py
```
Raw results: cpu-microbenchmark.json. This measures emit on a preallocated event,
including saturation/drops. It excludes event construction, OTel spans, request
parsing, networking and GPU work. It cannot establish inference overhead.
Do not advertise these values as throughput, TTFT, ITL or p99 overhead.

Failure injection covers a hung exporter, collector outage, queue overflow,
bounded memory with thousands of distinct events, disabled fast path and bounded
shutdown. A timed-out close returns false: the daemon worker remains alive until
its exporter returns; Python cannot forcibly terminate it.
M9 alone measures baseline-versus-instrumented GPU inference overhead.
