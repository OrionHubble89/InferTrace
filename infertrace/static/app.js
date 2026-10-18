"use strict";
const $ = id => document.getElementById(id);
let data = {events: [], intervals: [], warnings: []};
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function inspect(row) { $("detail").textContent = JSON.stringify(row, null, 2); }
function scope(row) {
  return (!$("session").value || row.session_id === $("session").value) &&
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
      const key = userView ? label(row) : (row.request_id || "aggregate") + " · " + (row.phase || row.event_type);
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
          if (userView && row.request_id) { $("request").value = row.request_id; render(); }
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
  $("status").textContent = "Loading observations…";
  try {
    const response = await fetch("/timeline?limit=10000");
    if (!response.ok) throw new Error("HTTP " + response.status);
    data = await response.json();
    $("status").textContent = data.events.length + " observations loaded (up to 10000).";
    render();
  } catch (error) { $("status").textContent = "Unable to load observations: " + error.message; }
}
for (const id of ["session","request","source","zoom"]) $(id).addEventListener("input", render);
$("refresh").onclick = load;
load();
