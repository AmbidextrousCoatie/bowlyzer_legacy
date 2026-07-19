"""Rangliste (*Aktive Mitglieder*) affiliation index and Verein registry."""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import pandas as pd

from data_access.aktive_mitglieder_registry import (
    AktiveParseStats,
    AktivePlayerRow,
    discover_local_aktive_workbooks,
    is_einzelmitglied_club,
    parse_aktive_workbook,
)
from data_access.clubs_registry import club_identity_key
from data_access.player_id_name_normalization import normalize_player_id
from data_access.text_norm import normalize_unicode_label
from data_access.tournament_coverage import folder_slug_to_app_season

AFFILIATION_COLUMNS = (
    "player_id",
    "season",
    "club_raw",
    "verein_raw",
    "club_canonical",
    "verein_canonical",
    "is_einzelmitglied",
    "source",
    "updated_at",
)

VEREINE_REGISTRY_COLUMNS = (
    "canonical_verein",
    "aliases",
    "member_clubs",
    "source",
    "updated_at",
)

AFFILIATION_FORMAT_VERSION = 1
VEREINE_FORMAT_VERSION = 1

# ``BV 68 Regensburg``, ``1. BBV Lindau``
_VEREIN_HEURISTIC_RE = re.compile(
    r"^(?:\d+\.\s*)?(?:BV|BBV|BFV|BKV|BSV|BSC|BF)\b",
    re.IGNORECASE,
)


def _affiliation_index_path() -> Path:
    from database.paths import affiliation_index_csv

    return affiliation_index_csv()


def _vereine_registry_path() -> Path:
    from database.paths import vereine_registry_csv

    return vereine_registry_csv()


def _rangliste_crosswalk_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "database"
        / "relational_csv"
        / "rangliste_club_crosswalk.csv"
    )


def _split_pipe_list(raw: object) -> List[str]:
    return [part.strip() for part in str(raw or "").split("|") if part.strip()]


def _join_pipe(values: Iterable[str]) -> str:
    seen: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return "|".join(seen)


def verein_identity_key(label: object) -> str:
    return normalize_unicode_label(label).casefold()


def canonicalize_verein_label(label: object) -> str:
    return normalize_unicode_label(label)


@lru_cache(maxsize=1)
def load_rangliste_club_crosswalk() -> Dict[str, str]:
    """
    Manual Rangliste club label -> league ``clubs_registry`` canonical name.

    Unmapped Rangliste clubs keep ``club_raw`` as ``club_canonical`` and are
    reported as crosswalk gaps.
    """
    path = _rangliste_crosswalk_path()
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw = normalize_unicode_label(row.get("rangliste_club") or "")
            canonical = normalize_unicode_label(row.get("canonical_club") or "")
            if not raw or not canonical:
                continue
            key = club_identity_key(raw)
            if key and key not in out:
                out[key] = canonical
    return out


def resolve_rangliste_club_canonical(club_raw: object, crosswalk: Mapping[str, str]) -> Tuple[str, bool]:
    """Return ``(canonical, crosswalk_hit)``.

    Resolution order: explicit ``rangliste_club_crosswalk.csv``, then
    ``club_mapping.csv`` aliases (same durable Club renames as league/tournaments).
    """
    text = normalize_unicode_label(club_raw)
    if not text or is_einzelmitglied_club(text):
        return "", False
    hit = crosswalk.get(club_identity_key(text))
    if hit:
        return hit, True
    from data_access.clubs_registry import canonicalize_club_via_mapping

    mapped = canonicalize_club_via_mapping(text)
    if mapped and mapped != text:
        return mapped, True
    return text, False


def looks_like_verein_label(label: object) -> bool:
    text = normalize_unicode_label(label)
    if not text:
        return False
    if is_einzelmitglied_club(text):
        return False
    return bool(_VEREIN_HEURISTIC_RE.search(text))


@dataclass
class AffiliationBuildStats:
    seasons_selected: int = 0
    workbooks_parsed: int = 0
    workbooks_failed: int = 0
    affiliation_rows: int = 0
    unique_player_seasons: int = 0
    crosswalk_gaps: int = 0
    unique_vereine: int = 0
    league_rows_added: int = 0
    failures: List[str] = field(default_factory=list)


