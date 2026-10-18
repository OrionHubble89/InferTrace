# Development
Requires Python 3.10 or later. From a fresh checkout:
```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -c constraints.txt -e '.[dev]'
python -m pip check
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest -q
python -m build --wheel
```
Direct dependency versions are constrained to the tested set. Tests override the
host OTel sampling configuration, use mock transports, and need no GPU or external
services. CI runs Python 3.10 and 3.12. Local execution on one interpreter is not
evidence that the whole CI matrix passed.

## M1 tracing
Wrap calls with `inference_session("session")` and
`inference_turn("session", "turn")`. `observe_completion` creates a request span,
injects W3C trace context, and returns IDs on each client chunk. Explicitly close
partially consumed generators (or use `contextlib.closing`) to release the HTTP
connection and record cancellation. Content is returned to the caller but never
added to span attributes.

Embedded applications should call `use_provider(application_provider)` or
`configure_tracing(install_global=False)`. They own provider shutdown. Context
uses ContextVar and is restored on completion, cancellation and exceptions.
Do not reconfigure providers while requests are in flight.

The final CI additionally runs browser, Docker Compose and dependency-audit jobs,
and reinstalls the built wheel outside checkout. For the local runtime audit,
use a fresh production virtualenv, freeze its installed dependencies excluding
InferTrace, then run pip-audit==2.10.1 with --no-deps --disable-pip. npm audit checks
the browser-test toolchain. No GPU job is part of this workflow.
