# Plug & Play
Baseline integration only needs an OpenAI-compatible completions/chat endpoint.
It needs no source patch. Copy examples/config.json, set endpoint/model, optionally
set api_key_env to an environment variable name. Secrets stay out of config/logs.
Run:
```sh
python -m infertrace capabilities --config examples/config.json
python -m infertrace.api
python examples/plug_and_play.py --config examples/config.json
```
Capability discovery GETs /v1/models and /metrics. A models response does not prove
streaming support. The report labels streaming configured-not-probed, engine
phases unknown and engine tokens false. Successful streaming is proven by the
subsequent request; unsupported APIs fail explicitly, never silently fabricate data.

## CPU-only Compose installation
```sh
docker compose --profile mock up --build -d infertrace otel-collector jaeger mock
docker compose --profile mock run --rm demo
python scripts/compose_smoke.py
```
UI/API/collector: http://127.0.0.1:8080
Jaeger: http://127.0.0.1:16686

The Python collector batches metadata to the API/SQLite; OTel spans independently
flow through the OTel Collector to Jaeger. API and UI share one container.
A named events volume persists across restarts. All published ports bind to
loopback; mock is internal. Stop with docker compose down; do not use -v unless
you intend to delete demo data. In CI -v cleans only the isolated job's data.

| Interface | Validation | Available evidence |
|---|---|---|
| OpenAI completions SSE | Mock + local HTTP | chunks, request duration, trace IDs |
| OpenAI chat SSE | Mock transport | chunks and role/usage filtering |
| vLLM /metrics | Synthetic Prometheus exposition | aggregate numeric observations |
| vLLM OTel tracing | Optional OTLP export infrastructure | version-dependent, M9 needed |
| Engine token timing | Explicit engine Event fixtures | no automatic baseline hook |
| RTX 4090 / real vLLM | Deferred M9 | no measured overhead claim |

The current execution host has no Docker daemon. Compose runtime validation runs
in GitHub Actions; its result, not YAML generation, determines installation status.