def _collect_affiliation_rows(
    root: Optional[Path] = None,
    *,
    min_season: Optional[str] = None,
) -> Tuple[List[AktivePlayerRow], AktiveParseStats]:
    """
    Collect Aktive rows for the affiliation index.

    Unlike ``players_registry`` (which floors at 2008-09 by default), affiliation
    includes **all** seasons unless ``min_season`` is an explicit folder slug.
    Pre-06/07 EDVs are remapped to canonical ids in ``build_affiliation_index_dataframe``.
    """
    from database.paths import legacy_scrape_dir

    scrape_root = (root or legacy_scrape_dir()).resolve()
    # Do not apply DEFAULT_AKTIVE_MIN_SEASON — early seasons are required for
    # tournament club resolution (e.g. 05/06 rows keyed by remapped player_id).
    if min_season is None or str(min_season).strip() == "":
        season_floor = None
    else:
        season_floor = str(min_season).strip()
    selected = discover_local_aktive_workbooks(scrape_root, min_season=season_floor)
    stats = AktiveParseStats(seasons_selected=len(selected))
    rows: List[AktivePlayerRow] = []

    for season_slug, workbook in selected:
        try:
            parsed_rows = parse_aktive_workbook(workbook, season=season_slug)
        except Exception as exc:
            stats.workbooks_failed += 1
            stats.failures.append(f"{season_slug}: {workbook.name}: {exc}")
            continue
        stats.workbooks_parsed += 1
        stats.player_rows += len(parsed_rows)
        stats.seasons.append(
            {
                "season": season_slug,
                "workbook": str(workbook),
                "rows": str(len(parsed_rows)),
            }
        )
        rows.extend(parsed_rows)
    return rows, stats


def build_affiliation_index_dataframe(
    root: Optional[Path] = None,
    *,
    updated_at: Optional[str] = None,
    min_season: Optional[str] = None,
    crosswalk: Optional[Mapping[str, str]] = None,
) -> Tuple[pd.DataFrame, AffiliationBuildStats]:
    moment = updated_at or datetime.now(timezone.utc).isoformat()
    cross = crosswalk if crosswalk is not None else load_rangliste_club_crosswalk()
    raw_rows, _parse_stats = _collect_affiliation_rows(root, min_season=min_season)
    stats = AffiliationBuildStats(
        seasons_selected=_parse_stats.seasons_selected,
        workbooks_parsed=_parse_stats.workbooks_parsed,
        workbooks_failed=_parse_stats.workbooks_failed,
        affiliation_rows=len(raw_rows),
        failures=list(_parse_stats.failures),
    )

    out_rows: List[dict] = []
    seen_keys: set[Tuple[str, str]] = set()
    gap_clubs: set[str] = set()

    from data_access.aktive_mitglieder_registry import (
        build_pass_nr_edv_bridge,
        collect_aktive_rows_with_seasons,
        legacy_edv_to_canonical_remap,
    )
    from data_access.players_registry import build_legacy_player_id_remap

    legacy_remap = dict(build_legacy_player_id_remap())
    # Also derive from Aktive Pass-Nr when registry not yet rebuilt this run.
    bridge_rows, _ = collect_aktive_rows_with_seasons(root, min_season=None)
    for legacy, canonical in legacy_edv_to_canonical_remap(build_pass_nr_edv_bridge(bridge_rows)).items():
        legacy_remap.setdefault(legacy, canonical)

    for row in raw_rows:
        player_id = normalize_player_id(row.player_id)
        season = normalize_unicode_label(row.season) or folder_slug_to_app_season(row.season)
        if not player_id or not season:
            continue
        player_id = legacy_remap.get(player_id, player_id)
        key = (player_id, season)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        club_raw = normalize_unicode_label(row.club)
        verein_raw = normalize_unicode_label(row.verein)
        einzel = row.is_einzelmitglied
        club_canonical = ""
        crosswalk_hit = False
        if club_raw and not einzel:
            club_canonical, crosswalk_hit = resolve_rangliste_club_canonical(club_raw, cross)
            if not crosswalk_hit and club_canonical:
                gap_clubs.add(club_raw)

        out_rows.append(
            {
                "player_id": player_id,
                "season": season,
                "club_raw": club_raw,
                "verein_raw": verein_raw,
                "club_canonical": club_canonical,
                "verein_canonical": canonicalize_verein_label(verein_raw),
                "is_einzelmitglied": "true" if einzel else "false",
                "source": "rangliste",
                "updated_at": moment,
            }
        )

    stats.unique_player_seasons = len(seen_keys)
    stats.crosswalk_gaps = len(gap_clubs)
    if not out_rows:
        return pd.DataFrame(columns=list(AFFILIATION_COLUMNS)), stats
    return pd.DataFrame(out_rows, columns=list(AFFILIATION_COLUMNS)), stats


