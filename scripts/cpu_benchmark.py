"""CPU-only microbenchmark; not a claim about inference or GPU overhead."""

import json
import platform
import statistics
import time

from infertrace.collector import Collector
from infertrace.events import EventType, client_event

event = client_event(EventType.CLIENT_CHUNK, clock_domain="benchmark")
results = {}
for name, enabled in [("disabled_emit", False), ("enabled_emit", True)]:
    c = Collector(lambda _: None, enabled=enabled, capacity=1024)
    samples = []
    for _ in range(7):
        start = time.perf_counter_ns()
        for _ in range(10000):
            c.emit(event)
        samples.append((time.perf_counter_ns() - start) / 10000)
    c.flush()
    c.close()
    results[name] = {
        "median_ns_per_call": statistics.median(samples),
        "samples_ns": samples,
        "stats": vars(c.stats()),
    }
print(
    json.dumps(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "scope": "preallocated event emit only; no GPU/inference measurement",
            "results": results,
        },
        indent=2,
    )
)
