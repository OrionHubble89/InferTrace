# InferTrace

**One Trace. Three Waterfalls. Zero Overhead. Plug & Play.**

An inference observability MVP with OTel propagation, bounded background
collection, SQLite persistence and an interactive User / Request / Token UI.
HTTP client chunks are explicitly distinguished from engine tokens. Zero
Overhead is a measured engineering target, not a literal or validated claim.

## Run the CPU-only demonstration
Requires Docker Compose; no GPU or inference model is downloaded.
```sh
git clone https://github.com/OrionHubble89/InferTrace.git
cd InferTrace
docker compose --profile mock up --build -d infertrace otel-collector jaeger mock
docker compose --profile mock run --rm demo
```
After the containers start, open these addresses in a browser on the same machine:

| Service | Local address |
|---|---|
| Three Waterfalls UI | `http://localhost:8080` |
| Jaeger trace viewer | `http://localhost:16686` |

These are local services, not publicly hosted demos. On GitHub, see the
[waterfall UI documentation](docs/ui.md) for usage and interaction details.

If Docker runs on a remote host, forward its loopback ports first (replace
`user@host` with your SSH destination):
```sh
ssh -N -L 8080:127.0.0.1:8080 -L 16686:127.0.0.1:16686 user@host
```
Then open the local addresses above on your computer.

The demonstration produces synthetic client chunks, not real engine tokens.
Use `docker compose down` to stop and retain event data.

## Python integration
Python 3.10+:
```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -c constraints.txt -e '.[dev]'
python -m infertrace.api
```
Configure endpoint/model in examples/config.json, then from another terminal:
```sh
python -m infertrace capabilities --config examples/config.json
python examples/plug_and_play.py --config examples/config.json
```
Baseline completions/chat SSE needs no engine patch. Deeper engine events require
an explicit source; aggregate vLLM metrics do not provide per-request GPU timing.
Wrap application calls with inference_session / inference_turn; inference_tool
records named tool intervals without inputs/outputs.

## Engineering status
M0–M8 target a locally and CI-validated release candidate, not production
validation. The authoritative plan and evidence are tracked in:
- [Implementation plan](docs/implementation-plan.md)
- [Execution report and commits](docs/implementation-report.md)
- [Architecture](docs/architecture.md)
- [Development and checks](docs/development.md)
- [Configuration and compatibility](docs/plug-and-play.md)
- [Event schema](docs/event-schema.md) · [Collector/API](docs/collector.md)
- [Correlation](docs/correlation.md) · [UI](docs/ui.md)
- [Overhead scope](docs/overhead.md) · [Security/privacy](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md) · [Release checklist](docs/release-checklist.md)

M9 alone validates RTX 4090 + real vLLM, engine event compatibility and controlled
baseline/instrumented overhead. No real GPU validation has been performed here.
