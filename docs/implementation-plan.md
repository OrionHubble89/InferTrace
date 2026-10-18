# InferTrace Implementation Plan

Status: **M0–M8 release candidate implemented and CI verified; M9 deferred**. This document defines the implementation order; completion is based on evidence, not the presence of a file.

## Design principles

**One Trace. Three Waterfalls. Zero Overhead. Plug & Play.**

- **One Trace:** correlate session, turn, request, streaming events and engine observations via OTel trace context and explicit correlation IDs.
- **Three Waterfalls:** User / Request / Token. Client streaming chunks must be labeled as chunks, never passed off as model tokens.
- **Zero Overhead:** aspirational. Make collection opt-in or lightweight by default, non-blocking and bounded. Measure overhead at final GPU validation.
- **Plug & Play:** basic operation with OpenAI-compatible endpoints without patching inference engine source; deeper capabilities are optional and version-dependent.

## Execution policy

Implement M0–M8 with local/unit/mock/integration tests and CI. **Defer real GPU environment deployment and benchmarking to M9.** No claims of production readiness or measured overhead until M9. Every milestone requires source, tests, documentation, and a commit/PR. Do not mark incomplete features as done.

## Milestones

### M0 — Foundation
- Python package, versioning, lint/type/test configuration, GitHub Actions.
- Reproducible development setup and dependency constraints.
- Acceptance: clean install and deterministic CI unit tests.

### M1 — One Trace
- OpenTelemetry bootstrap with configurable exporter and propagation.
- Session, turn and request spans; request headers propagation; error/cancel handling.
- Trace identifiers persisted alongside streaming observations.
- Acceptance: mock client/server tests prove trace continuity and correct parent relationships.

### M2 — Unified Event Model
- Versioned event envelope with trace_id, session_id, turn_id, request_id, event_type, source, clock domain, timestamps and schema version.
- Distinguish client chunk, engine token, scheduler, KV and resource events.
- Explicit missing-data and provenance fields; schema validation.
- Acceptance: serialization/compatibility tests and example fixtures.

### M3 — Collector & Adapters
- OpenAI-compatible streaming adapter and a vLLM metrics/trace adapter using supported public interfaces.
- Async ingestion, bounded queue, batch export, configurable sampling.
- Local persistent backend suitable for MVP and query endpoints.
- Acceptance: mocked SSE, disconnect, malformed payload, backpressure and collector-outage tests.

### M4 — Correlation Engine
- Join events across session/turn/request, reconcile timestamp domains, preserve overlapping execution.
- Reconstruct timelines with partial data and provenance indicators.
- Critical-path analysis where causal relationships are known; no unsupported GPU attribution.
- Acceptance: deterministic multi-request, concurrent batch and missing-event fixtures.

### M5 — Three Waterfalls UI
- User waterfall: sessions, turns, model/tool requests.
- Request waterfall: queue/prefill/decode/streaming phases where observed.
- Token waterfall: engine tokens if instrumented, otherwise explicitly labeled client chunks.
- Drill-down, filters, zoom, detail inspector, missing-data annotations.
- Acceptance: UI tests with realistic fixture datasets and accessible navigation.

### M6 — Zero-Overhead Engineering
- Disabled fast path, bounded non-blocking buffering, batch export, adaptive sampling, drop counters.
- No synchronous network export from inference critical path.
- CPU-only microbenchmarks and failure-injection tests.
- Acceptance: no deadlock/blocking under collector failure, memory bounded; actual throughput/p99 overhead measured only in M9.

### M7 — Plug & Play
- Configuration-based endpoint discovery and adapter capability negotiation.
- Docker Compose for UI/API/collector/Jaeger; example integration scripts.
- No source patch required for baseline functionality.
- Acceptance: simulated end-to-end installation and compatibility matrix documented.

### M8 — Quality & Release Candidate
- CI: unit/integration/UI, format/lint, dependency checks.
- Documentation, architecture, API, troubleshooting, security/privacy defaults.
- Full mock end-to-end demonstration and release checklist.
- Acceptance: all CI checks green and no critical open blockers.

### M9 — Final Real-world Validation (LAST)
- Deploy vLLM with Qwen2.5-0.5B-Instruct on NVIDIA RTX 4090 24GB.
- Validate trace continuity and distinguish actual engine token events from HTTP chunks.
- Benchmark baseline vs instrumented: throughput, TTFT, ITL, p50/p95/p99 latency, CPU, RAM and GPU memory.
- Cover prompt length, output length, concurrency, cancellation, collector outage and cache behavior.
- Publish raw data, methodology, version matrix, overhead results and limitations.
- Only claim Zero Overhead target if measured evidence supports it.

## Tracking

| Milestone | Status |
|---|---|
| M0 | Implemented and CI verified; see implementation-report.md |
| M1 | Implemented and CI verified; see implementation-report.md |
| M2 | Implemented and CI verified |
| M3 | Implemented and CI verified; OTLP JSON strengthened in M8 |
| M4 | Implemented and CI verified |
| M5 | Implemented; Chromium UI and CI verified |
| M6 | Implemented; CPU/failure/memory tests and CI verified |
| M7 | Implemented; Compose/Jaeger and full CI verified at 9df9d45 |
| M8 | Complete: source 6a256b2; all jobs green in CI run 39108236394 |
| M9 | Deferred until M0–M8 complete |

## Definition of done

A milestone is complete only when code, tests, docs and CI evidence are present. GitHub commits alone are not evidence of successful execution. A release is not production-validated until M9 finishes.

Execution evidence and remaining limitations: [implementation-report.md](implementation-report.md).
