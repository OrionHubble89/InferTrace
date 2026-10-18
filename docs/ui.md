# Three waterfalls UI
Start `python -m infertrace.api` and open http://127.0.0.1:8080.
The same package serves UI, query API and ingestion. No CDN or external assets.

User lanes group session/turn/request intervals. Clicking a request drills down.
Request lanes show observed phases, including tools. Token lanes explicitly
distinguish engine tokens from HTTP client chunks. Server-side filters narrow exact trace, session,
request and source; zoom expands the timeline horizontally. Click or focus and
press Enter to inspect metadata, provenance, uncertainty and missing fields.
Unknown clock domains use independent axes. No unobserved engine phase is fabricated.

The UI starts with the newest 1000 ingested events. Older/Newer page buttons
navigate a stable ingestion snapshot; Refresh/Latest observations starts a new
snapshot. Filters query the full database, including sessions beyond 10000 events.
Each page includes total count, offset, snapshot and has_more. Partial-page
warnings explicitly indicate that intervals/causal paths may cross page boundaries.
Request drilldown sets both trace and session scope. Aggregate metrics remain
unattributed. Backend query-time parent-span resolution precedes filters and paging.
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
zoom, lifecycle intervals, empty data, text injection, mobile overflow and
server filters/pagination against a history of more than 10000 events. CHROMIUM_PATH can select
a locally installed binary; otherwise the pinned npm Chromium bundle is used.
