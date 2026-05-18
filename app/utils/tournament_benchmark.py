"""
Opt-in timing for tournament section builds (development / regression checks).

Environment
-----------
TOURNAMENT_BENCHMARK
    When set to ``1``, ``true``, ``yes``, or ``on`` (case-insensitive), enables:
    - Per-step timings in ``TournamentService.get_tournament_section``
    - Field-progress setup vs loop detail lines
    - Route-level ``DISK CACHE HIT`` / ``MISS`` lines on ``/tournament/get_section``

    Default: unset (disabled). No measurable overhead when disabled.

    Set on the **Flask/Gunicorn process**, not only on the HTTP client.

Usage
-----
See ``DEPLOY.md`` § "Tournament performance profiling" and::

    scripts/benchmark_tournament_section.py

Example::

    TOURNAMENT_BENCHMARK=1 uv run python wsgi.py

Logs are written to the server process stdout (Flask dev console).
Do not enable in production Docker.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


def tournament_benchmark_enabled() -> bool:
    return os.getenv("TOURNAMENT_BENCHMARK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class TournamentBenchmark:
    def __init__(self, label: str, *, context: Optional[Dict[str, Any]] = None):
        self.label = label
        self.context = context or {}
        self._timings: Dict[str, float] = {}
        self._t0 = time.perf_counter()
        self._enabled = tournament_benchmark_enabled()

    @contextmanager
    def step(self, name: str):
        if not self._enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self._timings[name] = time.perf_counter() - t0

    def add(self, name: str, seconds: float) -> None:
        if self._enabled:
            self._timings[name] = seconds

    def report(self) -> None:
        if not self._enabled:
            return
        total = time.perf_counter() - self._t0
        accounted = sum(self._timings.values())
        ctx = " | ".join(f"{k}={v!r}" for k, v in self.context.items())
        print(f"\n=== tournament benchmark: {self.label} ===", flush=True)
        if ctx:
            print(f"  context: {ctx}", flush=True)
        for name, sec in sorted(self._timings.items(), key=lambda x: -x[1]):
            pct = (sec / total * 100) if total else 0.0
            print(f"  {name:36s} {sec:7.3f}s  ({pct:5.1f}%)", flush=True)
        print(f"  {'accounted':36s} {accounted:7.3f}s", flush=True)
        print(f"  {'TOTAL':36s} {total:7.3f}s", flush=True)
        print("=== end benchmark ===\n", flush=True)
