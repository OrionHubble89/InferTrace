# Troubleshooting
| Symptom | Check / remedy |
|---|---|
| Empty UI | Run mock demo, inspect /health and /events; clear exact-match filters |
| No spans in Jaeger | Confirm OTEL_EXPORTER_OTLP_ENDPOINT, collector/Jaeger logs and provider shutdown |
| Random missing test spans | Tests fix sampler=always_on; production respects OTel sampling env |
| Missing queue/prefill/decode | Baseline HTTP cannot observe engine phases; supply explicit engine events |
| Token view says Client chunk | Correct for baseline SSE; a chunk can contain multiple/sub-token pieces |
| Partial timeline | Inspect missing-end warnings, collector drops, export_errors and sampling |
| Collector outage | Inference continues; batches are counted/dropped; no unbounded retry |
| close returns false | Exporter is blocked; enforce I/O timeout and allow its daemon thread to return |
| HTTP 400 / 413 / 422 | Invalid schema / oversized batch / cyclic timeline; inspect metadata offline |
| Clock domains do not align | Supply explicit clock anchors in correlation API; do not assume receipt time alignment |
| Stale SQLite data | Named volume persists; select session/request or intentionally remove test volume |
| Browser binary unavailable | npm CI uses pinned bundle; CHROMIUM_PATH selects existing Chromium |
| SOCKS proxy error | Install httpx[socks] if your configured network requires SOCKS |
| Missing API key | Set the configured api_key_env environment variable |
