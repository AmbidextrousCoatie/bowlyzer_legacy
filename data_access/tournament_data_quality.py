"""Per-tournament data quality audit (player IDs, names, clubs)."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

import pandas as pd

from app.utils.tournament_utils import normalize_tournament_group_name
from data_access.clubs_registry import (
    build_alias_to_canonical,
    club_identity_key,
    load_clubs_registry_df,
    propose_club_resolution,
    resolve_club_label,
)
from data_access.player_id_name_normalization import normalize_player_id
from data_access.player_name_normalization import normalize_player_label
from data_access.schema import Columns
from data_access.text_norm import normalize_unicode_label

TOURNAMENT_DATA_QUALITY_CSV = "tournament_data_quality.csv"

EVENT_COL_LEGACY = "Event Name"


def resolve_tournament_event_column(df: pd.DataFrame) -> str | None:
    """Published v2 uses ``Event``; legacy CSVs use ``Event Name``."""
    for col in (Columns.event, EVENT_COL_LEGACY, Columns.event_name):
        if col in df.columns:
            return col
    return None


def event_series(df: pd.DataFrame) -> pd.Series:
    col = resolve_tournament_event_column(df)
    if col is None:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[col].fillna("").astype(str).str.strip()


@dataclass
class TournamentQualityRow:
    season: str
    event_name: str
    tournament_group: str = ""
    row_count: int = 0
    player_count: int = 0
    missing_player_id: int = 0
    missing_club: int = 0
    club_unknown: int = 0
    club_resolved: int = 0
    club_names_normalized: int = 0
    player_id_remap_rows: int = 0
    registry_rows_changed: int = 0
    same_name_different_ids: int = 0
    same_id_different_names: int = 0
    status: str = "green"
    findings: List[str] = field(default_factory=list)
    notes: str = ""


def _player_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if Columns.player_name not in df.columns:
        return df.iloc[0:0]
    work = df.copy()
    work["_name"] = work[Columns.player_name].fillna("").astype(str).map(normalize_player_label)
    return work[work["_name"].astype(bool)]


def _count_same_name_different_ids(group: pd.DataFrame) -> int:
    names = group[Columns.player_name].fillna("").astype(str).map(normalize_player_label)
    issues = 0
    for name, sub in group.groupby(names, dropna=False):
        if not str(name).strip():
            continue
        ids = {
            normalize_player_id(value)
            for value in sub[Columns.player_id].tolist()
            if normalize_player_id(value)
        }
        if len(ids) > 1:
            issues += 1
    return issues


def _count_same_id_different_names(group: pd.DataFrame) -> int:
    ids = group[Columns.player_id].fillna("").astype(str).map(normalize_player_id)
    issues = 0
    for pid, sub in group.groupby(ids, dropna=False):
        if not str(pid).strip():
            continue
        names = {
            normalize_player_label(value)
            for value in sub[Columns.player_name].tolist()
            if normalize_player_label(value)
        }
        if len(names) > 1:
            issues += 1
    return issues


def _status_for_counts(
    *,
    same_name_different_ids: int,
    same_id_different_names: int,
    missing_player_id: int,
    missing_club: int,
    club_unknown: int,
) -> str:
    if same_name_different_ids > 0 or same_id_different_names > 0:
        return "red"
    if missing_player_id > 0 or missing_club > 0 or club_unknown > 0:
        return "yellow"
    return "green"


def _findings_for_row(item: TournamentQualityRow) -> List[str]:
    lines: List[str] = []
    if item.missing_player_id:
        lines.append(f"missing_player_id: {item.missing_player_id}")
    if item.missing_club:
        lines.append(f"missing_club: {item.missing_club}")
    if item.club_unknown:
        lines.append(f"club_unknown: {item.club_unknown}")
    if item.club_resolved:
        lines.append(f"club_resolved: {item.club_resolved}")
    if item.same_name_different_ids:
        lines.append(f"same_name_different_ids: {item.same_name_different_ids}")
    if item.same_id_different_names:
        lines.append(f"same_id_different_names: {item.same_id_different_names}")
    if item.club_names_normalized:
        lines.append(f"club_names_normalized: {item.club_names_normalized}")
    if item.player_id_remap_rows:
        lines.append(f"player_id_remap_rows: {item.player_id_remap_rows}")
    if item.registry_rows_changed:
        lines.append(f"registry_rows_changed: {item.registry_rows_changed}")
    return lines


def _count_club_issues(
    players: pd.DataFrame,
    alias_lookup: Mapping[str, str],
    canonical_names: Sequence[str],
) -> Tuple[int, int, int]:
    """missing, unknown (non-empty unresolved), resolved (canonical match)."""
    if players.empty or Columns.club not in players.columns:
        return 0, 0, 0
    missing = 0
    unknown = 0
    resolved = 0
    for raw in players[Columns.club].tolist():
        text = normalize_unicode_label(raw)
        if not text:
            missing += 1
            continue
        canonical, _rule = resolve_club_label(text, alias_lookup, canonical_names)
        if canonical:
            if club_identity_key(canonical) == club_identity_key(text):
                resolved += 1
            else:
                resolved += 1
        else:
            unknown += 1
    return missing, unknown, resolved


def audit_tournament_data_quality(
    df: pd.DataFrame,
    *,
    seasons: Optional[Sequence[str]] = None,
    events: Optional[Sequence[str]] = None,
    per_event_norm_stats: Optional[Mapping[tuple[str, str], Mapping[str, int]]] = None,
) -> List[TournamentQualityRow]:
    """One quality row per season × event_name."""
    if df is None or df.empty:
        return []
    if Columns.season not in df.columns or resolve_tournament_event_column(df) is None:
        return []

    work = df.copy()
    work[Columns.season] = work[Columns.season].fillna("").astype(str).str.strip()
    work["__event"] = event_series(work)
    if seasons:
        wanted = {str(s).strip() for s in seasons}
        work = work[work[Columns.season].isin(wanted)]
    if events:
        wanted_events = {str(e).strip() for e in events}
        work = work[work["__event"].isin(wanted_events)]
    if work.empty:
        return []

    registry = load_clubs_registry_df()
    alias_lookup = build_alias_to_canonical(registry) if registry is not None else {}
    canonical_names = (
        sorted(registry["canonical_name"].astype(str).tolist()) if registry is not None and not registry.empty else []
    )

    rows: List[TournamentQualityRow] = []
    for (season, event_name), group in work.groupby([Columns.season, "__event"], dropna=False):
        season_s = str(season).strip()
        event_s = str(event_name).strip()
        if not season_s or not event_s:
            continue

        players = _player_rows(group)
        player_count = int(players["_name"].nunique()) if not players.empty else 0
        missing_player_id = 0
        missing_club = 0
        club_unknown = 0
        club_resolved = 0
        if not players.empty and Columns.player_id in players.columns:
            missing_player_id = int(
                players[Columns.player_id].fillna("").astype(str).map(normalize_player_id).eq("").sum()
            )
        if (
            registry is not None
            and not registry.empty
            and not players.empty
            and Columns.club in players.columns
        ):
            missing_club, club_unknown, club_resolved = _count_club_issues(
                players, alias_lookup, canonical_names
            )

        same_name = _count_same_name_different_ids(players) if not players.empty else 0
        same_id = _count_same_id_different_names(players) if not players.empty else 0

        norm_stats = (per_event_norm_stats or {}).get((season_s, event_s), {})
        item = TournamentQualityRow(
            season=season_s,
            event_name=event_s,
            tournament_group=normalize_tournament_group_name(event_s),
            row_count=int(len(group)),
            player_count=player_count,
            missing_player_id=missing_player_id,
            missing_club=missing_club,
            club_unknown=club_unknown,
            club_resolved=club_resolved,
            club_names_normalized=int(norm_stats.get("club_registry_rows_changed") or 0),
            player_id_remap_rows=int(norm_stats.get("player_id_rows_changed") or 0),
            registry_rows_changed=int(norm_stats.get("registry_rows_changed") or 0),
            same_name_different_ids=same_name,
            same_id_different_names=same_id,
            status=_status_for_counts(
                same_name_different_ids=same_name,
                same_id_different_names=same_id,
                missing_player_id=missing_player_id,
                missing_club=missing_club,
                club_unknown=club_unknown,
            ),
        )
        item.findings = _findings_for_row(item)
        rows.append(item)

    rows.sort(key=lambda row: (row.season, row.event_name))
    return rows


def comparison_summary_from_dicts(rows: Sequence[Mapping[str, object]]) -> Dict[str, int]:
    summary = {"green": 0, "yellow": 0, "red": 0, "detail_rows": len(rows)}
    for row in rows:
        status = str(row.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def comparison_summary_for_manifest(rows: Sequence[TournamentQualityRow]) -> Dict[str, int]:
    summary = {"green": 0, "yellow": 0, "red": 0}
    for row in rows:
        status = str(row.status or "")
        if status in summary:
            summary[status] += 1
    summary["detail_rows"] = len(rows)
    return summary


def write_quality_report(rows: Sequence[TournamentQualityRow], out_path: Path) -> None:
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "season",
        "event_name",
        "tournament_group",
        "row_count",
        "player_count",
        "missing_player_id",
        "missing_club",
        "club_unknown",
        "club_resolved",
        "club_names_normalized",
        "player_id_remap_rows",
        "registry_rows_changed",
        "same_name_different_ids",
        "same_id_different_names",
        "status",
        "findings",
        "notes",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for item in rows:
            row = asdict(item)
            row["findings"] = "||".join(item.findings)
            writer.writerow(row)


def format_quality_report(
    rows: Sequence[TournamentQualityRow],
    *,
    data_path: Path | None = None,
) -> str:
    summary = comparison_summary_for_manifest(rows)
    prefix = f"Tournament data quality for {data_path}" if data_path else "Tournament data quality"
    lines = [
        prefix + ":",
        f"  events: {summary['detail_rows']}",
        f"  green: {summary['green']}  yellow: {summary['yellow']}  red: {summary['red']}",
    ]
    for item in rows:
        if item.status == "green":
            continue
        lines.append(
            f"  [{item.status}] {item.season} · {item.event_name}: "
            + ", ".join(item.findings or ["(no findings)"])
        )
    if summary["detail_rows"] and summary["red"] == 0 and summary["yellow"] == 0:
        lines[0] = prefix.replace(":", "") + ": OK"
    return "\n".join(lines)


def parse_findings_cell(raw: str) -> List[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    if "||" in text:
        return [part for part in text.split("||") if part]
    return [text]
