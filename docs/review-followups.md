# Review follow-ups — 0.1.0rc2

Status: all nine findings implemented and locally regression-tested; full GitHub
CI for this revision is pending. M9 real vLLM + RTX 4090 remains excluded.
The earlier rc1 CI established the paths it tested, not full principle compliance.

## Findings and implementation evidence

| Finding | Implementation | Regression evidence |
|---|---|---|
| P1 caller context overwritten | Generator runs in its own Context, bound at first consumption; caller context never receives generator tokens | New consumer spans survive next/exhaust/close; cross-thread close; best-effort GC |
| P1 identical OTLP retry rejected | Deduplicate upstream immutable data, retain first receipt timestamp | Identical HTTP retries return 200; changed span returns 400 and rolls back |
| P2 correlated events lost by filters | Indexed recursive SQLite scope resolution before filter/page selection | Parent arrives later; request/session/source filters; deep ancestry; ambiguous scope rejected |
| P2 missing session/turn intervals | Explicit collector-enabled lifecycle start/end events, including empty/error turns | Collected lifecycle fixtures; real local HTTP end-to-end; Compose lifecycle assertions |
| P2 equal-time boundaries unmatched | Start-before-end tie ordering, independent of arbitrary event IDs | Zero-duration request/phase/session/turn pairs in either input order |
| P2 UI hides newer sessions after 10000 events | Latest ingestion snapshot, full-database server filters, stable older/newer pages | API >10000-event history and concurrent arrival; Chromium >10000-event fixture |
| P2 disabled integration still exports spans | Skip provider and enclosing lifecycle setup; helper enabled=False; no stream context copy | Fail-if-called provider/span/event/context-copy guards |
| P2 non-finite metric rejects valid scrape | Preserve unsupported numeric sample as null plus explicit non-finite-value annotation | NaN, +Inf and -Inf alongside valid samples; JSON roundtrip |
| P2 metrics cap applied after buffering | Stream decoded bytes into a capped buffer; close on limit/error | 20 MiB source stops by 4 MiB + one 64 KiB chunk; exact limit accepted |

Regression suite: tests/test_review_regressions.py. Existing trace, queue,
backpressure, privacy, schema, correlation and installation tests remain enabled.
Aggregate metrics never inherit a request ID, including through parent ancestry.
Legacy database migration preserves original payloads and IDs.

## Design-principle acceptance

| Principle | Implemented contract | Remaining boundary |
|---|---|---|
| One Trace | Scoped IDs, W3C propagation, isolated consumers, ancestry-aware joins, retry-safe persistence | Real engine trace/version compatibility belongs to M9 |
| Three Waterfalls | Actual session/turn/model/tool intervals; observed request phases; explicit chunk/token distinction; full-history filters and pagination | Engine phase/token data must be supplied explicitly; partial pages are annotated |
| Zero Overhead | Explicit disabled path, no producer network/disk export, bounded queue/batches/sampling cache, streaming metrics cap and drop counters | Instrumentation has a cost; throughput/TTFT/ITL/p99 overhead is unmeasured until M9 |
| Plug & Play | Configuration-based OpenAI SSE integration, optional public metrics/OTLP JSON adapter, automatic local DB migration, Compose | No built-in native vLLM token hook; OTLP JSON adapter is not a full protobuf/gRPC receiver |

## Verification

Local: 80 Python tests, Ruff lint/format, strict mypy, Chromium interactions and
large-history pagination passed. Wheel build passed. Final GitHub verification
must additionally pass Python 3.10/3.12, installed-wheel smoke, Compose/Jaeger and
dependency audits before this revision is accepted. No real GPU test is run.
