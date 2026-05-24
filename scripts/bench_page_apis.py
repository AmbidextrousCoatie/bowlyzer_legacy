#!/usr/bin/env python3
"""Time backend APIs that back specific frontend pages (dev proxy or Flask direct).

Compares against fixed pre-Phase-1 reference timings (shared-cache work not deployed yet).
"""

from __future__ import annotations

import argparse
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Mapping, Sequence

DB = "db_real_merged"

# Pre-Phase-1 baseline: 3-round HTTP bench via :5173, database=db_real_merged (May 2026).
# warm_median_ms = median of 3 rounds; max_ms = worst round in that run.
REF_PRE_OPTIMIZATION: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, float]] = {
    ("/team/get_teams", (("database", DB),)): {"warm_median_ms": 390, "max_ms": 8_511},
    ("/league/get_club_matrix", (("database", DB),)): {"warm_median_ms": 10, "max_ms": 30},
    (
        "/league/get_club_matrix",
        (("club", "BC EMAX Unterföhring"), ("database", DB)),
    ): {"warm_median_ms": 12, "max_ms": 28},
    ("/player/search", (("database", DB),)): {"warm_median_ms": 26, "max_ms": 26_726},
    (
        "/player/get_available_seasons",
        (
            ("database", DB),
            ("player_id", "16007"),
            ("player_name", "Feller, Christian"),
        ),
    ): {"warm_median_ms": 503, "max_ms": 522},
    (
        "/player/get_lifetime_stats",
        (
            ("database", DB),
            ("player_id", "16007"),
            ("player_name", "Feller, Christian"),
            ("season", "all"),
        ),
    ): {"warm_median_ms": 5_442, "max_ms": 5_757},
    ("/league/get_available_seasons", (("database", DB),)): {
        "warm_median_ms": 4_131,
        "max_ms": 8_087,
    },
    (
        "/league/get_season_league_standings",
        (("database", DB), ("season", "10/11")),
    ): {"warm_median_ms": 23, "max_ms": 25},
}

SCENARIO_REF_PRE_OPTIMIZATION: dict[str, dict[str, float]] = {
    "Club history (/club)": {"warm_median_ms": 412, "max_ms": 8_569},
    "Player names (/spieler, no player)": {"warm_median_ms": 26, "max_ms": 26_726},
    "Player career (/spieler + player)": {"warm_median_ms": 5_970, "max_ms": 33_005},
    "League season overview (/liga, season only)": {"warm_median_ms": 4_154, "max_ms": 8_112},
}

ALL_SCENARIOS_REF_PRE_OPTIMIZATION = {"warm_median_ms": 10_561, "max_ms": 76_412}

SCENARIOS: list[tuple[str, list[tuple[str, dict[str, str]]]]] = [
    (
        "Club history (/club)",
        [
            ("/team/get_teams", {"database": DB}),
            ("/league/get_club_matrix", {"database": DB}),
            (
                "/league/get_club_matrix",
                {"database": DB, "club": "BC EMAX Unterföhring"},
            ),
        ],
    ),
    (
        "Player names (/spieler, no player)",
        [
            ("/player/search", {"database": DB}),
        ],
    ),
    (
        "Player career (/spieler + player)",
        [
            ("/player/search", {"database": DB}),
            (
                "/player/get_available_seasons",
                {
                    "database": DB,
                    "player_name": "Feller, Christian",
                    "player_id": "16007",
                },
            ),
            (
                "/player/get_lifetime_stats",
                {
                    "database": DB,
                    "player_name": "Feller, Christian",
                    "player_id": "16007",
                    "season": "all",
                },
            ),
        ],
    ),
    (
        "League season overview (/liga, season only)",
        [
            ("/league/get_available_seasons", {"database": DB}),
            ("/league/get_season_league_standings", {"database": DB, "season": "10/11"}),
        ],
    ),
]


