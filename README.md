# InferTrace

**One Trace. Three Waterfalls. Zero Overhead. Plug & Play.**

InferTrace is an open-source observability project for AI inference. Its goal is to correlate user experience, request execution and token-level timing while keeping instrumentation optional and lightweight.

## Design principles

1. **One Trace:** propagate W3C trace context and correlate session, turn and inference request identifiers.
2. **Three Waterfalls:** User, Request and Token timelines, with explicit measurement provenance. Streaming chunks are **not** equivalent to model tokens.
3. **Zero Overhead:** an aspirational target; no instrumentation is literally free. Default-off detailed instrumentation, nonblocking exports and reproducible A/B benchmarks.
4. **Plug & Play:** integrate with OpenAI-compatible inference servers without patching engine source.

## Quick start

Python 3.10+ required.

```bash
python -m pip install -e '.[dev]'
python -m infertrace.demo
pytest -q
```

The demo prints a local trace to stdout without needing a running inference engine.

## Scope

- **M0:** package, design principles, tests, CI.
- **M1:** OpenTelemetry trace context, user/turn/request spans, optional OTLP export, OpenAI-compatible streaming client adapter.
- **Next:** collector, correlation API, waterfall UI, vLLM internal token instrumentation, performance benchmarking.

See [architecture](docs/architecture.md) and [design principles](docs/design-principles.md).

## Accuracy contract

Client streaming observations measure *chunk arrival times*, not exact GPU execution or per-token decode latency. No measured overhead claim is made without controlled benchmarks.
