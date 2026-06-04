"""
Timing aggregation for league cache warmup (--benchmark).

Thread-safe records per endpoint build; prints where wall time goes when CPU is idle (GIL / I/O).
"""

from __future__ import annotations

import json
import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Mapping, Optional


@dataclass
class WarmTimingRecord:
    endpoint: str
    phase: str
    combo: str
    build_ms: float = 0.0
    localize_ms: float = 0.0
    cache_io_ms: float = 0.0
    status: str = ""
    lang: str = ""


@dataclass
class WarmBenchmark:
    database: str
    started_at: float = field(default_factory=time.perf_counter)
    revision_index_ms: float = 0.0
    data_load_ms: float = 0.0
    pool_idle_ms: float = 0.0
    _records: List[WarmTimingRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(
        self,
        *,
        endpoint: str,
        phase: str,
        combo: str,
        status: str,
        lang: str = "",
        build_ms: float = 0.0,
        localize_ms: float = 0.0,
        cache_io_ms: float = 0.0,
    ) -> None:
        with self._lock:
            self._records.append(
                WarmTimingRecord(
                    endpoint=endpoint,
                    phase=phase,
                    combo=combo,
                    build_ms=build_ms,
                    localize_ms=localize_ms,
                    cache_io_ms=cache_io_ms,
                    status=status,
                    lang=lang,
                )
            )

    def add_pool_idle(self, seconds: float) -> None:
        if seconds > 0:
            with self._lock:
                self.pool_idle_ms += seconds * 1000.0

    def snapshot(self) -> List[WarmTimingRecord]:
        with self._lock:
            return list(self._records)

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "database": self.database,
            "wall_ms": (time.perf_counter() - self.started_at) * 1000.0,
            "revision_index_ms": self.revision_index_ms,
            "data_load_ms": self.data_load_ms,
            "pool_idle_ms": self.pool_idle_ms,
            "records": [
                {
                    "endpoint": r.endpoint,
                    "phase": r.phase,
                    "combo": r.combo,
                    "status": r.status,
                    "lang": r.lang,
                    "build_ms": round(r.build_ms, 2),
                    "localize_ms": round(r.localize_ms, 2),
                    "cache_io_ms": round(r.cache_io_ms, 2),
                }
                for r in self.snapshot()
            ],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def print_report(self) -> None:
        records = self.snapshot()
        wall_ms = (time.perf_counter() - self.started_at) * 1000.0
        built = [r for r in records if r.status in {"miss-built", "localized"}]
        hits = [r for r in records if r.status == "hit"]

        by_endpoint: DefaultDict[str, float] = defaultdict(float)
        by_phase: DefaultDict[str, float] = defaultdict(float)
        for r in records:
            by_endpoint[r.endpoint] += r.build_ms + r.localize_ms + r.cache_io_ms
            by_phase[r.phase] += r.build_ms + r.localize_ms + r.cache_io_ms

        build_times = [r.build_ms for r in built if r.build_ms > 0]
        loc_times = [r.localize_ms for r in records if r.localize_ms > 0]

        print("\n--- cache warm benchmark ---", flush=True)
        print(f"wall={wall_ms/1000:.1f}s  data_load={self.data_load_ms/1000:.1f}s  "
              f"revision_index={self.revision_index_ms/1000:.1f}s  pool_idle(wait)={self.pool_idle_ms/1000:.1f}s",
              flush=True)
        print(f"records={len(records)}  hits={len(hits)}  built/localized={len(built)}", flush=True)
        if build_times:
            print(
                f"build_ms: n={len(build_times)}  sum={sum(build_times)/1000:.1f}s  "
                f"median={statistics.median(build_times):.0f}  p95={_percentile(build_times, 95):.0f}  "
                f"max={max(build_times):.0f}",
                flush=True,
            )
        if loc_times:
            print(
                f"localize_ms: n={len(loc_times)}  sum={sum(loc_times)/1000:.1f}s  "
                f"median={statistics.median(loc_times):.0f}",
                flush=True,
            )

        accounted = sum(by_endpoint.values()) + self.data_load_ms + self.revision_index_ms
        unaccounted = max(0.0, wall_ms - accounted - self.pool_idle_ms)
        print(
            f"time accounted≈{accounted/1000:.1f}s  unaccounted≈{unaccounted/1000:.1f}s "
            f"(thread overhead, GIL, tqdm, planning)",
            flush=True,
        )

        print("\nTop endpoints by total ms:", flush=True)
        for endpoint, ms in sorted(by_endpoint.items(), key=lambda x: -x[1])[:15]:
            print(f"  {ms/1000:7.2f}s  {endpoint}", flush=True)

        print("\nBy phase:", flush=True)
        for phase, ms in sorted(by_phase.items(), key=lambda x: -x[1]):
            print(f"  {ms/1000:7.2f}s  {phase}", flush=True)

        slow = sorted(built, key=lambda r: r.build_ms, reverse=True)[:12]
        if slow:
            print("\nSlowest single builds:", flush=True)
            for r in slow:
                if r.build_ms <= 0:
                    continue
                print(f"  {r.build_ms/1000:6.2f}s  {r.combo}  [{r.status}]", flush=True)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)
