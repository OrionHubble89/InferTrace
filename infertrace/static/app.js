"use strict";
const $ = id => document.getElementById(id);
let data = {events: [], intervals: [], warnings: []};
let offset = 0, snapshot = null, loadVersion = 0, timer = null, controller = null;
const pageSize = 1000;
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function inspect(row) { $("detail").textContent = JSON.stringify(row, null, 2); }
function scope(row) {
  return (!$("trace").value || row.trace_id === $("trace").value) &&
    (!$("session").value || row.session_id === $("session").value) &&
    (!$("request").value || row.request_id === $("request").value) &&
    (!$("source").value || row.source === $("source").value);
}
function label(row) {
  return (row.session_id || "unknown session") + " / " + (row.turn_id || "unknown turn") +
    " / " + (row.request_id || "aggregate") + (row.model ? " · " + row.model : "") +
    (row.operation_name ? " · tool: " + row.operation_name : "");
}
function renderLanes(target, rows, userView = false) {
  const parent = $(target); parent.replaceChildren();
  if (!rows.length) { parent.append(el("p", "No observations for this selection.", "empty")); return; }
  const domains = new Map();
  for (const row of rows) {
    if (!domains.has(row.domain)) domains.set(row.domain, []);
    domains.get(row.domain).push(row);
  }
  for (const [domain, observations] of domains) {
    const group = el("div", undefined, "lane");
    group.append(el("p", "Clock: " + domain + " · relative milliseconds", "lane-title"));
    let origin = Infinity, end = -Infinity;
    for (const row of [...data.events, ...data.intervals].filter(scope).filter(r => r.domain === domain)) {
      origin = Math.min(origin, row.start_ns); end = Math.max(end, row.end_ns);
    }
    const span = Math.max(end - origin, 1);
    const groups = new Map();
    for (const row of observations) {
      const key = row.trace_id + " · " + (userView ? label(row) : label(row) + " · " + (row.phase || row.event_type));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    for (const [name, items] of groups) {
      group.append(el("div", name, "lane-title"));
      const scroll = el("div", undefined, "scroll"), track = el("div", undefined, "track");
      track.style.width = Number($("zoom").value) * 100 + "%";
      for (const row of items) {
        const kind = row.event_type === "engine.token" ? "Engine token" :
          row.event_type === "client.chunk" ? "Client chunk" : row.phase || row.event_type;
        const start = ((row.start_ns - origin) / 1e6).toFixed(3);
        const duration = ((row.end_ns - row.start_ns) / 1e6).toFixed(3);
        const button = el("button", kind + " · " + start + " ms", "mark " + (row.source === "engine" ? "engine" : ""));
        button.style.left = (row.start_ns - origin) / span * 95 + "%";
        button.style.width = Math.max((row.end_ns - row.start_ns) / span * 95, 1) + "%";
        button.setAttribute("aria-label", kind + " " + name + ", start " + start + " ms, duration " + duration + " ms");
        button.title = kind + ": " + duration + " ms · " + row.provenance;
        button.onclick = () => {
          inspect(row);
          if (userView && row.request_id) {
            $("trace").value = row.trace_id; $("session").value = row.session_id;
            $("request").value = row.request_id; resetPage(); load();
          }
        };
        track.append(button);
      }
      scroll.append(track); group.append(scroll);
    }
    parent.append(group);
  }
}
function render() {
  const intervals = data.intervals.filter(scope), events = data.events.filter(scope);
  renderLanes("user", intervals.filter(r => ["request","session","turn","tool"].includes(r.phase)), true);
  renderLanes("requests", intervals);
  renderLanes("tokens", events.filter(r => ["engine.token","client.chunk"].includes(r.event_type)));
  $("warnings").replaceChildren(...[
    ...data.warnings, ...new Set(events.flatMap(r => r.missing || [])),
    "Aggregate metrics do not establish request or GPU attribution.",
    "Critical path requires explicit causal edges."
  ].map(w => el("p", w, "muted")));
}
async function load() {
  const version = ++loadVersion;
  if (controller) controller.abort();
  controller = new AbortController();
  $("status").textContent = "Loading observations…";
  const query = new URLSearchParams({limit: String(pageSize), offset: String(offset), order: "latest"});
  if (snapshot !== null) query.set("snapshot", String(snapshot));
  for (const [id, field] of [["trace","trace_id"],["session","session_id"],["request","request_id"],["source","source"]]) {
    if ($(id).value) query.set(field, $(id).value);
  }
  try {
    const response = await fetch("/timeline?" + query.toString(), {signal: controller.signal});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const received = await response.json();
    if (version !== loadVersion) return;
    data = received;
    const page = data.pagination;
    snapshot = page.snapshot;
    $("status").textContent = data.events.length + " observations loaded · " +
      page.total + " matching · page " + (Math.floor(offset / pageSize) + 1) +
      (page.has_more ? " · older observations available" : "");
    $("newer").disabled = offset === 0;
    $("older").disabled = !page.has_more;
    render();
  } catch (error) {
    if (version !== loadVersion || error.name === "AbortError") return;
    $("status").textContent = "Unable to load observations: " + error.message;
  }
}
function resetPage() { offset = 0; snapshot = null; clearTimeout(timer); }
for (const id of ["trace","session","request","source"]) $(id).addEventListener("input", () => {
  resetPage(); timer = setTimeout(load, 200);
});
$("zoom").addEventListener("input", render);
$("newer").onclick = () => { offset = Math.max(0, offset - pageSize); load(); };
$("older").onclick = () => { offset += pageSize; load(); };
$("refresh").onclick = $("latest").onclick = () => { resetPage(); load(); };
load();
