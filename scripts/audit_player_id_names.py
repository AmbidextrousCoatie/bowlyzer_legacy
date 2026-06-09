#!/usr/bin/env python3
"""
Report fishy player name / Player ID combinations in flat league or player CSVs.

Purely descriptive — no merging unless driven by external normalization JSON.
Intended for manual external lookup (BV registry, score sheets, …).

Analyses (``--analysis``; default: all):
  - ``MULTI_ID`` — ID consistency (same name → multiple IDs; same ID → multiple names)
  - ``MULTI_NAME`` — name reassembly (same ID → multiple raw names; canonical form)

Issue types:
  - same_name_different_ids — identical player name string maps to >1 Player ID
  - same_id_different_names — identical Player ID maps to >1 player name string
  - same_id_name_variants — MULTI_NAME: same ID, multiple raw names (with canonical_name)

Autoresolve columns (suggestions only — not applied to data):
  - ``majority`` — same_name_different_ids: dominant row_count > ratio × minority;
    tag on **both** rows; only minority gets ``proposed_id``.
  - ``placeholder`` — same_name group contains a dummy ID (all 1s/9s or ≥4 leading
    1s/9s); tag on placeholder row(s) **and** the canonical candidate (most games,
    preferring non-placeholder IDs); placeholder rows get ``proposed_id`` = canonical.
  - ``name_reassembly`` — same_id_name_variants: all raw names share one candidate
    canonical form (including two-token reversal, e.g. ``Köse, Sahin`` / ``Sahin Köse``);
    rows with a differing raw string get ``proposed_name``.
  - ``majority`` (MULTI_NAME) — same_id_name_variants: dominant raw name row_count
    > ratio × minority; tag on **both** rows; only minorities get ``proposed_name``
    (the dominant raw spelling). ``name_reassembly`` wins when all canonical forms match.

Usage:
  uv run python scripts/audit_player_id_names.py database/data/league_results_merged.csv
  uv run python scripts/audit_player_id_names.py database/data/player_stats_merged_plus_tournaments.parquet -o report.csv
  uv run python scripts/audit_player_id_names.py data.parquet --analysis MULTI_NAME -o names.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_access.player_name_normalization import (
    canonicalize_player_name,
    group_canonical_target,
    normalize_player_label,
)
from data_access.schema import Columns

ANALYSIS_MULTI_ID = "MULTI_ID"
ANALYSIS_MULTI_NAME = "MULTI_NAME"
ALL_ANALYSES = (ANALYSIS_MULTI_ID, ANALYSIS_MULTI_NAME)

ISSUE_SAME_NAME = "same_name_different_ids"
ISSUE_SAME_ID = "same_id_different_names"
ISSUE_SAME_ID_NAME_VARIANTS = "same_id_name_variants"

# Rule 1 (same_name_different_ids): dominant ID row_count > ratio × minority row_count.
AUTORESOLVE_MAJORITY = "majority"
MAJORITY_ROW_COUNT_RATIO = 5

# Rule 2: scrape / entry placeholder EDV numbers (ones or nines).
AUTORESOLVE_PLACEHOLDER = "placeholder"
PLACEHOLDER_PREFIX_LEN = 4

# MULTI_NAME rule 1: raw spellings collapse to one canonical ``Family, Given`` form.
AUTORESOLVE_NAME_REASSEMBLY = "name_reassembly"

REPORT_FIELDS = [
    "issue_type",
    "source_file",
    "player_name",
    "player_id",
    "row_count",
    "season_count",
    "seasons",
    "peer_player_ids",
    "peer_player_names",
    "group_size_ids",
    "group_size_names",
    "autoresolve_rule",
    "proposed_id",
    "canonical_name",
    "proposed_name",
]


@dataclass(frozen=True)
class PlayerIdNameConflict:
    issue_type: str
    source_file: str
    player_name: str
    player_id: str
    row_count: int
    season_count: int
    seasons: str
    peer_player_ids: str
    peer_player_names: str
    group_size_ids: int
    group_size_names: int
    autoresolve_rule: str = ""
    proposed_id: str = ""
    canonical_name: str = ""
    proposed_name: str = ""

    def as_row(self) -> Dict[str, str | int]:
        return {
            "issue_type": self.issue_type,
            "source_file": self.source_file,
            "player_name": self.player_name,
            "player_id": self.player_id,
            "row_count": self.row_count,
            "season_count": self.season_count,
            "seasons": self.seasons,
            "peer_player_ids": self.peer_player_ids,
            "peer_player_names": self.peer_player_names,
            "group_size_ids": self.group_size_ids,
            "group_size_names": self.group_size_names,
            "autoresolve_rule": self.autoresolve_rule,
            "proposed_id": self.proposed_id,
            "canonical_name": self.canonical_name,
            "proposed_name": self.proposed_name,
        }


def normalize_player_id(value: object) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw or raw.lower() in {"nan", "none"}:
        return ""
    try:
        return str(int(float(raw)))
    except ValueError:
        return raw


def normalize_player_name(value: object) -> str:
    return normalize_player_label(value)


def is_placeholder_player_id(player_id: str) -> bool:
    """
    True when ID looks like a dummy EDV (all 1s / all 9s, or ≥4 leading 1s or 9s).
    """
    pid = normalize_player_id(player_id)
    if not pid or not pid.isdigit():
        return False
    if set(pid) <= {"1"} or set(pid) <= {"9"}:
        return True
    ones_prefix = "1" * PLACEHOLDER_PREFIX_LEN
    nines_prefix = "9" * PLACEHOLDER_PREFIX_LEN
    return pid.startswith(ones_prefix) or pid.startswith(nines_prefix)


def _canonical_id_among_candidates(counts_by_id: Dict[str, int]) -> str:
    """Candidate with most game rows; prefer non-placeholder IDs when any exist."""
    non_placeholder = {
        pid: count for pid, count in counts_by_id.items() if not is_placeholder_player_id(pid)
    }
    pool = non_placeholder if non_placeholder else counts_by_id
    return sorted(pool.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _placeholder_autoresolve_for_name_group(
    counts_by_id: Dict[str, int],
) -> Dict[str, Tuple[str, str]]:
    """
    When a same-name group has placeholder ID(s), tag placeholders and the
    canonical majority-games row (source ID for remapping).
    """
    empty = ("", "")
    if len(counts_by_id) < 2:
        return {pid: empty for pid in counts_by_id}

    placeholder_ids = [pid for pid in counts_by_id if is_placeholder_player_id(pid)]
    if not placeholder_ids:
        return {pid: empty for pid in counts_by_id}

    canonical_id = _canonical_id_among_candidates(counts_by_id)
    out: Dict[str, Tuple[str, str]] = {pid: empty for pid in counts_by_id}
    out[canonical_id] = (AUTORESOLVE_PLACEHOLDER, "")
    for pid in placeholder_ids:
        if pid != canonical_id:
            out[pid] = (AUTORESOLVE_PLACEHOLDER, canonical_id)
    return out


def _merge_autoresolve_for_name_group(
    counts_by_id: Dict[str, int],
    *,
    ratio: int = MAJORITY_ROW_COUNT_RATIO,
) -> Dict[str, Tuple[str, str]]:
    """Placeholder wins over majority when both apply to the same row."""
    majority = _majority_autoresolve_for_name_group(counts_by_id, ratio=ratio)
    placeholder = _placeholder_autoresolve_for_name_group(counts_by_id)
    out: Dict[str, Tuple[str, str]] = {}
    for pid in counts_by_id:
        ph = placeholder.get(pid, ("", ""))
        maj = majority.get(pid, ("", ""))
        if ph[0]:
            out[pid] = ph
        elif maj[0]:
            out[pid] = maj
        else:
            out[pid] = ("", "")
    return out


def _placeholder_autoresolve_for_same_id_row(player_id: str) -> Tuple[str, str]:
    """same_id_different_names: tag rows whose shared ID is a placeholder."""
    if is_placeholder_player_id(player_id):
        return AUTORESOLVE_PLACEHOLDER, ""
    return "", ""


def _player_input_mask(df) -> "object":
    import pandas as pd

    mask = pd.Series(True, index=df.index)
    player_col = Columns.player_name
    if player_col in df.columns:
        names = df[player_col].fillna("").astype(str).str.strip()
        mask &= names.ne("") & names.str.lower().ne("team total")
    if Columns.input_data in df.columns:
        mask &= df[Columns.input_data].fillna("").astype(str).str.strip().str.lower().isin(
            {"true", "1", "yes", "y", "on"}
        )
    if Columns.computed_data in df.columns:
        mask &= df[Columns.computed_data].fillna("").astype(str).str.strip().str.lower().isin(
            {"false", "0", "no", "n", "off", ""}
        )
    return mask


def _load_player_frame(data_path: Path, *, sep: str = ";"):
    import pandas as pd

    path = data_path.resolve()
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, sep=sep, dtype=str, low_memory=False)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()].copy()
    return df


def _majority_autoresolve_for_name_group(
    counts_by_id: Dict[str, int],
    *,
    ratio: int = MAJORITY_ROW_COUNT_RATIO,
) -> Dict[str, Tuple[str, str]]:
    """
    Per player_id in a same-name group: (autoresolve_rule, proposed_id).

    When dominant row_count > ratio × minority row_count, tag **both** the
    dominant row and each qualifying minority with ``majority``; only minorities
    get ``proposed_id`` (pointing at the dominant ID).
    """
    empty = ("", "")
    if len(counts_by_id) < 2:
        return {pid: empty for pid in counts_by_id}

    ranked = sorted(counts_by_id.items(), key=lambda item: (-item[1], item[0]))
    dominant_id, dominant_count = ranked[0]
    minorities = [
        pid
        for pid, count in ranked[1:]
        if dominant_count > ratio * count
    ]
    if not minorities:
        return {pid: empty for pid in counts_by_id}

    out: Dict[str, Tuple[str, str]] = {pid: empty for pid in counts_by_id}
    out[dominant_id] = (AUTORESOLVE_MAJORITY, "")
    for pid in minorities:
        out[pid] = (AUTORESOLVE_MAJORITY, dominant_id)
    return out


def _prepare_pair_stats(
    data_path: Path,
    *,
    sep: str = ";",
    source_file: str | None = None,
    apply_normalization: bool = True,
) -> Tuple[str, Dict[Tuple[str, str], Dict[str, object]], Dict[str, set[str]], Dict[str, set[str]]] | None:
    from data_access.player_id_name_normalization import apply_player_id_name_normalization
    from data_access.player_name_normalization_config import apply_player_name_normalization

    path = data_path.resolve()
    label = source_file or path.name
    df = _load_player_frame(path, sep=sep)

    name_col = Columns.player_name
    id_col = Columns.player_id
    if name_col not in df.columns or id_col not in df.columns:
        return None

    work = df.loc[_player_input_mask(df), [name_col, id_col]].copy()
    if Columns.season in df.columns:
        work[Columns.season] = df.loc[work.index, Columns.season].fillna("").astype(str).str.strip()
    else:
        work[Columns.season] = ""

    if apply_normalization:
        work, _stats = apply_player_id_name_normalization(work)
        work, _name_stats = apply_player_name_normalization(work)

    work["name"] = work[name_col].map(normalize_player_name)
    work["pid"] = work[id_col].map(normalize_player_id)
    work = work.loc[work["name"].ne("") & work["pid"].ne("")]
    if work.empty:
        return None

    pair_stats: Dict[Tuple[str, str], Dict[str, object]] = {}
    for (name, pid), group in work.groupby(["name", "pid"], sort=False):
        seasons = sorted({str(s).strip() for s in group[Columns.season].tolist() if str(s).strip()})
        pair_stats[(str(name), str(pid))] = {
            "row_count": int(len(group)),
            "seasons": seasons,
        }

    name_to_ids: Dict[str, set[str]] = {}
    id_to_names: Dict[str, set[str]] = {}
    for name, pid in pair_stats:
        name_to_ids.setdefault(name, set()).add(pid)
        id_to_names.setdefault(pid, set()).add(name)

    return label, pair_stats, name_to_ids, id_to_names


def _audit_multi_id(
    label: str,
    pair_stats: Dict[Tuple[str, str], Dict[str, object]],
    name_to_ids: Dict[str, set[str]],
    id_to_names: Dict[str, set[str]],
    *,
    apply_normalization: bool = True,
) -> List[PlayerIdNameConflict]:
    from data_access.player_id_name_normalization import is_different_person_name_group

    conflicts: List[PlayerIdNameConflict] = []

    for name, ids in sorted(name_to_ids.items()):
        if len(ids) < 2:
            continue
        if apply_normalization and is_different_person_name_group(name, set(ids)):
            continue
        sorted_ids = sorted(ids)
        counts_by_id = {pid: int(pair_stats[(name, pid)]["row_count"]) for pid in sorted_ids}
        autoresolve_by_pid = _merge_autoresolve_for_name_group(counts_by_id)
        for pid in sorted_ids:
            stats = pair_stats[(name, pid)]
            peer_ids = [x for x in sorted_ids if x != pid]
            autoresolve_rule, proposed_id = autoresolve_by_pid.get(pid, ("", ""))
            conflicts.append(
                PlayerIdNameConflict(
                    issue_type=ISSUE_SAME_NAME,
                    source_file=label,
                    player_name=name,
                    player_id=pid,
                    row_count=int(stats["row_count"]),
                    season_count=len(stats["seasons"]),
                    seasons="; ".join(stats["seasons"]),
                    peer_player_ids="; ".join(peer_ids),
                    peer_player_names="",
                    group_size_ids=len(sorted_ids),
                    group_size_names=1,
                    autoresolve_rule=autoresolve_rule,
                    proposed_id=proposed_id,
                )
            )

    for pid, names in sorted(id_to_names.items()):
        if len(names) < 2:
            continue
        sorted_names = sorted(names, key=lambda n: n.lower())
        for name in sorted_names:
            stats = pair_stats[(name, pid)]
            peer_names = [x for x in sorted_names if x != name]
            autoresolve_rule, proposed_id = _placeholder_autoresolve_for_same_id_row(pid)
            conflicts.append(
                PlayerIdNameConflict(
                    issue_type=ISSUE_SAME_ID,
                    source_file=label,
                    player_name=name,
                    player_id=pid,
                    row_count=int(stats["row_count"]),
                    season_count=len(stats["seasons"]),
                    seasons="; ".join(stats["seasons"]),
                    peer_player_ids="",
                    peer_player_names="; ".join(peer_names),
                    group_size_ids=1,
                    group_size_names=len(sorted_names),
                    autoresolve_rule=autoresolve_rule,
                    proposed_id=proposed_id,
                )
            )

    return conflicts


def _majority_autoresolve_for_id_name_group(
    counts_by_name: Dict[str, int],
    *,
    ratio: int = MAJORITY_ROW_COUNT_RATIO,
) -> Dict[str, Tuple[str, str]]:
    """
    Per raw name in a same-id group: (autoresolve_rule, proposed_name).

    When dominant row_count > ratio × minority row_count, tag **both** the
    dominant row and each qualifying minority with ``majority``; only minorities
    get ``proposed_name`` (the dominant raw spelling).
    """
    empty = ("", "")
    if len(counts_by_name) < 2:
        return {name: empty for name in counts_by_name}

    ranked = sorted(counts_by_name.items(), key=lambda item: (-item[1], item[0].lower()))
    dominant_name, dominant_count = ranked[0]
    minorities = [
        name for name, count in ranked[1:] if dominant_count > ratio * count
    ]
    if not minorities:
        return {name: empty for name in counts_by_name}

    out: Dict[str, Tuple[str, str]] = {name: empty for name in counts_by_name}
    out[dominant_name] = (AUTORESOLVE_MAJORITY, "")
    for name in minorities:
        out[name] = (AUTORESOLVE_MAJORITY, dominant_name)
    return out


def _merge_autoresolve_for_id_name_group(
    names: Iterable[str],
    counts_by_name: Dict[str, int],
    *,
    ratio: int = MAJORITY_ROW_COUNT_RATIO,
) -> Dict[str, Tuple[str, str, str]]:
    """Combine ``name_reassembly`` (when canonical forms agree) with ``majority``."""
    sorted_names = sorted(set(names), key=lambda n: n.lower())
    canonical_by_name = {name: canonicalize_player_name(name) for name in sorted_names}
    reassembly = _name_reassembly_autoresolve_for_id_group(sorted_names)
    majority = _majority_autoresolve_for_id_name_group(counts_by_name, ratio=ratio)

    out: Dict[str, Tuple[str, str, str]] = {}
    for name in sorted_names:
        r_rule, r_prop, r_canon = reassembly.get(name, ("", "", canonical_by_name[name]))
        m_rule, m_prop = majority.get(name, ("", ""))
        if r_rule:
            out[name] = (r_rule, r_prop, r_canon)
        elif m_rule:
            out[name] = (m_rule, m_prop, canonical_by_name[name])
        else:
            out[name] = ("", "", canonical_by_name[name])
    return out


def _name_reassembly_autoresolve_for_id_group(
    names: Iterable[str],
) -> Dict[str, Tuple[str, str, str]]:
    """
    Per raw name in a same-id group: (autoresolve_rule, proposed_name, canonical_name).

    When every variant shares one candidate canonical form (see
    ``group_canonical_target``), tag all rows with ``name_reassembly``; only rows
    whose raw label differs from that target get ``proposed_name``.
    """
    sorted_names = sorted(set(names), key=lambda n: n.lower())
    canonical_by_name = {name: canonicalize_player_name(name) for name in sorted_names}
    target = group_canonical_target(sorted_names)
    empty = ("", "", "")
    if target is None:
        return {name: (*empty[:2], canonical_by_name.get(name, "")) for name in sorted_names}

    out: Dict[str, Tuple[str, str, str]] = {}
    for name in sorted_names:
        if name == target:
            out[name] = (AUTORESOLVE_NAME_REASSEMBLY, "", target)
        else:
            out[name] = (AUTORESOLVE_NAME_REASSEMBLY, target, target)
    return out


def _audit_multi_name(
    label: str,
    pair_stats: Dict[Tuple[str, str], Dict[str, object]],
    id_to_names: Dict[str, set[str]],
    *,
    apply_normalization: bool = True,
) -> List[PlayerIdNameConflict]:
    from data_access.player_name_normalization_config import is_same_person_name_group

    conflicts: List[PlayerIdNameConflict] = []

    for pid, names in sorted(id_to_names.items()):
        if len(names) < 2:
            continue
        if apply_normalization and is_same_person_name_group(pid, set(names)):
            continue
        sorted_names = sorted(names, key=lambda n: n.lower())
        counts_by_name = {
            name: int(pair_stats[(name, pid)]["row_count"]) for name in sorted_names
        }
        autoresolve_by_name = _merge_autoresolve_for_id_name_group(sorted_names, counts_by_name)
        for name in sorted_names:
            stats = pair_stats[(name, pid)]
            peer_names = [x for x in sorted_names if x != name]
            autoresolve_rule, proposed_name, canonical_name = autoresolve_by_name.get(
                name, ("", "", canonicalize_player_name(name))
            )
            conflicts.append(
                PlayerIdNameConflict(
                    issue_type=ISSUE_SAME_ID_NAME_VARIANTS,
                    source_file=label,
                    player_name=name,
                    player_id=pid,
                    row_count=int(stats["row_count"]),
                    season_count=len(stats["seasons"]),
                    seasons="; ".join(stats["seasons"]),
                    peer_player_ids="",
                    peer_player_names="; ".join(peer_names),
                    group_size_ids=1,
                    group_size_names=len(sorted_names),
                    autoresolve_rule=autoresolve_rule,
                    proposed_id="",
                    canonical_name=canonical_name,
                    proposed_name=proposed_name,
                )
            )

    return conflicts


def _normalize_analyses(analyses: Sequence[str] | None) -> Tuple[str, ...]:
    if not analyses:
        return ALL_ANALYSES
    selected = tuple(dict.fromkeys(analyses))
    unknown = [item for item in selected if item not in ALL_ANALYSES]
    if unknown:
        raise ValueError(f"Unknown analysis: {unknown[0]!r} (expected MULTI_ID or MULTI_NAME)")
    return selected


def audit_player_id_names(
    data_path: Path,
    *,
    sep: str = ";",
    source_file: str | None = None,
    apply_normalization: bool = True,
    analyses: Sequence[str] | None = None,
) -> List[PlayerIdNameConflict]:
    """
    Scan player input rows and return conflict detail rows for the selected analyses.

    When ``apply_normalization`` is true (default), applies
    ``player_id_name_normalization.json`` remaps and skips registered
    ``different_person`` name groups before reporting MULTI_ID same-name issues.
    """
    selected = _normalize_analyses(analyses)
    prepared = _prepare_pair_stats(
        data_path,
        sep=sep,
        source_file=source_file,
        apply_normalization=apply_normalization,
    )
    if prepared is None:
        return []

    label, pair_stats, name_to_ids, id_to_names = prepared
    conflicts: List[PlayerIdNameConflict] = []
    if ANALYSIS_MULTI_ID in selected:
        conflicts.extend(
            _audit_multi_id(
                label,
                pair_stats,
                name_to_ids,
                id_to_names,
                apply_normalization=apply_normalization,
            )
        )
    if ANALYSIS_MULTI_NAME in selected:
        conflicts.extend(
            _audit_multi_name(
                label,
                pair_stats,
                id_to_names,
                apply_normalization=apply_normalization,
            )
        )
    return conflicts


def write_conflict_report(
    conflicts: Sequence[PlayerIdNameConflict],
    out_path: Path,
    *,
    append: bool = False,
) -> None:
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and out_path.is_file() else "w"
    write_header = mode == "w" or not out_path.is_file()
    with out_path.open(mode, encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in conflicts:
            writer.writerow(row.as_row())


def format_summary(
    conflicts: Sequence[PlayerIdNameConflict],
    *,
    data_path: Path,
    report_path: Path | None = None,
    analyses: Sequence[str] | None = None,
) -> str:
    conflicts = list(conflicts)
    selected = _normalize_analyses(analyses)
    same_name = sum(1 for c in conflicts if c.issue_type == ISSUE_SAME_NAME)
    same_id = sum(1 for c in conflicts if c.issue_type == ISSUE_SAME_ID)
    name_variants = sum(1 for c in conflicts if c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS)
    name_groups = len({(c.source_file, c.player_name) for c in conflicts if c.issue_type == ISSUE_SAME_NAME})
    id_groups = len({(c.source_file, c.player_id) for c in conflicts if c.issue_type == ISSUE_SAME_ID})
    variant_groups = len(
        {(c.source_file, c.player_id) for c in conflicts if c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS}
    )
    reassembly_rows = sum(
        1 for c in conflicts if c.autoresolve_rule == AUTORESOLVE_NAME_REASSEMBLY
    )
    name_majority_rows = sum(
        1
        for c in conflicts
        if c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS
        and c.autoresolve_rule == AUTORESOLVE_MAJORITY
    )
    autoresolve_rows = sum(1 for c in conflicts if c.autoresolve_rule)

    lines = [f"Player audit for {data_path} ({', '.join(selected)}):"]
    if ANALYSIS_MULTI_ID in selected:
        lines.extend(
            [
                f"  same_name_different_ids: {name_groups} name(s), {same_name} detail row(s)",
                f"  same_id_different_names: {id_groups} id(s), {same_id} detail row(s)",
            ]
        )
    if ANALYSIS_MULTI_NAME in selected:
        lines.append(
            f"  same_id_name_variants: {variant_groups} id(s), {name_variants} detail row(s)"
        )
        lines.append(f"  name_reassembly suggestions: {reassembly_rows} row(s)")
        lines.append(f"  name majority suggestions: {name_majority_rows} row(s)")
    lines.append(f"  autoresolve suggestions (all rules): {autoresolve_rows} row(s)")
    if report_path is not None:
        lines.append(f"  report: {report_path}")
    if not conflicts:
        lines[0] = f"OK: no player audit findings in {data_path} ({', '.join(selected)})"
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit player name vs Player ID consistency.")
    parser.add_argument("data", type=Path, help="League or player CSV/Parquet")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write conflict detail CSV (default: print summary only)",
    )
    parser.add_argument("--sep", default=";", help="CSV delimiter when reading .csv")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip player_id_name_normalization.json (report unresolved conflicts only)",
    )
    parser.add_argument(
        "--analysis",
        choices=list(ALL_ANALYSES),
        action="append",
        dest="analyses",
        metavar="ANALYSIS",
        help="Run only MULTI_ID and/or MULTI_NAME (default: both)",
    )
    args = parser.parse_args()

    data_path = args.data.resolve()
    if not data_path.is_file():
        print(f"File not found: {data_path}", file=sys.stderr)
        return 2

    conflicts = audit_player_id_names(
        data_path,
        sep=args.sep,
        apply_normalization=not args.raw,
        analyses=args.analyses,
    )
    if args.output:
        write_conflict_report(conflicts, args.output)
        print(
            format_summary(
                conflicts,
                data_path=data_path,
                report_path=args.output.resolve(),
                analyses=args.analyses,
            )
        )
    else:
        print(format_summary(conflicts, data_path=data_path, analyses=args.analyses))
        for row in conflicts[:20]:
            print(
                f"  [{row.issue_type}] {row.player_name!r} id={row.player_id} "
                f"rows={row.row_count} peers="
                f"{row.peer_player_ids or row.peer_player_names}"
            )
        if len(conflicts) > 20:
            print(f"  ... and {len(conflicts) - 20} more (use -o report.csv)")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
