#!/usr/bin/env python3
"""
Build ``database/config/team_name_normalization.json`` from an annotated cluster CSV.

The annotated export has one ``proposed_canonical_name`` per ``cluster_id`` (forward-filled).
Generates regex rules per cluster, merges with existing rules (including any legacy
``team_name_regex_map_ignored`` entries when re-reading an old config), consolidates
duplicates, and orders patterns so specific rules win over broad ones in
``normalize_team_name`` (single-pass, first match). Output contains only
``team_name_regex_map`` — no ignored stash.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Set, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.audit_team_name_clusters import (  # noqa: E402
    ClubCluster,
    comparison_key,
    propose_regex_patterns,
    split_club_and_team_number,
)

_CONFIG_PATH = REPO_ROOT / "database" / "config" / "team_name_normalization.json"


@dataclass
class AnnotationCluster:
    cluster_id: int
    canonical: str
    team_names: Set[str] = field(default_factory=set)


def load_annotated_clusters(path: Path) -> Tuple[List[AnnotationCluster], List[str]]:
    """Load clusters; return (clusters, validation_errors)."""
    df = pd.read_csv(path, sep=";", dtype=str).fillna("")
    errors: List[str] = []
    if "cluster_id" not in df.columns or "team_name" not in df.columns:
        return [], ["CSV must have cluster_id and team_name columns"]
    canon_col = "proposed_canonical_name"
    if canon_col not in df.columns:
        return [], [f"CSV must have {canon_col} column"]

    df[canon_col] = df[canon_col].replace("", pd.NA).ffill()
    empty = df[df[canon_col].str.strip() == ""]
    if not empty.empty:
        errors.append(f"{len(empty)} rows missing canonical after forward-fill")

    by_id: Dict[int, AnnotationCluster] = {}
    for cid_raw, group in df.groupby("cluster_id"):
        try:
            cid = int(str(cid_raw).strip())
        except ValueError:
            errors.append(f"invalid cluster_id: {cid_raw!r}")
            continue
        canon_vals = group[canon_col].astype(str).str.strip().unique()
        if len(canon_vals) != 1:
            errors.append(f"cluster {cid}: multiple canonicals {canon_vals.tolist()}")
            continue
        canonical = canon_vals[0]
        if not canonical:
            errors.append(f"cluster {cid}: empty canonical")
            continue
        names = {str(n).strip() for n in group["team_name"] if str(n).strip()}
        by_id[cid] = AnnotationCluster(cluster_id=cid, canonical=canonical, team_names=names)

    return sorted(by_id.values(), key=lambda c: c.cluster_id), errors


def _cluster_for_regex(ann: AnnotationCluster) -> ClubCluster:
    club_members = {split_club_and_team_number(n)[0] for n in ann.team_names}
    return ClubCluster(
        cluster_id=ann.cluster_id,
        club_members=club_members,
        team_names=set(ann.team_names),
    )


def patterns_from_annotations(clusters: Iterable[AnnotationCluster]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for ann in clusters:
        if len(ann.team_names) < 1:
            continue
        cluster = _cluster_for_regex(ann)
        for pattern, replacement, _note in propose_regex_patterns(cluster, ann.canonical):
            if pattern in out and out[pattern] != replacement:
                raise ValueError(
                    f"cluster {ann.cluster_id}: pattern collision {pattern!r}: "
                    f"{out[pattern]!r} vs {replacement!r}"
                )
            out[pattern] = replacement
    return out


def load_existing_maps(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    merged: Dict[str, str] = {}
    for key in ("team_name_regex_map", "team_name_regex_map_ignored"):
        block = payload.get(key, {})
        if not isinstance(block, dict):
            continue
        for pat, repl in block.items():
            pat_s = str(pat).strip()
            repl_s = str(repl).strip()
            if not pat_s or not repl_s:
                continue
            if pat_s in merged and merged[pat_s] != repl_s:
                print(
                    f"Warning: pattern {pat_s!r} in {key} differs: "
                    f"{merged[pat_s]!r} vs {repl_s!r}; keeping active map value",
                    file=sys.stderr,
                )
                continue
            merged[pat_s] = repl_s
    return merged


def _pattern_specificity(pattern: str) -> Tuple[int, int, int]:
    """Higher tuple = apply earlier (more specific)."""
    anchored = int(pattern.startswith("^")) + int(pattern.endswith("$"))
    wild = pattern.count(".*") + pattern.count("(?:") + pattern.count("[^")
    broad_digit = int("(?:\\s+[^\\d]*)?" in pattern or "(?:\\s+[^\\d]" in pattern)
    literal_bonus = len(re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", pattern))
    return (anchored * 10 - wild * 3 - broad_digit * 5 + literal_bonus, -len(pattern), anchored)


def sort_regex_map(mapping: Mapping[str, str]) -> Dict[str, str]:
    items = sorted(mapping.items(), key=lambda kv: (_pattern_specificity(kv[0]), kv[0]))
    return dict(items)


def _flex_pattern_matches(flex_pattern: str, name: str) -> bool:
    try:
        return bool(re.match(flex_pattern, name))
    except re.error:
        return False


def _is_full_literal_pattern(pattern: str) -> bool:
    if not (pattern.startswith("^") and pattern.endswith("$")):
        return False
    inner = pattern[1:-1]
    return "(?:" not in inner and ".*" not in inner and "[" not in inner and "(?!" not in inner


def consolidate_patterns(
    mapping: Mapping[str, str],
    known_names: Iterable[str] | None = None,
    *,
    only_patterns: Set[str] | None = None,
) -> Dict[str, str]:
    """
    Drop literal patterns already covered by a flexible rule with the same replacement.

    When ``only_patterns`` is set, only those keys are candidates for removal (keeps
    legacy rules that use alternate regex spellings for the same club).
    """
    names = list(known_names or [])
    if not names:
        return dict(mapping)

    drop: Set[str] = set()
    by_replacement: Dict[str, List[str]] = defaultdict(list)
    for pat, repl in mapping.items():
        by_replacement[repl].append(pat)

    for repl, patterns in by_replacement.items():
        flex_pats = [p for p in patterns if "(?:\\s+(\\d+))?$" in p]
        for pat in patterns:
            if only_patterns is not None and pat not in only_patterns:
                continue
            if pat in flex_pats or not _is_full_literal_pattern(pat):
                continue
            matched = [n for n in names if re.match(pat, n)]
            if matched and all(
                any(_flex_pattern_matches(fp, n) for fp in flex_pats) for n in matched
            ):
                drop.add(pat)

    return {k: v for k, v in mapping.items() if k not in drop}


def merge_maps(
    existing: Mapping[str, str],
    annotated: Mapping[str, str],
    *,
    annotated_wins: bool = True,
) -> Dict[str, str]:
    merged = dict(existing)
    for pat, repl in annotated.items():
        if pat in merged and merged[pat] != repl:
            if annotated_wins:
                print(
                    f"Override: {pat!r} {merged[pat]!r} -> {repl!r}",
                    file=sys.stderr,
                )
            else:
                print(f"Keep existing: {pat!r} = {merged[pat]!r}", file=sys.stderr)
                continue
        merged[pat] = repl
    return merged


def apply_regex_map(name: str, regex_map: Mapping[str, str]) -> str:
    text = re.sub(r"\s+", " ", str(name or "").strip())
    for pattern, replacement in regex_map.items():
        try:
            updated = re.sub(pattern, replacement, text, count=1)
        except re.error:
            continue
        if updated != text:
            return re.sub(r"\s+", " ", updated).strip()
    return text


def validate_annotations(
    clusters: Iterable[AnnotationCluster],
    regex_map: Mapping[str, str],
) -> List[str]:
    issues: List[str] = []
    for ann in clusters:
        for name in ann.team_names:
            club, num = split_club_and_team_number(name)
            got = apply_regex_map(name, regex_map)
            got_club, got_num = split_club_and_team_number(got)
            if comparison_key(got_club) != comparison_key(ann.canonical):
                issues.append(
                    f"cluster {ann.cluster_id}: {name!r} -> {got!r} "
                    f"(expected club {ann.canonical!r})"
                )
            elif num and not got_num:
                issues.append(f"cluster {ann.cluster_id}: {name!r} lost team number -> {got!r}")
    return issues


def build_payload(regex_map: Mapping[str, str]) -> dict:
    return {"team_name_regex_map": sort_regex_map(dict(regex_map))}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "annotated_csv",
        type=Path,
        help="Annotated cluster report (proposed_canonical_name per cluster_id)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_CONFIG_PATH,
        help="Output team_name_normalization.json path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print stats without writing config",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write validation report JSON",
    )
    args = parser.parse_args(argv)

    clusters, load_errors = load_annotated_clusters(args.annotated_csv)
    if load_errors:
        for err in load_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"Loaded {len(clusters)} annotated clusters", file=sys.stderr)

    existing_full = load_existing_maps(args.config)

    try:
        from_annotations = patterns_from_annotations(clusters)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    all_names = {n for c in clusters for n in c.team_names}
    merged = merge_maps(existing_full, from_annotations, annotated_wins=True)
    merged = consolidate_patterns(
        merged,
        known_names=all_names,
        only_patterns=set(from_annotations.keys()),
    )
    from scripts.sweep_team_name_normalization import (  # noqa: PLC0415
        collect_test_names,
        sweep_map,
    )

    test_names = collect_test_names(merged, args.annotated_csv)
    merged, sweep_stats = sweep_map(merged, test_names)
    print(
        f"Sweep: {sweep_stats['start']} -> {sweep_stats['end']} "
        f"(-{sweep_stats['merged_literals_removed']} literals merged, "
        f"-{sweep_stats['dead_removed']} dead literals)",
        file=sys.stderr,
    )

    validation = validate_annotations(clusters, merged)
    report = {
        "clusters": len(clusters),
        "patterns_from_annotations": len(from_annotations),
        "patterns_merged_total": len(merged),
        "validation_issues": validation,
        "load_errors": load_errors,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report: {args.report}", file=sys.stderr)

    if validation:
        print(f"Validation: {len(validation)} issues (see report)", file=sys.stderr)
        for line in validation[:30]:
            print(f"  {line}", file=sys.stderr)
        if len(validation) > 30:
            print(f"  ... and {len(validation) - 30} more", file=sys.stderr)
    else:
        print("Validation: all annotated team names normalize to proposed canonical", file=sys.stderr)

    print(
        f"Patterns: {len(existing_full)} existing -> {len(merged)} merged "
        f"({len(from_annotations)} from annotations)",
        file=sys.stderr,
    )

    if args.dry_run:
        return 0 if not validation and not load_errors else 1

    out_payload = build_payload(merged)
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(
        json.dumps(out_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.config} ({len(merged)} active patterns)", file=sys.stderr)
    return 0 if not validation else 1


if __name__ == "__main__":
    raise SystemExit(main())
