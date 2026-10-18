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
