# InferTrace Design Principles

## One Trace
Correlate user sessions, turns, inference requests and observations using OpenTelemetry/W3C trace context. Maintain explicit identifiers for relationships that are not parent-child.

## Three Waterfalls
- **User:** session, turn, agent/tool activities, perceived latency.
- **Request:** gateway, routing, queue, prefill, decode and streaming when observed.
- **Token:** per-token timestamps **only** when emitted by an instrumented engine. Otherwise display a clearly labeled client-side *chunk* timeline.

Do not infer precise GPU scheduling from HTTP chunk arrival times.

## Zero Overhead
Zero is an aspiration, not a measured fact. Keep deep instrumentation off by default, use bounded buffers, asynchronous export and adaptive sampling. Never block the inference critical path for telemetry. Benchmark baseline versus instrumented throughput, TTFT, ITL and p99 latency.

## Plug & Play
Support existing OpenAI-compatible endpoints and standard OpenTelemetry protocols without requiring a source patch. Declare adapter capabilities and engine-version limitations.
