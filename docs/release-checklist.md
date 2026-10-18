# Release candidate checklist
M0–M8 acceptance requires the final source revision to pass:
- Python 3.10 and 3.12: install, pip check, Ruff lint/format, strict mypy, unit/integration tests.
- Build wheel, reinstall outside checkout, verify packaged UI/API assets.
- Chromium: three waterfalls, drilldown, filters, shared clock origin, keyboard, zoom, mobile, injection.
- Docker Compose: non-root app, mock endpoint, persisted events, OTel Collector, Jaeger trace continuity.
- Runtime Python dependency audit; npm high/critical advisory audit.
- Architecture/API/config/privacy/troubleshooting docs; commit/evidence ledger.
- Review regressions: caller context, OTLP retries, lifecycle collection,
  pre-filter ancestry, equal timestamps, >10000-event pagination, disabled setup,
  non-finite metrics and streaming input limits.
- No critical unresolved blocker; known limits remain explicit.

M9 is a separate final gate, not included in these checks:
- RTX 4090 24GB and real vLLM/Qwen2.5-0.5B-Instruct.
- Record exact runtime/engine/model/driver versions and raw data.
- Verify engine trace/event compatibility and distinguish chunks/tokens.
- Controlled baseline vs instrumented throughput, TTFT/ITL, p50/p95/p99,
  CPU/RAM/GPU memory; vary prompt/output/concurrency.
- Include cancellation, collector outage and cache behavior.
- No Zero Overhead or production-readiness claim without measured evidence.

No tag, package publication or GPU deployment is automatically performed.
