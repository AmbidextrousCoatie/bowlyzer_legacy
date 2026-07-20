#!/usr/bin/env python3
"""
Run API disk-cache warm in parallel OS processes (one Python interpreter per shard).

Covers league (``warm_league_cache.py``), player (``warm_player_cache.py``), and
optionally tournament (``warm_tournament_cache.py``).

Shards:
  - league: seasons, meta/league-wide, clubs, club-legends (see ``warm_league_cache.py``)
  - player: search, seasons list, one process per all-players lifetime season, career merge,
    all-players highest-games (``season=all`` + one process per season), batched per-player
    highest-games (career only), unscoped club-300, batched per-club club-300, batched
    myClub Spieler stacks (club-filtered all-time stats for every canonical club)
  - tournament: single process (internal per-season hit/miss)

Usage:
  uv run python scripts/warm_cache_shard.py --database db_real_merged --warm-all --rebuild --max-parallel 12
  uv run python scripts/warm_cache_shard.py --all-published --rebuild --max-parallel 12
  uv run python scripts/warm_cache_shard.py --database db_real_merged --warm-players --max-parallel 8
  uv run python scripts/warm_cache_shard.py --database db_real_merged --season "25/26" --dry-run

Hit/miss: each shard skips endpoints already on disk (valid revision). Independent of ``--rebuild``.
``--rebuild`` only deletes cache files first (per database), forcing misses on the next warm.

Environment: same as ``warm_league_cache.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict

ROOT = Path(__file__).resolve().parents[1]
LEAGUE_WARM_SCRIPT = ROOT / "scripts" / "warm_league_cache.py"
PLAYER_WARM_SCRIPT = ROOT / "scripts" / "warm_player_cache.py"
TOURNAMENT_WARM_SCRIPT = ROOT / "scripts" / "warm_tournament_cache.py"
LEGACY = ROOT / "league_analyzer_v1"
for _p in (LEGACY, ROOT):
    if _p.is_dir():
        sys.path.insert(0, str(_p))

import importlib.util

PUBLISHED_LEAGUE_DATABASE = "db_real_merged"
PUBLISHED_PLAYER_DATABASE = "db_player_merged_hybrid"
PUBLISHED_TOURNAMENT_DATABASE = "db_tournament_regions_2026_gf"
# One subprocess warms this many players' highest-games caches (career scope only).
PLAYERS_PER_HIGHEST_GAMES_WARM_SHARD = 50

_spec = importlib.util.spec_from_file_location("warm_league_cache_mod", LEAGUE_WARM_SCRIPT)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Could not load warm_league_cache.py")
_warm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _warm
_spec.loader.exec_module(_warm)

WarmShard = _warm.WarmShard
build_warm_shards = _warm.build_warm_shards
seasons_for_warmup = None  # loaded lazily


def _load_player_warm():
    spec = importlib.util.spec_from_file_location("warm_player_cache_mod", PLAYER_WARM_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load warm_player_cache.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass(frozen=True)
class CacheWarmShard:
    label: str
    script: Path
    database: str
    argv: Tuple[str, ...] = ()
    extra_argv: Tuple[str, ...] = ()
    finalize: bool = False


def _python_invocation(script: Path) -> List[str]:
    return ["uv", "run", "python", str(script)]


def fetch_league_catalog(
    database: str,
    *,
    season: Optional[str] = None,
    league: Optional[str] = None,
) -> Dict[str, object]:
    cmd = _python_invocation(LEAGUE_WARM_SCRIPT) + ["--database", database, "--catalog"]
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
        raise RuntimeError(f"league --catalog failed ({proc.returncode}): {err}")
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
    return json.loads(line)


def fetch_player_catalog(player_database: str) -> Dict[str, object]:
    cmd = _python_invocation(PLAYER_WARM_SCRIPT) + [
        "--database",
        player_database,
        "--catalog",
    ]
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
        raise RuntimeError(f"player --catalog failed ({proc.returncode}): {err}")
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout else ""
    return json.loads(line)


def build_cache_warm_shards(
    *,
    league_database: str,
    league_catalog: Dict[str, object],
    player_database: str,
    player_seasons: List[str],
    player_catalog_players: List[Dict[str, object]],
    warm_clubs: bool,
    warm_club_legends: bool,
    warm_players: bool,
    warm_tournament: bool,
    skip_seasons: bool,
    skip_meta: bool,
    skip_clubs: bool,
    skip_club_legends: bool,
    meta_per_league: bool,
    clubs_per_shard: int,
    season_filter: Optional[str],
    league_filter: Optional[str],
    player_clubs_file: Optional[str] = None,
) -> Tuple[List[CacheWarmShard], List[CacheWarmShard]]:
    """Return (parallel_shards, finalize_shards)."""
    from app.cache.cache_warmup import seasons_for_warmup as _seasons_for_warmup

    parallel: List[CacheWarmShard] = []
    finalize: List[CacheWarmShard] = []

    league_shards: List[WarmShard] = build_warm_shards(
        league_catalog,
        warm_clubs=warm_clubs,
        warm_club_legends=warm_club_legends,
        skip_seasons=skip_seasons,
        skip_meta=skip_meta,
        skip_clubs=skip_clubs,
        skip_club_legends=skip_club_legends,
        meta_per_league=meta_per_league,
        clubs_per_shard=clubs_per_shard,
        season_filter=season_filter,
        league_filter=league_filter,
    )
    for shard in league_shards:
        parallel.append(
            CacheWarmShard(
                label=shard.label,
                script=LEAGUE_WARM_SCRIPT,
                database=league_database,
                argv=tuple(shard.argv),
                extra_argv=tuple(shard.extra_argv),
            )
        )

    if warm_players:
        player_mod = _load_player_warm()
        limited_seasons = _seasons_for_warmup(player_seasons)
        catalog_players = [
            {"id": str(p.get("id") or ""), "name": str(p.get("name") or "")}
            for p in player_catalog_players
            if str(p.get("name") or "").strip()
        ]
        catalog_clubs = [
            str(c).strip()
            for c in (league_catalog.get("clubs") or [])
            if str(c).strip()
        ]
        for p_shard in player_mod.build_player_warm_shards(
            limited_seasons,
            players=catalog_players,
            clubs=catalog_clubs,
            clubs_file=player_clubs_file,
            players_per_highest_shard=PLAYERS_PER_HIGHEST_GAMES_WARM_SHARD,
            clubs_per_myclub_shard=clubs_per_shard,
        ):
            target = finalize if p_shard.label == "player:lifetime:all" else parallel
            target.append(
                CacheWarmShard(
                    label=p_shard.label,
                    script=PLAYER_WARM_SCRIPT,
                    database=player_database,
                    argv=p_shard.argv,
                    finalize=p_shard.label == "player:lifetime:all",
                )
            )

    if warm_tournament:
        parallel.append(
            CacheWarmShard(
                label="tournament:all",
                script=TOURNAMENT_WARM_SCRIPT,
                database=PUBLISHED_TOURNAMENT_DATABASE,
                argv=(),
            )
        )

    # Move any finalize-flagged shards out of parallel (safety)
    still_parallel: List[CacheWarmShard] = []
    for shard in parallel:
        if shard.finalize:
            finalize.append(shard)
        else:
            still_parallel.append(shard)
    return still_parallel, finalize


class ShardRunResult(TypedDict):
    label: str
    code: int
    elapsed: float
    stderr_tail: str


def _child_extra_for_script(
    script: Path,
    *,
    languages: str,
    quiet_children: bool,
    standings_no_division_grid: bool,
    verbose: bool,
    dry_run: bool,
    club_workers: int,
) -> List[str]:
    """CLI flags forwarded to shard subprocesses (script-specific)."""
    if script == LEAGUE_WARM_SCRIPT:
        extra: List[str] = [
            "--languages",
            languages,
            "--sequential",
            "--no-progress",
        ]
        if quiet_children:
            extra.append("--quiet")
        if standings_no_division_grid:
            extra.append("--standings-no-division-grid")
        if verbose:
            extra.append("--verbose")
        if dry_run:
            extra.append("--dry-run")
        if club_workers > 0:
            extra.extend(["--club-workers", str(club_workers)])
        return extra

    extra = []
    if script == PLAYER_WARM_SCRIPT:
        if quiet_children:
            extra.append("--quiet")
        if dry_run:
            extra.append("--dry-run")
        return extra

    if script == TOURNAMENT_WARM_SCRIPT:
        if dry_run:
            extra.append("--dry-run")
        return extra

    if quiet_children:
        extra.append("--quiet")
    if dry_run:
        extra.append("--dry-run")
    return extra


def _run_one_shard(
    shard: CacheWarmShard,
    *,
    languages: str,
    quiet_children: bool,
    standings_no_division_grid: bool,
    verbose: bool,
    dry_run: bool,
    club_workers: int,
    env: Dict[str, str],
    quiet: bool,
) -> ShardRunResult:
    extra_args = _child_extra_for_script(
        shard.script,
        languages=languages,
        quiet_children=quiet_children,
        standings_no_division_grid=standings_no_division_grid,
        verbose=verbose,
        dry_run=dry_run,
        club_workers=club_workers,
    )
    cmd = (
        _python_invocation(shard.script)
        + ["--database", shard.database]
        + list(shard.argv)
        + list(shard.extra_argv)
        + extra_args
    )
    t0 = time.perf_counter()
    if quiet:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
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
    def __init__(self, total: int, *, title: str, disable: bool) -> None:
        from tqdm import tqdm

        self._timings: List[Tuple[str, float, int]] = []
        self._pbar = tqdm(
            total=total,
            desc=title,
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
        show = ranked[:12]
        if show:
            lines.append("Slowest shards:")
            for label, elapsed, code in show:
                mark = "" if code == 0 else " [FAILED]"
                lines.append(f"  {elapsed:6.1f}s  {label}{mark}")
        for line in lines:
            tqdm.write(line, file=sys.stdout)


def _run_shard_batch(
    shards: Sequence[CacheWarmShard],
    *,
    database_label: str,
    languages: str,
    quiet_children: bool,
    standings_no_division_grid: bool,
    verbose: bool,
    dry_run: bool,
    club_workers: int,
    env: Dict[str, str],
    max_parallel: int,
    no_progress: bool,
) -> List[str]:
    if not shards:
        return []

    failed: List[str] = []
    t_wall = time.perf_counter()
    progress = ShardProgress(
        len(shards),
        title=f"warm {database_label}",
        disable=no_progress or verbose,
    )

    def _submit(executor: ThreadPoolExecutor, shard: CacheWarmShard):
        return executor.submit(
            _run_one_shard,
            shard,
            languages=languages,
            quiet_children=quiet_children,
            standings_no_division_grid=standings_no_division_grid,
            verbose=verbose,
            dry_run=dry_run,
            club_workers=club_workers,
            env=env,
            quiet=quiet_children,
        )

    try:
        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
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
                        if verbose or no_progress:
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
                    if verbose or no_progress:
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
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Warm API disk caches using parallel processes (league / player / tournament)."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="League source id, e.g. db_real_merged")
    target.add_argument(
        "--all-published",
        action="store_true",
        help=(
            f"Published stack: league={PUBLISHED_LEAGUE_DATABASE}, "
            f"player={PUBLISHED_PLAYER_DATABASE}, tournament={PUBLISHED_TOURNAMENT_DATABASE}"
        ),
    )
    parser.add_argument("--season", help="Limit league/player scope to this season")
    parser.add_argument("--league", help="Only shard meta jobs for this league")
    parser.add_argument("--languages", default="de,en")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Invalidate on-disk cache per warmed database before shards (forces rebuild)",
    )
    parser.add_argument(
        "--warm-all",
        action="store_true",
        help="League clubs + club-legends + player stack + tournament",
    )
    parser.add_argument("--warm-clubs", action="store_true")
    parser.add_argument("--warm-club-legends", action="store_true")
    parser.add_argument(
        "--warm-players",
        action="store_true",
        help="player_search + all-players lifetime (per season + career merge)",
    )
    parser.add_argument("--warm-tournament", action="store_true", help="Full tournament cache warm")
    parser.add_argument("--skip-seasons", action="store_true")
    parser.add_argument("--skip-meta", action="store_true")
    parser.add_argument("--skip-clubs", action="store_true")
    parser.add_argument("--skip-club-legends", action="store_true")
    parser.add_argument("--skip-players", action="store_true")
    parser.add_argument("--skip-tournament", action="store_true")
    parser.add_argument(
        "--clubs-per-shard",
        type=int,
        default=12,
        help="Clubs per club-phase process (default: 12)",
    )
    parser.add_argument("--club-workers", type=int, default=0)
    parser.add_argument("--meta-monolith", action="store_true")
    parser.add_argument("--standings-no-division-grid", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 4))),
        help="Max concurrent shard processes (default: min(8, CPU count))",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    args = parser.parse_args()

    os.environ["LEAGUE_CACHE_WARM_ON_START"] = "0"

    if args.clubs_per_shard < 1:
        print("--clubs-per-shard must be >= 1", file=sys.stderr)
        return 1
    if args.max_parallel < 1:
        print("--max-parallel must be >= 1", file=sys.stderr)
        return 1

    league_database = PUBLISHED_LEAGUE_DATABASE if args.all_published else (args.database or "").strip()
    if not league_database:
        print("--database is required", file=sys.stderr)
        return 1

    from app.utils.league_player_sources import resolve_player_database_id

    player_database = PUBLISHED_PLAYER_DATABASE if args.all_published else resolve_player_database_id(league_database)

    warm_all = args.warm_all or args.all_published
    warm_clubs = warm_all or args.warm_clubs
    warm_club_legends = warm_all or args.warm_club_legends
    warm_players = (warm_all or args.warm_players) and not args.skip_players
    warm_tournament = (warm_all or args.warm_tournament) and not args.skip_tournament

    quiet_children = not args.verbose
    os.environ.setdefault("LEAGUE_CACHE_ENABLED", "1")

    print(f"Catalog: loading league scope for {league_database!r} …", flush=True)
    try:
        league_catalog = fetch_league_catalog(league_database, season=args.season, league=args.league)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    player_seasons: List[str] = []
    player_catalog_players: List[Dict[str, object]] = []
    if warm_players:
        print(f"Catalog: loading player scope for {player_database!r} …", flush=True)
        try:
            player_catalog = fetch_player_catalog(player_database)
            player_seasons = [str(s) for s in (player_catalog.get("seasons") or [])]
            player_catalog_players = list(player_catalog.get("players") or [])
            if args.season:
                player_seasons = [s for s in player_seasons if s == args.season]
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    player_clubs_file: Optional[str] = None
    if warm_players:
        catalog_clubs = [
            str(c).strip()
            for c in (league_catalog.get("clubs") or [])
            if str(c).strip()
        ]
        if catalog_clubs:
            clubs_dir = ROOT / ".cache" / "league" / "_warm_shards"
            clubs_dir.mkdir(parents=True, exist_ok=True)
            clubs_path = clubs_dir / f"player_myclub_clubs__{league_database}.txt"
            clubs_path.write_text("\n".join(catalog_clubs) + "\n", encoding="utf-8")
            player_clubs_file = str(clubs_path)
            print(
                f"Catalog: wrote {len(catalog_clubs)} canonical club(s) for myClub Spieler warm "
                f"-> {clubs_path}",
                flush=True,
            )

    parallel_shards, finalize_shards = build_cache_warm_shards(
        league_database=league_database,
        league_catalog=league_catalog,
        player_database=player_database,
        player_seasons=player_seasons,
        player_catalog_players=player_catalog_players,
        warm_clubs=warm_clubs,
        warm_club_legends=warm_club_legends,
        warm_players=warm_players,
        warm_tournament=warm_tournament,
        skip_seasons=args.skip_seasons,
        skip_meta=args.skip_meta,
        skip_clubs=args.skip_clubs,
        skip_club_legends=args.skip_club_legends,
        meta_per_league=not args.meta_monolith,
        clubs_per_shard=args.clubs_per_shard,
        season_filter=args.season,
        league_filter=args.league,
        player_clubs_file=player_clubs_file,
    )

    all_shards = parallel_shards + finalize_shards
    if not all_shards:
        print("No shards to run.", flush=True)
        return 0

    print(
        f"Shard plan: {len(parallel_shards)} parallel + {len(finalize_shards)} finalize, "
        f"max_parallel={args.max_parallel} "
        f"(league={league_database!r}, player={player_database!r}, "
        f"players={'on' if warm_players else 'off'}, tournament={'on' if warm_tournament else 'off'})",
        flush=True,
    )

    if args.verbose or args.dry_run:
        for shard in all_shards:
            shard_extra = _child_extra_for_script(
                shard.script,
                languages=args.languages,
                quiet_children=quiet_children,
                standings_no_division_grid=args.standings_no_division_grid,
                verbose=args.verbose,
                dry_run=args.dry_run,
                club_workers=args.club_workers,
            )
            cmd = (
                _python_invocation(shard.script)
                + ["--database", shard.database]
                + list(shard.argv)
                + list(shard.extra_argv)
                + shard_extra
            )
            phase = "finalize" if shard.finalize else "parallel"
            print(f"  [{phase}] [{shard.label}] {' '.join(cmd)}", flush=True)

    if args.dry_run:
        return 0

    if args.rebuild:
        os.environ.setdefault("LEAGUE_CACHE_WARM_ON_START", "0")
        os.environ["LEAGUE_CACHE_WARM_ON_START"] = "0"
        from app import create_app
        from app.cache.league_response_cache import league_cache_invalidate_database

        app = create_app()
        with app.app_context():
            removed = league_cache_invalidate_database(league_database)
            print(f"Rebuild: removed {removed} cached file(s) for league {league_database!r}", flush=True)
            if warm_players and player_database != league_database:
                removed_p = league_cache_invalidate_database(player_database)
                print(
                    f"Rebuild: removed {removed_p} cached file(s) for player {player_database!r}",
                    flush=True,
                )
            if warm_tournament:
                removed_t = league_cache_invalidate_database(PUBLISHED_TOURNAMENT_DATABASE)
                print(
                    f"Rebuild: removed {removed_t} cached file(s) for tournament "
                    f"{PUBLISHED_TOURNAMENT_DATABASE!r}",
                    flush=True,
                )

    env = os.environ.copy()
    env["LEAGUE_CACHE_WARM_ON_START"] = "0"

    failed = _run_shard_batch(
        parallel_shards,
        database_label=league_database,
        languages=args.languages,
        quiet_children=quiet_children,
        standings_no_division_grid=args.standings_no_division_grid,
        verbose=args.verbose,
        dry_run=args.dry_run,
        club_workers=args.club_workers,
        env=env,
        max_parallel=args.max_parallel,
        no_progress=args.no_progress,
    )

    if finalize_shards:
        print(f"Finalize phase: {len(finalize_shards)} shard(s) …", flush=True)
        failed_finalize = _run_shard_batch(
            finalize_shards,
            database_label=f"{league_database}+finalize",
            languages=args.languages,
            quiet_children=quiet_children,
            standings_no_division_grid=args.standings_no_division_grid,
            verbose=args.verbose,
            dry_run=args.dry_run,
            club_workers=args.club_workers,
            env=env,
            max_parallel=1,
            no_progress=args.no_progress,
        )
        failed.extend(failed_finalize)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