def _endpoint_key(path: str, params: Mapping[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return path, tuple(sorted((str(k), str(v)) for k, v in params.items()))


def _lookup_pre_opt_ref(path: str, params: Mapping[str, str]) -> dict[str, float] | None:
    return REF_PRE_OPTIMIZATION.get(_endpoint_key(path, params))


def _format_timing_line(times: Sequence[float]) -> str:
    if not times:
        return "no samples"
    return (
        f"this run: median={statistics.median(times):,.0f} ms  |  "
        f"initial={times[0]:,.0f} ms  |  max={max(times):,.0f} ms  |  min={min(times):,.0f} ms"
    )


def _format_pre_opt_ref_line(ref: Mapping[str, float]) -> str:
    return (
        f"pre-Phase-1 ref: warm median={ref['warm_median_ms']:,.0f} ms  |  "
        f"max={ref['max_ms']:,.0f} ms"
    )


def _format_vs_ref(median_ms: float, ref: Mapping[str, float]) -> str:
    warm = ref["warm_median_ms"]
    if warm <= 0:
        return ""
    ratio = median_ms / warm
    return f"vs ref warm median: {ratio:.2f}x"


def fetch_once(base: str, path: str, params: dict[str, str], timeout: float) -> tuple[float, int, int]:
    qs = urllib.parse.urlencode(params)
    url = f"{base.rstrip('/')}{path}?{qs}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return elapsed_ms, resp.status, len(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="http://192.168.68.109:5173",
        help="Vite dev server (proxies API) or Flask origin",
    )
    parser.add_argument("--rounds", type=int, default=3, help="Timed rounds per endpoint")
    parser.add_argument(
        "--in-process-cold",
        action="store_true",
        help=(
            "Print adapter cold-load timing for --database in this Python process "
            "(CSV read + metadata index; not the HTTP server)."
        ),
    )
    parser.add_argument(
        "--database",
        default=DB,
        help=f"Database id for --in-process-cold (default: {DB})",
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    print(f"Base URL: {args.base}")
    print(f"Rounds per endpoint: {args.rounds}")
    print(
        "Compare to pre-Phase-1 ref (per-request CSV reload, no metadata index, "
        "limited route cache).\n"
    )

    if args.in_process_cold:
        from data_access.shared_pandas_store import get_shared_pandas_adapter, invalidate_adapter_cache

        invalidate_adapter_cache(args.database)
        t0 = time.perf_counter()
        adapter = get_shared_pandas_adapter(args.database)
        load_ms = (time.perf_counter() - t0) * 1000
        rows = len(adapter.df) if adapter.df is not None else 0
        print(
            f"In-process cold load [{args.database}]: {load_ms:,.0f} ms  "
            f"({rows:,} rows, CSV read + metadata index)\n"
        )

    grand_total = 0.0
    grand_initial = 0.0
    grand_max = 0.0
    for scenario_name, endpoints in SCENARIOS:
        print(f"=== {scenario_name} ===")
        scenario_total = 0.0
        scenario_initial = 0.0
        scenario_max = 0.0
        scenario_ref = SCENARIO_REF_PRE_OPTIMIZATION.get(scenario_name)
        for path, params in endpoints:
            times: list[float] = []
            status = 0
            nbytes = 0
            err: str | None = None
            for _ in range(args.rounds):
                try:
                    ms, status, nbytes = fetch_once(args.base, path, params, args.timeout)
                    times.append(ms)
                except urllib.error.HTTPError as exc:
                    err = f"HTTP {exc.code}"
                    break
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    break
            if err:
                print(f"  FAIL {path}  {err}")
                continue
            med = statistics.median(times)
            scenario_total += med
            scenario_initial += times[0]
            scenario_max += max(times)
            kb = nbytes / 1024
            lines = [
                f"  {path}",
                f"    params: {params}",
                f"    {_format_timing_line(times)}",
            ]
            pre_opt = _lookup_pre_opt_ref(path, params)
            if pre_opt:
                lines.append(f"    {_format_pre_opt_ref_line(pre_opt)}")
                lines.append(f"    {_format_vs_ref(med, pre_opt)}")
            lines.append(f"    status={status}  size={kb:,.1f} KiB")
            print("\n".join(lines))

        scenario_lines = [
            f"  scenario total: median={scenario_total:,.0f} ms  |  "
            f"initial={scenario_initial:,.0f} ms  |  max={scenario_max:,.0f} ms"
        ]
        if scenario_ref:
            scenario_lines.append(f"  {_format_pre_opt_ref_line(scenario_ref)}")
            scenario_lines.append(f"  {_format_vs_ref(scenario_total, scenario_ref)}")
        print("\n".join(scenario_lines) + "\n")

        grand_total += scenario_total
        grand_initial += scenario_initial
        grand_max += scenario_max

    all_ref = ALL_SCENARIOS_REF_PRE_OPTIMIZATION
    print(
        f"=== All scenarios: median={grand_total:,.0f} ms  |  "
        f"initial={grand_initial:,.0f} ms  |  max={grand_max:,.0f} ms"
    )
    print(f"  {_format_pre_opt_ref_line(all_ref)}")
    print(f"  {_format_vs_ref(grand_total, all_ref)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
