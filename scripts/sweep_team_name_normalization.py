#!/usr/bin/env python3
"""
Sweep ``team_name_regex_map`` for redundant per-number literals and dead rules.

- Merges literal runs like ``^Foo\\ Bar\\ 1$`` … ``^Foo\\ Bar\\ 7$`` into ``^Foo\\ Bar\\ (\\d+)$``.
- Drops patterns that never change normalization (earlier rule wins on all test names).
- Re-sorts with the same specificity ordering as ``build_team_name_normalization.py``.

Usage:
  uv run python scripts/sweep_team_name_normalization.py
  uv run python scripts/sweep_team_name_normalization.py --write
  uv run python scripts/sweep_team_name_normalization.py --annotated path/to.csv --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_team_name_normalization import (  # noqa: E402
    _CONFIG_PATH,
    apply_regex_map,
    load_annotated_clusters,
    sort_regex_map,
)

# ^literal escaped name\ 123$  (build script / re.escape output)
_LITERAL_NUM_SUFFIX = re.compile(r"^(\^.+)\\ (\d+)\$$")
# replacement ends with space + digits only
_REPL_NUM_SUFFIX = re.compile(r"^(.*) (\d+)$")


def _literal_pattern_to_sample(pattern: str) -> str | None:
    """Turn ^re.escape(name)$ into a sample team name."""
    if not (pattern.startswith("^") and pattern.endswith("$")):
        return None
    inner = pattern[1:-1]
    try:
        rx = re.compile(pattern)
    except re.error:
        return None
    # Unescape: split on backslash-space and backslash sequences from re.escape
    sample = ""
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt in r".^$*+?{}[]()|":
                sample += nxt
                i += 2
                continue
            if nxt == " ":
                sample += " "
                i += 2
                continue
        sample += inner[i]
        i += 1
    if rx.match(sample):
        return sample
    return None


def _team_names_from_merged_data() -> Set[str]:
    from database.paths import league_results_merged_csv
    from data_access.parquet_sidecar import resolve_load_path

    path = resolve_load_path(league_results_merged_csv())
    if not path.is_file():
        return set()
    import pandas as pd

    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    names: Set[str] = set()
    for col in ("Team", "Opponent"):
        if col in df.columns:
            for value in df[col].dropna().astype(str):
                text = str(value).strip()
                if text:
                    names.add(text)
    return names


def collect_test_names(
    regex_map: Mapping[str, str],
    annotated_csv: Path | None,
    *,
    include_merged_data: bool = True,
) -> Set[str]:
    names: Set[str] = set()
    for pattern in regex_map:
        sample = _literal_pattern_to_sample(pattern)
        if sample:
            names.add(sample)
    if annotated_csv and annotated_csv.is_file():
        clusters, _ = load_annotated_clusters(annotated_csv)
        for cluster in clusters:
            names.update(cluster.team_names)
    if include_merged_data:
        names.update(_team_names_from_merged_data())
    return names


def normalize_with_map(text: str, regex_map: Mapping[str, str]) -> str:
    return apply_regex_map(text, regex_map)


def _winning_pattern(name: str, regex_map: Mapping[str, str]) -> str | None:
    for pat, repl in regex_map.items():
        try:
            updated = re.sub(pat, repl, name, count=1)
        except re.error:
            continue
        if updated != name:
            return pat
    return None


def _is_removable_literal_pattern(pattern: str) -> bool:
    """Only drop unreachable full-string literals (annotation artifacts)."""
    if not (pattern.startswith("^") and pattern.endswith("$")):
        return False
    inner = pattern[1:-1]
    if "(?:" in inner or ".*" in inner or "[" in inner or "(\\d" in inner or "(?!" in inner:
        return False
    return True


def find_unreachable_literal_patterns(
    regex_map: Mapping[str, str],
    test_names: Iterable[str],
) -> List[str]:
    """Unreachable full literals — broad legacy rules are kept even if unused in the test corpus."""
    used: Set[str] = set()
    for name in test_names:
        winner = _winning_pattern(name, regex_map)
        if winner:
            used.add(winner)
    return [
        pat
        for pat in regex_map
        if pat not in used and _is_removable_literal_pattern(pat)
    ]


def _literal_number_groups(
    regex_map: Mapping[str, str],
) -> Dict[Tuple[str, str], List[Tuple[str, int, str]]]:
    """
    Group literal ``^prefix\\ N$`` patterns by (regex_prefix, replacement_base).

    Values: list of (full_pattern, team_number, full_replacement).
    """
    groups: Dict[Tuple[str, str], List[Tuple[str, int, str]]] = defaultdict(list)
    for pattern, replacement in regex_map.items():
        m_pat = _LITERAL_NUM_SUFFIX.match(pattern)
        m_repl = _REPL_NUM_SUFFIX.match(replacement)
        if not m_pat or not m_repl:
            continue
        num = int(m_pat.group(2))
        repl_num = m_repl.group(2)
        if repl_num != str(num):
            continue
        prefix = m_pat.group(1)
        repl_base = m_repl.group(1)
        groups[(prefix, repl_base)].append((pattern, num, replacement))
    return groups


def merge_literal_runs(regex_map: Dict[str, str], *, min_run: int = 2) -> Tuple[Dict[str, str], int]:
    """
    Replace runs of per-number literals with one ``prefix\\ (\\d+)`` rule.

    Inserts the merged rule at the position of the earliest literal in the run.
    """
    order = list(regex_map.keys())
    groups = _literal_number_groups(regex_map)
    to_drop: Set[str] = set()
    insert_at_first_drop: Dict[str, Tuple[str, str]] = {}

    for (prefix, repl_base), items in groups.items():
        if len(items) < min_run:
            continue
        patterns = {p for p, _, _ in items}
        merged_pat = f"{prefix}\\ (\\d+)$"
        merged_repl = f"{repl_base} \\1"
        if merged_pat in regex_map:
            if regex_map[merged_pat] != merged_repl:
                continue
            to_drop.update(patterns)
            continue
        first = min(order.index(p) for p in patterns if p in order)
        anchor = order[first]
        if anchor not in insert_at_first_drop:
            insert_at_first_drop[anchor] = (merged_pat, merged_repl)
        to_drop.update(patterns)

    if not to_drop:
        return regex_map, 0

    final: Dict[str, str] = {}
    merged_inserted: Set[str] = set()
    for key in order:
        if key in insert_at_first_drop:
            merged_pat, merged_repl = insert_at_first_drop[key]
            if merged_pat not in merged_inserted:
                final[merged_pat] = merged_repl
                merged_inserted.add(merged_pat)
        if key in to_drop:
            continue
        final[key] = regex_map[key]

    return final, len(to_drop)


def sweep_map(
    regex_map: Mapping[str, str],
    test_names: Iterable[str],
    *,
    min_literal_run: int = 2,
) -> Tuple[Dict[str, str], dict]:
    stats = {
        "start": len(regex_map),
        "merged_literals_removed": 0,
        "dead_removed": 0,
    }
    current = dict(regex_map)

    merged, n_lit = merge_literal_runs(current, min_run=min_literal_run)
    stats["merged_literals_removed"] = n_lit
    current = merged

    names = set(test_names)
    for _ in range(2):
        removable = find_unreachable_literal_patterns(current, names)
        if not removable:
            break
        for pat in removable:
            del current[pat]
        stats["dead_removed"] += len(removable)

    current = sort_regex_map(current)
    stats["end"] = len(current)
    return current, stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=_CONFIG_PATH,
        help="team_name_normalization.json path",
    )
    parser.add_argument(
        "--annotated",
        type=Path,
        default=Path(r"C:\tmp\bowlyzer\data\team_name_clusters_report_annotated.csv"),
        help="Annotated cluster CSV for regression tests",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write swept map back to config",
    )
    parser.add_argument(
        "--min-run",
        type=int,
        default=2,
        help="Minimum literals in a run to merge (default: 2)",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.config.read_text(encoding="utf-8"))
    regex_map = payload.get("team_name_regex_map", {})
    if not isinstance(regex_map, dict):
        print("ERROR: team_name_regex_map missing or invalid", file=sys.stderr)
        return 1

    test_names = collect_test_names(regex_map, args.annotated)
    swept, stats = sweep_map(regex_map, test_names, min_literal_run=args.min_run)

    regressions: List[str] = []
    for name in sorted(test_names):
        before = normalize_with_map(name, regex_map)
        after = normalize_with_map(name, swept)
        if before != after:
            regressions.append(f"{name!r}: {before!r} -> {after!r}")

    print(
        f"Sweep: {stats['start']} -> {stats['end']} patterns "
        f"(-{stats['merged_literals_removed']} literals merged, "
        f"-{stats['dead_removed']} dead)",
        file=sys.stderr,
    )
    print(f"Test names: {len(test_names)}", file=sys.stderr)
    if regressions:
        print(f"REGRESSIONS: {len(regressions)}", file=sys.stderr)
        for line in regressions[:20]:
            print(f"  {line}", file=sys.stderr)
        return 1

    if args.write:
        out = {"team_name_regex_map": swept}
        args.config.write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.config}", file=sys.stderr)
    else:
        print("Dry run (pass --write to apply)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
