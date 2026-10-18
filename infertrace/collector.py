"""Bounded, best-effort background collection. Producers never perform I/O."""

from __future__ import annotations

import hashlib
import queue
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from infertrace.events import Event


@dataclass(frozen=True)
class CollectorStats:
    accepted: int
    dropped: int
    sampled_out: int
    exported: int
    export_errors: int
    pending: int


class Collector:
    def __init__(
        self,
        export: Callable[[Sequence[Event]], None],
        *,
        capacity: int = 1024,
        batch_size: int = 64,
        sample_rate: float = 1.0,
        enabled: bool = True,
        interval: float = 0.05,
        adaptive: bool = False,
        decision_capacity: int = 4096,
    ):
        if (
            capacity < 1
            or batch_size < 1
            or not 0 <= sample_rate <= 1
            or interval <= 0
            or decision_capacity < 1
        ):
            raise ValueError("invalid collector limits")
        self._adaptive = adaptive
        self._decision_capacity = decision_capacity
        self._decisions: OrderedDict[str, bool] = OrderedDict()
        self._queue: queue.Queue[Event] = queue.Queue(capacity)
        self._export = export
        self._batch_size = batch_size
        self._sample_rate = sample_rate
        self._enabled = enabled
        self._interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._accepted = self._dropped = self._sampled = self._exported = self._errors = 0
        self._thread: threading.Thread | None = None
        if enabled:
            self._thread = threading.Thread(target=self._run, daemon=True, name="infertrace-export")
            self._thread.start()

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._stop.is_set()

    def emit(self, event: Event) -> bool:
        if not self._enabled:
            return False
        # Trace-consistent sampling preserves joins; untraced events sample by ID.
        key = event.trace_id if event.trace_id != "0" * 32 else event.event_id
        ratio = int.from_bytes(hashlib.blake2s(key.encode(), digest_size=8).digest(), "big") / 2**64
        with self._lock:
            if self._stop.is_set():
                self._dropped += 1
                return False
            if key in self._decisions:
                sampled = self._decisions[key]
                self._decisions.move_to_end(key)
            else:
                pressure = self._queue.qsize() / self._queue.maxsize
                rate = (
                    self._sample_rate * max(0.05, 1 - pressure)
                    if self._adaptive
                    else self._sample_rate
                )
                sampled = ratio < rate
                self._decisions[key] = sampled
                if len(self._decisions) > self._decision_capacity:
                    self._decisions.popitem(last=False)
            if not sampled:
                self._sampled += 1
                return False
            try:
                self._queue.put_nowait(event)
                self._accepted += 1
                return True
            except queue.Full:
                self._dropped += 1
                return False

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            batch = []
            try:
                batch.append(self._queue.get(timeout=self._interval))
            except queue.Empty:
                continue
            while len(batch) < self._batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._export(batch)
                with self._lock:
                    self._exported += len(batch)
            except Exception:
                # No unbounded retries, no content/credentials in logs.
                with self._lock:
                    self._errors += 1
                    self._dropped += len(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks:
            if time.monotonic() >= deadline:
                return False
            self._stop.wait(0.001) if not self._stop.is_set() else time.sleep(0.001)
        return True

    def close(self, timeout: float = 5.0) -> bool:
        with self._lock:
            self._stop.set()
        if self._thread:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def stats(self) -> CollectorStats:
        with self._lock:
            return CollectorStats(
                self._accepted,
                self._dropped,
                self._sampled,
                self._exported,
                self._errors,
                self._queue.qsize(),
            )
