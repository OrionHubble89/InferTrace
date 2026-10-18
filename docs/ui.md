# Three waterfalls UI
Start `python -m infertrace.api` and open http://127.0.0.1:8080.
The same package serves UI, query API and ingestion. No CDN or external assets.

User lanes group session/turn/request intervals. Clicking a request drills down.
Request lanes show observed phases, including tools. Token lanes explicitly
distinguish engine tokens from HTTP client chunks. Filters narrow exact session,
request and source; zoom expands the timeline horizontally. Click or focus and
press Enter to inspect metadata, provenance, uncertainty and missing fields.
Unknown clock domains use independent axes. No unobserved engine phase is fabricated.

The UI loads at most 10000 events; API pagination supports larger logs.
Sub-millisecond Unix precision is constrained by JavaScript Number precision;
backend integer timestamps remain authoritative. This is an MVP, not a large
trace virtualization engine.

Browser validation:
```sh
npm ci --ignore-scripts
npm run test:ui
```
The test starts a synthetic local server, launches headless Chromium and checks
all waterfalls, chunk/token labels, drilldown, filters, keyboard activation,
zoom, empty data, text injection and mobile overflow. CHROMIUM_PATH can select
a locally installed binary; otherwise the pinned npm Chromium bundle is used.
