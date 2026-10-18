# Architecture (MVP)

```text
User / Agent
    |
InferTrace Python SDK (session/turn/request spans)
    |
OpenAI-compatible API ----> vLLM / SGLang
    |
OTel SDK -- optional OTLP --> Collector / Jaeger

Future: compact engine token events --> bounded local agent --> correlation API --> three waterfalls
```

## Data contract

- Trace identity: W3C trace_id / span_id.
- User identity: opaque session_id and turn_id; avoid recording prompt content by default.
- Request identity: trace context plus model and optional engine request ID.
- Chunk observations: monotonic client timestamps, sequence index and content length.
- Token observations: distinct source, timestamp domain and engine version; do not equate chunks with tokens.

## Production constraints

Collector failures must not stop inference. Avoid unbounded buffers and per-token OTel spans. Never claim a GPU kernel belongs exclusively to one token under continuous batching.
