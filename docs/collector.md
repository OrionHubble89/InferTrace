# Collector and adapters
Run `python -m infertrace.api --db infertrace.db`. The default bind is loopback.
`POST /events` accepts up to 1000 schema-validated events in a 1 MiB JSON list,
atomically and idempotently by event ID. `GET /events` filters by trace_id,
session_id, request_id; limit (1–10000) and offset provide pagination.
`GET /health` reports process availability. SQLite stores metadata only.

Create `Collector(store.export)` locally or
`Collector(HTTPExporter("http://127.0.0.1:8080/events"))` remotely, and pass it
to `observe_completion(collector=collector, ...)`. Producers enqueue without
network/disk I/O; export happens on a daemon thread in bounded batches.
Overflow/export failures are counted and dropped, never retried without limit.
`flush(timeout)` and `close(timeout)` report whether draining finished.
Exporters must enforce I/O timeouts; Python cannot kill a blocked exporter.
The store must outlive the collector and be closed after collection stops.

The OpenAI adapter supports completion/chat SSE, W3C propagation, authorization,
explicit cancellation, multiline SSE, usage-only messages, malformed payloads
and premature disconnect detection. Telemetry excludes all content/API keys.
A stream without [DONE] is incomplete/error even if a final text chunk arrived.

The optional vLLM adapter scrapes public `/metrics` Prometheus exposition;
`parse_vllm_metrics` supports fixture/offline ingestion. Metrics are process-wide
resource observations, not request spans or engine tokens. Labels are omitted
and marked missing. Deeper engine-token/phase events require a separate source
that supplies explicit request correlation and an Event with engine provenance.
This MVP does not claim a built-in vLLM token hook or OTLP gRPC/protobuf receiver;
OTel spans can independently be exported to Jaeger using its public OTLP input.
Real vLLM interface compatibility is reserved for M9.


## OTLP JSON span bridge
POST /v1/traces accepts OTLP/HTTP JSON resourceSpans/scopeSpans with hex traceId,
spanId, optional parentSpanId and string start/endTimeUnixNano. It stores span
boundaries, drops arbitrary attributes, and does not infer phases or tokens.
Only infertrace.session_id/turn_id/request_id/clock_domain string attributes are
retained. Missing request correlation is explicit; the correlation engine can
join via known parent-span ancestry. Unknown clocks remain separate.
This is a JSON adapter, not a complete OTLP collector implementation: no
protobuf/gRPC/gzip support, no native token instrumentation, no claimed vLLM
version compatibility before M9. Use a supported JSON bridge/explicit conversion.
POST responses use HTTP 200 with {} for accepted OTLP JSON.

GET /timeline accepts the same filters/pagination as /events and returns
reconstructed intervals, observations, evidence warnings and causal-path data.
Cyclic causal data produces HTTP 422 rather than an unhandled server failure.
Conflicting duplicate event IDs reject an entire batch; exact retries are safe.

## Review follow-up query semantics
GET /timeline now resolves parent-span scope before filtering and pagination.
Optional source=client|engine|metrics|collector, order=oldest|latest and snapshot
join the existing trace_id/session_id/request_id/limit/offset parameters.
The response includes pagination: total, snapshot, offset, limit, has_more and
next_offset. Latest means ingestion order, not timestamp comparison between hosts.
Pass the returned snapshot on subsequent pages; omit it to refresh. Filters apply
to the full snapshot. Partial pages carry a warning and can split intervals.

GET /events retains its raw event-list response and supports the same query
parameters, without inferred scope. EventStore.query_page(resolve=True) is the
typed Python API for correlated queries. Exact OTLP JSON retries preserve the
first receipt time; changed immutable span content rejects the batch.

Metrics scrape reads stop as soon as the decoded 4 MiB limit is exceeded and
close the response on success/error. NaN and infinity are retained as value=null
with missing containing non-finite-value; valid samples in the scrape survive.
