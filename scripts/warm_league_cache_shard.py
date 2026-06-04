#!/usr/bin/env python3
"""
Run league cache warm in parallel OS processes (one Python interpreter per shard).

Each shard loads data independently, so CPU can use multiple cores (no shared GIL).

Shards:
  - one process per season (--phase seasons)
  - one process per league for meta / league-wide charts (--phase league-wide)
  - club matrix split into batches (--phase clubs --clubs-offset/--clubs-limit)

Usage:
  uv run python scripts/warm_league_cache_shard.py --database db_real_merged --rebuild --warm-clubs
  uv run python scripts/warm_league_cache_shard.py --database db_real_merged --warm-clubs --max-parallel 6
  uv run python scripts/warm_league_cache_shard.py --database db_real_merged --season "25/26" --skip-meta
  uv run python scripts/warm_league_cache_shard.py --database db_real_merged --dry-run

Environment: same as warm_league_cache.py.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Dict, List, Optional, Tuple, TypedDict

ROOT = Path(__file__).resolve().parents[1]
WARM_SCRIPT = Path(__file__).resolve().parent / "warm_league_cache.py"
LEGACY = ROOT / "league_analyzer_v1"
for _p in (LEGACY, ROOT):
    if _p.is_dir():
        sys.path.insert(0, str(_p))

import importlib.util

_spec = importlib.util.spec_from_file_location("warm_league_cache_mod", WARM_SCRIPT)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Could not load warm_league_cache.py")
_warm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _warm
_spec.loader.exec_module(_warm)

WarmShard = _warm.WarmShard
build_warm_shards = _warm.build_warm_shards


def _python_invocation() -> List[str]:
    return ["uv", "run", "python", str(WARM_SCRIPT)]


def fetch_catalog(
    database: str,
    *,
    season: Optional[str] = None,
    league: Optional[str] = None,
) -> Dict[str, object]:
    cmd = _python_invocation() + ["--database", database, "--catalog"]
    if season:
        cmd.extend(["--season", season])
    if league:
        cmd.extend(["--league", league])
    env = os.environ.copy()
    env["LEAGUE_CACHE_WARM_ON_START"] = "0"
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"--catalog failed ({proc.returncode}): {err}")
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
    return json.loads(line)


class ShardRunResult(TypedDict):
    label: str
    code: int
    elapsed: float
    stderr_tail: str


def _run_one_shard(
    database: str,
    shard: WarmShard,
    *,
    extra_args: List[str],
    env: Dict[str, str],
    quiet: bool,
) -> ShardRunResult:
    cmd = (
        _python_invocation()
        + ["--database", database]
        + shard.argv
        + list(shard.extra_argv)
        + extra_args
    )
    t0 = time.perf_counter()
    if quiet:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stderr_tail = ""
        if proc.stderr:
            lines = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
            stderr_tail = "\n".join(lines[-8:])
    else:
        proc = subprocess.run(cmd, cwd=ROOT, env=env)
        stderr_tail = ""
    elapsed = time.perf_counter() - t0
    return {
        "label": shard.label,
        "code": proc.returncode,
        "elapsed": elapsed,
        "stderr_tail": stderr_tail,
    }


class ShardProgress:
    """tqdm over shard subprocesses with ETA."""

    def __init__(self, total: int, *, database: str, disable: bool) -> None:
        from tqdm import tqdm

        self._timings: List[Tuple[str, float, int]] = []
        self._pbar = tqdm(
            total=total,
            desc=f"warm {database}",
            unit="shard",
            disable=disable or total <= 0,
            dynamic_ncols=True,
            mininterval=0.3,
            file=sys.stdout,
        )
        self._ok = 0
        self._fail = 0

    def complete(self, result: ShardRunResult) -> None:
        label = result["label"]
        code = result["code"]
        elapsed = result["elapsed"]
        self._timings.append((label, elapsed, code))
        if code == 0:
            self._ok += 1
        else:
            self._fail += 1
        self._pbar.update(1)
        self._pbar.set_postfix(
            ok=self._ok,
            fail=self._fail,
            last=f"{label} {elapsed:.0f}s",
            refresh=True,
        )

    def close(self) -> None:
        self._pbar.close()

    def print_timing_summary(self, wall_s: float, *, failed: List[str]) -> None:
        from tqdm import tqdm

        lines = [
            f"Shard warm: {len(self._timings)} process(es) in {wall_s:.1f}s "
            f"(ok={self._ok}, fail={self._fail})",
        ]
        if failed:
            lines.append(f"Failed: {', '.join(failed)}")
        ranked = sorted(self._timings, key=lambda row: row[1], reverse=True)
        show = ranked[:10]
        if show:
            lines.append("Slowest shards:")
            for label, elapsed, code in show:
                mark = "" if code == 0 else " [FAILED]"
                lines.append(f"  {elapsed:6.1f}s  {label}{mark}")
        for line in lines:
            tqdm.write(line, file=sys.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warm league caches using parallel processes (shard by season / league / clubs)."
    )
    parser.add_argument("--database", required=True)
    parser.add_argument("--season", help="Only shard seasons (and scope catalog) for this season")
    parser.add_argument("--league", help="Only shard meta jobs for this league")
    parser.add_argument("--languages", default="de,en")
    parser.add_argument("--rebuild", action="store_true", help="Invalidate cache once before shards")
    parser.add_argument("--warm-clubs", action="store_true")
    parser.add_argument(
        "--clubs-per-shard",
        type=int,
        default=12,
        help="Clubs per club-phase process (default: 12; use 8 or less to fill --max-parallel)",
    )
    parser.add_argument(
        "--club-workers",
        type=int,
        default=0,
        help="Forwarded to each club shard: in-process threads for matrices (GIL-limited; "
        "prefer more shards via --clubs-per-shard)",
    )
    parser.add_argument(
        "--meta-monolith",
        action="store_true",
        help="One league-wide process for all leagues (default: one process per league)",
    )
    parser.add_argument("--skip-seasons", action="store_true")
    parser.add_argument("--skip-meta", action="store_true")
    parser.add_argument("--skip-clubs", action="store_true")
    parser.add_argument(
        "--standings-no-division-grid",
        action="store_true",
        help="Forwarded to each shard",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print shard commands only")
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 4))),
        help="Max concurrent shard processes (default: min(8, CPU count))",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each shard command, stream child stdout, per-endpoint logs",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable shard-level tqdm (line-per-shard log instead)",
    )
    args = parser.parse_args()
    quiet_children = not args.verbose

    if args.clubs_per_shard < 1:
        print("--clubs-per-shard must be >= 1", file=sys.stderr)
        return 1
    if args.max_parallel < 1:
        print("--max-parallel must be >= 1", file=sys.stderr)
        return 1

    database = args.database.strip()
    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")

    print(f"Catalog: loading scope for {database!r} …", flush=True)
    try:
        catalog = fetch_catalog(database, season=args.season, league=args.league)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    shards = build_warm_shards(
        catalog,
        warm_clubs=args.warm_clubs,
        skip_seasons=args.skip_seasons,
        skip_meta=args.skip_meta,
        skip_clubs=args.skip_clubs,
        meta_per_league=not args.meta_monolith,
        clubs_per_shard=args.clubs_per_shard,
        season_filter=args.season,
        league_filter=args.league,
    )
    if not shards:
        print("No shards to run.", flush=True)
        return 0

    child_extra = [
        "--languages",
        args.languages,
        "--sequential",
        "--no-progress",
    ]
    if quiet_children:
        child_extra.append("--quiet")
    if args.standings_no_division_grid:
        child_extra.append("--standings-no-division-grid")
    if args.verbose:
        child_extra.append("--verbose")
    if args.dry_run:
        child_extra.append("--dry-run")
    if args.club_workers > 0:
        child_extra.extend(["--club-workers", str(args.club_workers)])

    print(
        f"Shard plan: {len(shards)} process(es), max_parallel={args.max_parallel} "
        f"({len(catalog.get('seasons') or [])} season(s), "
        f"{len(catalog.get('leagues') or [])} league(s), "
        f"{len(catalog.get('clubs') or [])} club(s))",
        flush=True,
    )

    if args.verbose or args.dry_run:
        for shard in shards:
            cmd = (
                _python_invocation()
                + ["--database", database]
                + shard.argv
                + list(shard.extra_argv)
                + child_extra
            )
            print(f"  [{shard.label}] {' '.join(cmd)}", flush=True)

    if args.dry_run:
        return 0

    if args.rebuild:
        from app import create_app
        from app.cache.league_response_cache import league_cache_invalidate_database

        app = create_app()
        with app.app_context():
            removed = league_cache_invalidate_database(database)
        print(f"Rebuild: removed {removed} cached file(s) for {database!r}", flush=True)

    env = os.environ.copy()
    env["LEAGUE_CACHE_WARM_ON_START"] = "0"
    failed: List[str] = []
    t_wall = time.perf_counter()
    progress = ShardProgress(
        len(shards),
        database=database,
        disable=args.no_progress or args.verbose,
    )

    def _submit(executor: ThreadPoolExecutor, shard: WarmShard):
        return executor.submit(
            _run_one_shard,
            database,
            shard,
            extra_args=child_extra,
            env=env,
            quiet=quiet_children,
        )

    try:
        with ThreadPoolExecutor(max_workers=args.max_parallel) as executor:
            fut_to_shard = {_submit(executor, s): s for s in shards}
            pending = set(fut_to_shard)
            done_n = 0
            while pending:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for fut in finished:
                    shard = fut_to_shard[fut]
                    done_n += 1
                    try:
                        result = fut.result()
                    except Exception as exc:
                        if args.verbose or args.no_progress:
                            print(f"[{done_n}/{len(shards)}] {shard.label} FAILED: {exc}", flush=True)
                        failed.append(shard.label)
                        progress.complete(
                            {
                                "label": shard.label,
                                "code": 1,
                                "elapsed": 0.0,
                                "stderr_tail": str(exc),
                            }
                        )
                        continue
                    if args.verbose or args.no_progress:
                        status = "ok" if result["code"] == 0 else f"exit {result['code']}"
                        print(
                            f"[{done_n}/{len(shards)}] {result['label']} {status} "
                            f"({result['elapsed']:.1f}s)",
                            flush=True,
                        )
                    if result["code"] != 0:
                        failed.append(result["label"])
                        if result["stderr_tail"]:
                            from tqdm import tqdm

                            tqdm.write(
                                f"--- {result['label']} stderr ---\n{result['stderr_tail']}",
                                file=sys.stdout,
                            )
                    progress.complete(result)
    finally:
        progress.close()

    wall = time.perf_counter() - t_wall
    progress.print_timing_summary(wall, failed=failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
