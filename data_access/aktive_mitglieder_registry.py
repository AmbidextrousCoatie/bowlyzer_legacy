"""Import *Aktive Mitglieder* season workbooks into the players registry."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from data_access.player_id_name_normalization import normalize_player_id, normalize_player_name
from data_access.player_name_normalization import normalize_player_label
from data_access.players_registry import REGISTRY_COLUMNS, _join_aliases
from data_access.text_norm import normalize_unicode_label
from data_access.tournament_coverage import folder_slug_to_app_season
from scripts.data.extract_excel_data import get_sheet_names_safely, read_excel_safely

MEMBER_SHEET_NAMES = ("member", "mitglieder", "aktive")
AKTIVE_WORKBOOK_RE = re.compile(r"aktive.*\.xls$", re.IGNORECASE)
SAISON_DIR_RE = re.compile(r"^saison(\d{4}-\d{2})$", re.IGNORECASE)
EDV_HEADER_RE = re.compile(r"^edv", re.IGNORECASE)
DBU_AKTIVE_SOURCE = "dbu_id"
# League/player stats start at 08/09; omit 2004–07 Aktive exports (phantom 6-digit EDVs).
DEFAULT_AKTIVE_MIN_SEASON = "2008-09"
# EDV numbers before this season are ``player_id_legacy`` (Pass-Nr bridges them).
# Folder ``2005-06`` ↔ app ``05/06``; renumber starts at ``06/07`` / ``2006-07``.
LEGACY_EDV_CUTOFF_SEASON = "2006-07"
LEGACY_EDV_CUTOFF_APP_SEASON = "06/07"


def resolve_aktive_min_season(value: Optional[str]) -> Optional[str]:
    """
    Season floor for Aktive import.

    ``None`` → :data:`DEFAULT_AKTIVE_MIN_SEASON`. Empty string → all seasons (no floor).
    """
    if value is None:
        return DEFAULT_AKTIVE_MIN_SEASON
    stripped = str(value).strip()
    if not stripped:
        return None
    return stripped


@dataclass
class AktiveParseStats:
    seasons_selected: int = 0
    workbooks_parsed: int = 0
    workbooks_failed: int = 0
    player_rows: int = 0
    unique_player_ids: int = 0
    failures: List[str] = field(default_factory=list)
    seasons: List[Dict[str, str]] = field(default_factory=list)


EINZELMITGLIED_LABEL = "einzelmitglied"


def is_einzelmitglied_club(label: object) -> bool:
    return normalize_unicode_label(label).casefold() == EINZELMITGLIED_LABEL


@dataclass(frozen=True)
class AktivePlayerRow:
    player_id: str
    canonical_name: str
    season: str
    club: str = ""
    verein: str = ""
    pass_nr: str = ""

    @property
    def is_einzelmitglied(self) -> bool:
        return is_einzelmitglied_club(self.club)


def normalize_pass_nr(value: object) -> str:
    """Normalize Pass-Nr for registry storage / bridge keys."""
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-"}:
        return ""
    # Numeric strings from Excel floats: ``9107553.0``
    try:
        as_float = float(text)
        if as_float.is_integer():
            return str(int(as_float))
    except ValueError:
        pass
    return re.sub(r"\s+", " ", text)


def _pass_nr_column_index(columns: Mapping[str, int]) -> Optional[int]:
    for key in ("pass-nr", "passnr", "pass"):
        if key in columns:
            return columns[key]
    return None


def is_legacy_edv_season(season: object) -> bool:
    """True when season is before the 06/07 EDV renumber (app ``YY/YY`` or folder ``YYYY-YY``)."""
    text = str(season or "").strip()
    if not text:
        return False
    if re.match(r"^\d{2}/\d{2}$", text):
        return text < LEGACY_EDV_CUTOFF_APP_SEASON
    folder = text.replace("/", "-")
    return folder < LEGACY_EDV_CUTOFF_SEASON


@dataclass(frozen=True)
class PassNrEdvBridge:
    """Pass-Nr → canonical EDV plus legacy EDVs observed before the 06/07 renumber."""

    pass_nr: str
    player_id: str
    player_id_legacy: Tuple[str, ...]
    canonical_name: str


def build_pass_nr_edv_bridge(
    rows: Sequence[Tuple[str, AktivePlayerRow]],
) -> Dict[str, PassNrEdvBridge]:
    """
    Build Pass-Nr bridges from ``(folder_or_app_season, row)`` observations.

    Canonical ``player_id`` is the latest non-legacy EDV for that Pass-Nr.
    """
    by_pass: Dict[str, Dict[str, Any]] = {}
    for season, row in rows:
        pass_nr = normalize_pass_nr(row.pass_nr)
        pid = normalize_player_id(row.player_id)
        if not pass_nr or not pid:
            continue
        bucket = by_pass.setdefault(
            pass_nr,
            {"legacy": {}, "modern": {}, "names": []},
        )
        name = normalize_player_name(row.canonical_name)
        if name:
            bucket["names"].append(name)
        target = bucket["legacy"] if is_legacy_edv_season(season) else bucket["modern"]
        seasons = target.setdefault(pid, [])
        seasons.append(str(season))

    bridges: Dict[str, PassNrEdvBridge] = {}
    for pass_nr, bucket in by_pass.items():
        modern: Dict[str, List[str]] = bucket["modern"]
        legacy: Dict[str, List[str]] = bucket["legacy"]
        if not modern:
            continue

        def _latest_key(pid: str, modern_map: Dict[str, List[str]] = modern) -> str:
            return max(str(s) for s in modern_map[pid])

        canonical_id = max(modern.keys(), key=_latest_key)
        legacy_ids = tuple(sorted(legacy.keys(), key=lambda x: (max(legacy[x]), x)))
        names = bucket["names"]
        canonical_name = names[-1] if names else ""
        bridges[pass_nr] = PassNrEdvBridge(
            pass_nr=pass_nr,
            player_id=canonical_id,
            player_id_legacy=legacy_ids,
            canonical_name=canonical_name,
        )
    return bridges


def legacy_edv_to_canonical_remap(
    bridges: Mapping[str, PassNrEdvBridge],
) -> Dict[str, str]:
    """Map every legacy EDV → canonical ``player_id``."""
    out: Dict[str, str] = {}
    for bridge in bridges.values():
        canonical = normalize_player_id(bridge.player_id)
        if not canonical:
            continue
        for legacy in bridge.player_id_legacy:
            lid = normalize_player_id(legacy)
            if lid and lid != canonical and lid not in out:
                out[lid] = canonical
    return out


def collect_aktive_rows_with_seasons(
    root: Optional[Path] = None,
    *,
    workbook_paths: Optional[Sequence[Tuple[str, Path]]] = None,
    min_season: Optional[str] = None,
) -> Tuple[List[Tuple[str, AktivePlayerRow]], AktiveParseStats]:
    """Return ``(folder_season, row)`` pairs from Aktive workbooks."""
    from database.paths import legacy_scrape_dir

    scrape_root = (root or legacy_scrape_dir()).resolve()
    if workbook_paths is None:
        selected = discover_local_aktive_workbooks(scrape_root, min_season=min_season)
    else:
        selected = list(workbook_paths)
        if min_season:
            selected = [(season, path) for season, path in selected if season >= min_season]
    stats = AktiveParseStats(seasons_selected=len(selected))
    out: List[Tuple[str, AktivePlayerRow]] = []
    for season, workbook in selected:
        try:
            parsed_rows = parse_aktive_workbook(workbook, season=season)
        except Exception as exc:
            stats.workbooks_failed += 1
            stats.failures.append(f"{season}: {workbook.name}: {exc}")
            continue
        stats.workbooks_parsed += 1
        stats.player_rows += len(parsed_rows)
        stats.seasons.append(
            {
                "season": season,
                "workbook": str(workbook),
                "rows": str(len(parsed_rows)),
            }
        )
        for row in parsed_rows:
            out.append((season, row))
    return out, stats


def _normalize_header_cell(value: object) -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("\n", " ")
    return re.sub(r"[.\s]+", "", raw)


def _column_index_map(header_cells: Sequence[object]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for idx, cell in enumerate(header_cells):
        key = _normalize_header_cell(cell)
        if key and key not in out:
            out[key] = idx
    return out


def _edv_column_index(columns: Mapping[str, int]) -> Optional[int]:
    for key, idx in columns.items():
        if EDV_HEADER_RE.match(key):
            return idx
    return None


def locate_member_header(df: pd.DataFrame) -> Tuple[Optional[int], str, Dict[str, int]]:
    """
    Return ``(header_row_index, layout, column_map)``.

  ``layout`` is ``split`` (Nachname/Vorname) or ``combined`` (single Name column).
    """
    limit = min(20, len(df))
    for row_idx in range(limit):
        cells = df.iloc[row_idx].tolist()
        columns = _column_index_map(cells)
        edv_idx = _edv_column_index(columns)
        if edv_idx is None:
            continue
        if "nachname" in columns and "vorname" in columns:
            return row_idx, "split", columns
        if "name" in columns:
            return row_idx, "combined", columns
    return None, "", {}


def _cell_str(row: Sequence[object], idx: Optional[int]) -> str:
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    value = row[idx]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def canonical_name_from_combined(raw_name: str) -> str:
    """Legacy single ``Name`` column uses ``Family Given`` token order."""
    label = normalize_player_label(raw_name)
    if not label:
        return ""
    if "," in label:
        return normalize_player_name(label)
    parts = label.split()
    if len(parts) == 1:
        return normalize_player_name(parts[0])
    family = parts[0]
    given = " ".join(parts[1:])
    return normalize_player_name(f"{family}, {given}")


def canonical_name_from_split(nachname: str, vorname: str, zusatz: str = "") -> str:
    family = normalize_player_label(nachname)
    given_parts = [normalize_player_label(vorname), normalize_player_label(zusatz)]
    given = " ".join(part for part in given_parts if part)
    if not family:
        return ""
    if given:
        return normalize_player_name(f"{family}, {given}")
    return normalize_player_name(family)


def row_to_aktive_player(
    row_values: Sequence[object],
    *,
    layout: str,
    columns: Mapping[str, int],
) -> Optional[AktivePlayerRow]:
    edv_idx = _edv_column_index(columns)
    if edv_idx is None:
        return None
    player_id = normalize_player_id(_cell_str(row_values, edv_idx))
    if not player_id:
        return None

    if layout == "split":
        name = canonical_name_from_split(
            _cell_str(row_values, columns.get("nachname")),
            _cell_str(row_values, columns.get("vorname")),
            _cell_str(row_values, columns.get("zusatz")),
        )
    elif layout == "combined":
        raw_name = _cell_str(row_values, columns.get("name"))
        name = canonical_name_from_combined(raw_name)
    else:
        return None

    if not name:
        return None

    club = normalize_unicode_label(_cell_str(row_values, columns.get("club")))
    verein = normalize_unicode_label(_cell_str(row_values, columns.get("verein")))
    pass_nr = normalize_pass_nr(_cell_str(row_values, _pass_nr_column_index(columns)))
    return AktivePlayerRow(
        player_id=player_id,
        canonical_name=name,
        season="",
        club=club,
        verein=verein,
        pass_nr=pass_nr,
    )


def _member_sheet_name(sheet_names: Sequence[str]) -> str:
    lowered = {name.lower(): name for name in sheet_names}
    for candidate in MEMBER_SHEET_NAMES:
        if candidate in lowered:
            return lowered[candidate]
    return sheet_names[0]


def parse_aktive_workbook(path: Path, *, season: str = "") -> List[AktivePlayerRow]:
    """Parse one *Aktive Mitglieder* workbook into player rows."""
    workbook_path = resolve_aktive_workbook_path(path)
    raw: Optional[pd.DataFrame] = None
    try:
        sheet_names = get_sheet_names_safely(workbook_path)
        if not sheet_names:
            raise ValueError(f"workbook has no sheets: {workbook_path.name}")
        sheet_name = _member_sheet_name(sheet_names)
        raw = read_excel_safely(workbook_path, sheet_name=sheet_name, header=None)
    except Exception as primary_exc:
        try:
            from data_access.xls_biff_salvage import read_truncated_xls_via_ole_biff

            raw = read_truncated_xls_via_ole_biff(workbook_path)
        except Exception as salvage_exc:
            raise ValueError(
                f"could not read Aktive workbook {workbook_path.name}: {primary_exc} "
                f"(salvage failed: {salvage_exc})"
            ) from primary_exc

    header_idx, layout, columns = locate_member_header(raw)
    if header_idx is None or not layout:
        raise ValueError(f"could not locate EDV header row in {workbook_path.name}")

    rows: List[AktivePlayerRow] = []
    for row_idx in range(header_idx + 1, len(raw)):
        values = raw.iloc[row_idx].tolist()
        parsed = row_to_aktive_player(values, layout=layout, columns=columns)
        if parsed is None:
            continue
        rows.append(
            AktivePlayerRow(
                player_id=parsed.player_id,
                canonical_name=parsed.canonical_name,
                season=folder_slug_to_app_season(season) if season else "",
                club=parsed.club,
                verein=parsed.verein,
                pass_nr=parsed.pass_nr,
            )
        )
    return rows


def resolve_aktive_workbook_path(path: Path) -> Path:
    """Return a readable ``.xls`` path (extract from ``.zip`` when needed)."""
    if path.suffix.lower() == ".zip":
        xls_path = path.with_suffix(".xls")
        if xls_path.is_file():
            return xls_path
        data = path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".xls")]
            if not members:
                raise ValueError(f"zip has no .xls member: {path.name}")
            xls_path.parent.mkdir(parents=True, exist_ok=True)
            xls_path.write_bytes(archive.read(members[0]))
        return xls_path
    return path


def _season_from_path(root: Path, path: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    if rel.parts and SAISON_DIR_RE.match(rel.parts[0]):
        return rel.parts[0].replace("saison", "", 1)
    return ""


def discover_local_aktive_workbooks(
    root: Path,
    *,
    min_season: Optional[str] = None,
) -> List[Tuple[str, Path]]:
    """
    Find one primary *Aktive Mitglieder* workbook per season under ``root``.

    Prefers filenames containing ``Endstand``; otherwise picks the first match.

    When ``min_season`` is set (e.g. ``"2007-08"``), seasons before that label are
    omitted. Season labels use the ``YYYY-YY`` form from ``saisonYYYY-YY`` folders.
    """
    by_season: Dict[str, List[Path]] = {}
    if not root.is_dir():
        return []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name.endswith(".zip") and AKTIVE_WORKBOOK_RE.search(lower_name.replace(".zip", ".xls")):
            season = _season_from_path(root, path)
            if season:
                by_season.setdefault(season, []).append(path)
            continue
        if not AKTIVE_WORKBOOK_RE.search(path.name):
            continue
        season = _season_from_path(root, path)
        if not season:
            continue
        by_season.setdefault(season, []).append(path)

    selected: List[Tuple[str, Path]] = []
    for season in sorted(by_season):
        paths = sorted(by_season[season], key=lambda item: str(item).lower())
        preferred = [path for path in paths if "endstand" in path.name.lower()]
        pick = preferred[0] if preferred else paths[0]
        selected.append((season, pick))
    if min_season:
        selected = [(season, path) for season, path in selected if season >= min_season]
    return selected


def build_registry_dataframe_from_aktive(
    root: Optional[Path] = None,
    *,
    updated_at: str,
    workbook_paths: Optional[Sequence[Tuple[str, Path]]] = None,
    min_season: Optional[str] = None,
) -> Tuple[pd.DataFrame, AktiveParseStats]:
    """
    Build registry rows from scraped *Aktive Mitglieder* workbooks.

    Pass-Nr bridges pre-06/07 EDVs onto the canonical modern ``player_id``.
    Registry rows are keyed only by canonical ``player_id`` (never by legacy EDV).

    ``min_season`` controls which seasons contribute names / modern IDs; Pass-Nr
    bridging always scans all available Aktive seasons (including 2004–07).
    """
    # Full history for Pass-Nr → EDV bridge (includes legacy seasons).
    all_rows, bridge_stats = collect_aktive_rows_with_seasons(
        root,
        workbook_paths=workbook_paths,
        min_season=None,
    )
    bridges = build_pass_nr_edv_bridge(all_rows)
    legacy_remap = legacy_edv_to_canonical_remap(bridges)
    pass_by_canonical: Dict[str, PassNrEdvBridge] = {}
    for bridge in bridges.values():
        existing = pass_by_canonical.get(bridge.player_id)
        if existing is None:
            pass_by_canonical[bridge.player_id] = bridge
        else:
            # Merge legacy IDs if multiple Pass-Nr somehow share a modern EDV.
            merged_legacy = tuple(
                sorted(set(existing.player_id_legacy) | set(bridge.player_id_legacy))
            )
            pass_by_canonical[bridge.player_id] = PassNrEdvBridge(
                pass_nr=existing.pass_nr or bridge.pass_nr,
                player_id=bridge.player_id,
                player_id_legacy=merged_legacy,
                canonical_name=bridge.canonical_name or existing.canonical_name,
            )

    season_floor = resolve_aktive_min_season(min_season)
    if workbook_paths is None:
        primary_rows = [
            (season, row)
            for season, row in all_rows
            if season_floor is None or season >= season_floor
        ]
        stats = AktiveParseStats(
            seasons_selected=len({s for s, _ in primary_rows}),
            workbooks_parsed=bridge_stats.workbooks_parsed,
            workbooks_failed=bridge_stats.workbooks_failed,
            player_rows=sum(1 for _ in primary_rows),
            failures=list(bridge_stats.failures),
            seasons=[
                s
                for s in bridge_stats.seasons
                if season_floor is None or str(s.get("season") or "") >= season_floor
            ],
        )
    else:
        primary_rows, stats = collect_aktive_rows_with_seasons(
            root,
            workbook_paths=workbook_paths,
            min_season=season_floor,
        )

    entries: Dict[str, Dict[str, object]] = {}
    for season, row in primary_rows:
        raw_pid = normalize_player_id(row.player_id)
        if not raw_pid:
            continue
        # Never create registry rows under legacy EDVs.
        if is_legacy_edv_season(season):
            continue
        pid = legacy_remap.get(raw_pid, raw_pid)
        name = normalize_player_name(row.canonical_name)
        bridge = pass_by_canonical.get(pid)
        pass_nr = normalize_pass_nr(row.pass_nr) or (bridge.pass_nr if bridge else "")
        legacy_ids = list(bridge.player_id_legacy) if bridge else []
        slot = entries.get(pid)
        if slot is None:
            entries[pid] = {
                "player_id": pid,
                "player_id_legacy": set(legacy_ids),
                "player_id_pass": pass_nr,
                "canonical_name": name,
                "source": DBU_AKTIVE_SOURCE,
                "updated_at": updated_at,
                "aliases": set(),
            }
            continue

        aliases = set(slot.get("aliases") or set())
        old_name = normalize_player_label(str(slot.get("canonical_name") or ""))
        if old_name and old_name != normalize_player_label(name):
            aliases.add(old_name)
        slot["canonical_name"] = name
        slot["source"] = DBU_AKTIVE_SOURCE
        slot["updated_at"] = updated_at
        slot["aliases"] = aliases
        if pass_nr and not slot.get("player_id_pass"):
            slot["player_id_pass"] = pass_nr
        legacy_set = set(slot.get("player_id_legacy") or set())
        legacy_set.update(legacy_ids)
        slot["player_id_legacy"] = legacy_set
        entries[pid] = slot

    # Ensure bridge attributes land even when modern ID only appears via Pass-Nr.
    for pid, bridge in pass_by_canonical.items():
        slot = entries.get(pid)
        if slot is None:
            continue
        if bridge.pass_nr and not slot.get("player_id_pass"):
            slot["player_id_pass"] = bridge.pass_nr
        legacy_set = set(slot.get("player_id_legacy") or set())
        legacy_set.update(bridge.player_id_legacy)
        slot["player_id_legacy"] = legacy_set

    stats.unique_player_ids = len(entries)
    if not entries:
        return pd.DataFrame(columns=list(REGISTRY_COLUMNS)), stats

    rows: List[Dict[str, str]] = []
    for pid in sorted(entries):
        slot = entries[pid]
        aliases = _join_aliases(set(slot.get("aliases") or set()))
        legacy_joined = _join_aliases(set(slot.get("player_id_legacy") or set()))
        rows.append(
            {
                "player_id": pid,
                "player_id_legacy": legacy_joined,
                "player_id_pass": str(slot.get("player_id_pass") or ""),
                "canonical_name": str(slot["canonical_name"]),
                "source": str(slot["source"]),
                "updated_at": str(slot["updated_at"]),
                "aliases": aliases,
            }
        )
    return pd.DataFrame(rows, columns=list(REGISTRY_COLUMNS)), stats


def format_aktive_import_summary(stats: AktiveParseStats) -> str:
    if stats.seasons_selected <= 0:
        return "Aktive Mitglieder: no workbooks found under legacy_scrape"
    lines = [
        (
            f"Aktive Mitglieder: {stats.workbooks_parsed}/{stats.seasons_selected} season workbook(s) "
            f"-> {stats.unique_player_ids} player id(s) from {stats.player_rows} row(s)"
        )
    ]
    if stats.workbooks_failed:
        lines.append(
            f"  {stats.workbooks_failed} workbook(s) skipped (unreadable; non-fatal — "
            "add manual registry rows if needed)"
        )
        for failure in stats.failures[:5]:
            lines.append(f"    - {failure}")
        if len(stats.failures) > 5:
            lines.append(f"    … and {len(stats.failures) - 5} more")
    return "\n".join(lines)