def _league_affiliation_input_mask(df: pd.DataFrame) -> pd.Series:
    from data_access.schema import Columns

    if df is None or df.empty:
        return pd.Series(dtype=bool)
    mask = pd.Series(True, index=df.index)
    if Columns.computed_data in df.columns:
        normalized = df[Columns.computed_data].fillna("").astype(str).str.strip().str.lower()
        mask &= normalized.isin({"false", "0", "no", ""})
    if Columns.event_type in df.columns:
        mask &= (
            df[Columns.event_type].fillna("").astype(str).str.strip().str.lower().ne("tournament")
        )
    return mask


def extend_affiliation_index_from_league(
    affiliation_df: pd.DataFrame,
    league_df: pd.DataFrame,
    *,
    updated_at: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Pass 2: add ``(player_id, season)`` rows from league merge when absent from pass 1.

    Never overwrites existing Rangliste rows. Verein columns stay empty for league-only rows.
    """
    from data_access.clubs_registry import apply_clubs_registry
    from data_access.competition_schema import club_name_from_team
    from data_access.schema import Columns

    moment = updated_at or datetime.now(timezone.utc).isoformat()
    stats = {"league_rows_added": 0, "league_rows_skipped_existing": 0}

    if league_df is None or league_df.empty:
        empty = (
            affiliation_df.copy()
            if affiliation_df is not None and not affiliation_df.empty
            else pd.DataFrame(columns=list(AFFILIATION_COLUMNS))
        )
        return empty, stats

    base = (
        affiliation_df.copy()
        if affiliation_df is not None and not affiliation_df.empty
        else pd.DataFrame(columns=list(AFFILIATION_COLUMNS))
    )
    existing_keys = {
        (normalize_player_id(row.player_id), normalize_unicode_label(row.season))
        for row in base.itertuples(index=False)
        if normalize_player_id(getattr(row, "player_id", ""))
        and normalize_unicode_label(getattr(row, "season", ""))
    }

    work = league_df.loc[_league_affiliation_input_mask(league_df)].copy()
    if work.empty:
        return base, stats
    if Columns.player_id not in work.columns or Columns.season not in work.columns:
        return base, stats

    if Columns.club not in work.columns:
        work[Columns.club] = ""
    if Columns.team_name in work.columns:
        missing = work[Columns.club].fillna("").astype(str).str.strip().eq("")
        work.loc[missing, Columns.club] = work.loc[missing, Columns.team_name].map(club_name_from_team)

    work, _club_stats = apply_clubs_registry(work)

    buckets: Dict[Tuple[str, str], str] = {}
    for _, row in work.iterrows():
        player_id = normalize_player_id(row.get(Columns.player_id))
        season = normalize_unicode_label(row.get(Columns.season))
        club = normalize_unicode_label(row.get(Columns.club))
        if not player_id or not season or not club or is_einzelmitglied_club(club):
            continue
        key = (player_id, season)
        if key in existing_keys or key in buckets:
            continue
        buckets[key] = club

    if not buckets:
        return base, stats

    new_rows: List[dict] = []
    for (player_id, season), club in sorted(buckets.items()):
        new_rows.append(
            {
                "player_id": player_id,
                "season": season,
                "club_raw": club,
                "verein_raw": "",
                "club_canonical": club,
                "verein_canonical": "",
                "is_einzelmitglied": "false",
                "source": "league",
                "updated_at": moment,
            }
        )
        stats["league_rows_added"] += 1

    extended = pd.concat([base, pd.DataFrame(new_rows, columns=list(AFFILIATION_COLUMNS))], ignore_index=True)
    return extended, stats


def build_vereine_registry_dataframe(
    affiliation_df: pd.DataFrame,
    *,
    updated_at: Optional[str] = None,
) -> pd.DataFrame:
    moment = updated_at or datetime.now(timezone.utc).isoformat()
    if affiliation_df is None or affiliation_df.empty:
        return pd.DataFrame(columns=list(VEREINE_REGISTRY_COLUMNS))

    buckets: Dict[str, Dict[str, Any]] = {}
    for row in affiliation_df.itertuples(index=False):
        verein_raw = normalize_unicode_label(getattr(row, "verein_raw", "") or "")
        verein_canon = normalize_unicode_label(getattr(row, "verein_canonical", "") or "") or verein_raw
        if not verein_canon:
            continue
        club_raw = normalize_unicode_label(getattr(row, "club_raw", "") or "")
        club_canon = normalize_unicode_label(getattr(row, "club_canonical", "") or "")
        einzel = str(getattr(row, "is_einzelmitglied", "") or "").strip().lower() == "true"
        bucket = buckets.setdefault(
            verein_canon,
            {"canonical_verein": verein_canon, "aliases": set(), "member_clubs": set()},
        )
        if verein_raw and verein_raw != verein_canon:
            bucket["aliases"].add(verein_raw)
        if club_raw and club_raw != verein_canon:
            bucket["aliases"].add(club_raw)
        if not einzel:
            member = club_canon or club_raw
            if member and not is_einzelmitglied_club(member):
                bucket["member_clubs"].add(member)

    rows: List[dict] = []
    for verein in sorted(buckets):
        item = buckets[verein]
        aliases = set(item["aliases"])
        aliases.discard(verein)
        rows.append(
            {
                "canonical_verein": verein,
                "aliases": _join_pipe(sorted(aliases)),
                "member_clubs": _join_pipe(sorted(item["member_clubs"])),
                "source": "rangliste",
                "updated_at": moment,
            }
        )
    return pd.DataFrame(rows, columns=list(VEREINE_REGISTRY_COLUMNS))


def compute_affiliation_fingerprint(df: Optional[pd.DataFrame]) -> str:
    if df is None or df.empty:
        return "empty"
    keys = "|".join(
        f"{row.player_id}:{row.season}"
        for row in df.itertuples(index=False)
    )
    return hashlib.sha256(keys.encode("utf-8")).hexdigest()[:12]


def write_affiliation_index(df: pd.DataFrame, *, write_csv: bool = False) -> Dict[str, str]:
    from data_access.parquet_sidecar import publish_dataframe

    out_path = _affiliation_index_path()
    published = publish_dataframe(df, out_path, write_csv=write_csv, sep=";")
    load_affiliation_index_df.cache_clear()
    return published


def write_vereine_registry(df: pd.DataFrame, *, write_csv: bool = False) -> Dict[str, str]:
    from data_access.parquet_sidecar import publish_dataframe

    out_path = _vereine_registry_path()
    published = publish_dataframe(df, out_path, write_csv=write_csv, sep=";")
    load_vereine_registry_df.cache_clear()
    return published


@lru_cache(maxsize=1)
def load_affiliation_index_df() -> Optional[pd.DataFrame]:
    path = _affiliation_index_path()
    from data_access.parquet_sidecar import data_file_exists, resolve_load_path

    if not data_file_exists(path):
        return None
    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


@lru_cache(maxsize=1)
def load_vereine_registry_df() -> Optional[pd.DataFrame]:
    path = _vereine_registry_path()
    from data_access.parquet_sidecar import data_file_exists, resolve_load_path

    if not data_file_exists(path):
        return None
    load_path = resolve_load_path(path)
    if load_path.suffix.lower() == ".parquet":
        return pd.read_parquet(load_path)
    return pd.read_csv(load_path, sep=";", dtype=str, keep_default_na=False)


def build_affiliation_lookup(
    affiliation_df: Optional[pd.DataFrame] = None,
) -> Dict[Tuple[str, str], Dict[str, str]]:
    df = affiliation_df if affiliation_df is not None else load_affiliation_index_df()
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    if df is None or df.empty:
        return out
    for row in df.itertuples(index=False):
        player_id = normalize_player_id(getattr(row, "player_id", ""))
        season = normalize_unicode_label(getattr(row, "season", ""))
        if not player_id or not season:
            continue
        out[(player_id, season)] = {
            "club_raw": normalize_unicode_label(getattr(row, "club_raw", "") or ""),
            "verein_raw": normalize_unicode_label(getattr(row, "verein_raw", "") or ""),
            "club_canonical": normalize_unicode_label(getattr(row, "club_canonical", "") or ""),
            "verein_canonical": normalize_unicode_label(getattr(row, "verein_canonical", "") or ""),
            "is_einzelmitglied": str(getattr(row, "is_einzelmitglied", "") or "").strip().lower() == "true",
            "source": normalize_unicode_label(getattr(row, "source", "") or ""),
        }
    return out


def build_verein_alias_lookup(
    vereine_df: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    df = vereine_df if vereine_df is not None else load_vereine_registry_df()
    out: Dict[str, str] = {}
    if df is None or df.empty:
        return out
    for row in df.itertuples(index=False):
        canonical = normalize_unicode_label(getattr(row, "canonical_verein", "") or "")
        if not canonical:
            continue
        keys = {canonical}
        keys.update(_split_pipe_list(getattr(row, "aliases", "")))
        for label in keys:
            key = verein_identity_key(label)
            if key and key not in out:
                out[key] = canonical
    return out


def season_sort_key(season: object) -> int:
    text = normalize_unicode_label(season).replace("-", "/")
    parts = text.split("/")
    if len(parts) != 2 or not parts[0].isdigit():
        return -1
    return int(parts[0])


def _affiliation_row_verein_key(aff: Mapping[str, Any]) -> str:
    label = normalize_unicode_label(aff.get("verein_canonical") or aff.get("verein_raw") or "")
    return verein_identity_key(label)


def _player_seasons_for_lookup(
    player_id: object,
    lookup: Mapping[Tuple[str, str], Mapping[str, str]],
) -> List[str]:
    pid = normalize_player_id(player_id)
    if not pid:
        return []
    seasons = sorted(
        {season for (pid_key, season) in lookup if pid_key == pid},
        key=season_sort_key,
    )
    return seasons


def lookup_tournament_affiliation(
    player_id: object,
    season: object,
    lookup: Mapping[Tuple[str, str], Mapping[str, str]],
    *,
    tournament_verein: object = "",
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Resolve tournament affiliation without blind season extrapolation.

    1. Same-season index hit (Rangliste or league pass 2).
    2. Only when missing: Verein-gated scan of past then future player seasons.
    """
    pid = normalize_player_id(player_id)
    season_text = normalize_unicode_label(season)
    if not pid or not season_text:
        return None, ""

    hit = lookup.get((pid, season_text))
    if hit:
        payload = dict(hit)
        source = normalize_unicode_label(payload.get("source") or "")
        if source == "league":
            return payload, "league_same_season"
        return payload, "index_same_season"

    verein_needle = verein_identity_key(tournament_verein)
    if not verein_needle:
        return None, ""

    target_key = season_sort_key(season_text)
    if target_key < 0:
        return None, ""

    past_seasons = [
        s
        for s in _player_seasons_for_lookup(pid, lookup)
        if season_sort_key(s) < target_key
    ]
    for candidate_season in reversed(past_seasons):
        candidate = lookup.get((pid, candidate_season))
        if not candidate:
            continue
        if _affiliation_row_verein_key(candidate) != verein_needle:
            continue
        payload = dict(candidate)
        payload["extrapolated_from_season"] = candidate_season
        return payload, "extrapolated_past"

    future_seasons = [
        s
        for s in _player_seasons_for_lookup(pid, lookup)
        if season_sort_key(s) > target_key
    ]
    for candidate_season in future_seasons:
        candidate = lookup.get((pid, candidate_season))
        if not candidate:
            continue
        if _affiliation_row_verein_key(candidate) != verein_needle:
            continue
        payload = dict(candidate)
        payload["extrapolated_from_season"] = candidate_season
        return payload, "extrapolated_future"

    return None, ""


def neighbor_seasons(season: str, *, radius: int = 1) -> List[str]:
    text = normalize_unicode_label(season).replace("-", "/")
    parts = text.split("/")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return []
    start_yy = int(parts[0])
    neighbors: List[str] = []
    for delta in range(-radius, radius + 1):
        if delta == 0:
            continue
        yy = start_yy + delta
        if yy < 0:
            continue
        neighbors.append(f"{yy:02d}/{(yy + 1) % 100:02d}")
    return neighbors


def lookup_player_affiliation(
    player_id: object,
    season: object,
    lookup: Mapping[Tuple[str, str], Mapping[str, str]],
    *,
    allow_neighbor: bool = True,
    neighbor_radius: int = 1,
) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Return ``(affiliation_dict, rule)`` where rule is ``same_season``,
    ``neighbor_season``, or ``""``.
    """
    pid = normalize_player_id(player_id)
    season_text = normalize_unicode_label(season)
    if not pid or not season_text:
        return None, ""

    hit = lookup.get((pid, season_text))
    if hit:
        return dict(hit), "same_season"

    if not allow_neighbor:
        return None, ""

    for neighbor in neighbor_seasons(season_text, radius=neighbor_radius):
        hit = lookup.get((pid, neighbor))
        if hit:
            payload = dict(hit)
            payload["neighbor_season"] = neighbor
            return payload, "neighbor_season"
    return None, ""


def publish_affiliation_bundle(
    affiliation_df: pd.DataFrame,
    *,
    write_csv: bool = False,
) -> Dict[str, Any]:
    """Write affiliation index and rebuild Verein registry from the combined index."""
    moment = datetime.now(timezone.utc).isoformat()
    vereine_df = build_vereine_registry_dataframe(affiliation_df, updated_at=moment)
    aff_pub = write_affiliation_index(affiliation_df, write_csv=write_csv)
    ver_pub = write_vereine_registry(vereine_df, write_csv=write_csv)
    return {
        "affiliation_rows": int(len(affiliation_df)),
        "vereine_rows": int(len(vereine_df)),
        "paths": {
            "affiliation_index": str(_affiliation_index_path().resolve()),
            "affiliation_parquet": str(aff_pub["parquet"]),
            "vereine_registry": str(_vereine_registry_path().resolve()),
            "vereine_parquet": str(ver_pub["parquet"]),
        },
        "fingerprint": compute_affiliation_fingerprint(affiliation_df),
    }


def build_and_publish_affiliation_registry(
    *,
    root: Optional[Path] = None,
    write_csv: bool = False,
    min_season: Optional[str] = None,
) -> Dict[str, Any]:
    moment = datetime.now(timezone.utc).isoformat()
    affiliation_df, stats = build_affiliation_index_dataframe(
        root,
        updated_at=moment,
        min_season=min_season,
    )
    vereine_df = build_vereine_registry_dataframe(affiliation_df, updated_at=moment)
    stats.unique_vereine = int(len(vereine_df))

    published = publish_affiliation_bundle(affiliation_df, write_csv=write_csv)

    return {
        "affiliation_rows": published["affiliation_rows"],
        "vereine_rows": published["vereine_rows"],
        "crosswalk_gaps": stats.crosswalk_gaps,
        "stats": {
            "seasons_selected": stats.seasons_selected,
            "workbooks_parsed": stats.workbooks_parsed,
            "workbooks_failed": stats.workbooks_failed,
            "unique_player_seasons": stats.unique_player_seasons,
            "league_rows_added": 0,
            "failures": stats.failures,
        },
        "paths": published["paths"],
        "fingerprint": published["fingerprint"],
    }


def extend_and_publish_affiliation_from_league(
    league_df: pd.DataFrame,
    *,
    write_csv: bool = False,
) -> Dict[str, Any]:
    """Pass 2: extend published affiliation index from league merge output."""
    existing = load_affiliation_index_df()
    base = existing if existing is not None else pd.DataFrame(columns=list(AFFILIATION_COLUMNS))
    moment = datetime.now(timezone.utc).isoformat()
    extended, league_stats = extend_affiliation_index_from_league(base, league_df, updated_at=moment)
    published = publish_affiliation_bundle(extended, write_csv=write_csv)
    rangliste_rows = int(len(base))
    return {
        **published,
        "rangliste_rows": rangliste_rows,
        "league_rows_added": int(league_stats.get("league_rows_added") or 0),
        "affiliation_rows": int(len(extended)),
    }


def format_affiliation_league_extend_summary(summary: Mapping[str, Any]) -> str:
    added = int(summary.get("league_rows_added") or 0)
    total = int(summary.get("affiliation_rows") or 0)
    rangliste = int(summary.get("rangliste_rows") or 0)
    return f"Affiliation index: {rangliste} Rangliste + {added} league row(s) -> {total} total"


def format_affiliation_build_summary(summary: Mapping[str, Any]) -> str:
    rows = int(summary.get("affiliation_rows") or 0)
    vereine = int(summary.get("vereine_rows") or 0)
    gaps = int(summary.get("crosswalk_gaps") or 0)
    parts = [
        f"Affiliation index: {rows} player-season row(s)",
        f"{vereine} Verein(s)",
    ]
    if gaps:
        parts.append(f"{gaps} unmapped Rangliste club label(s) — extend rangliste_club_crosswalk.csv")
    return ", ".join(parts)
