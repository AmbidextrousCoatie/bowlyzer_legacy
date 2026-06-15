"""Import *Aktive Mitglieder* season workbooks into the players registry."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from data_access.player_id_name_normalization import normalize_player_id, normalize_player_name
from data_access.player_name_normalization import normalize_player_label
from data_access.players_registry import REGISTRY_COLUMNS, _join_aliases
from extract_excel_data import get_sheet_names_safely, read_excel_safely

MEMBER_SHEET_NAMES = ("member", "mitglieder", "aktive")
AKTIVE_WORKBOOK_RE = re.compile(r"aktive.*\.xls$", re.IGNORECASE)
SAISON_DIR_RE = re.compile(r"^saison(\d{4}-\d{2})$", re.IGNORECASE)
EDV_HEADER_RE = re.compile(r"^edv", re.IGNORECASE)
DBU_AKTIVE_SOURCE = "dbu_id"
# League/player stats start at 08/09; omit 2004–07 Aktive exports (phantom 6-digit EDVs).
DEFAULT_AKTIVE_MIN_SEASON = "2008-09"


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


@dataclass(frozen=True)
class AktivePlayerRow:
    player_id: str
    canonical_name: str
    season: str


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
    return AktivePlayerRow(player_id=player_id, canonical_name=name, season="")


def _member_sheet_name(sheet_names: Sequence[str]) -> str:
    lowered = {name.lower(): name for name in sheet_names}
    for candidate in MEMBER_SHEET_NAMES:
        if candidate in lowered:
            return lowered[candidate]
    return sheet_names[0]


def parse_aktive_workbook(path: Path, *, season: str = "") -> List[AktivePlayerRow]:
    """Parse one *Aktive Mitglieder* workbook into player rows."""
    workbook_path = resolve_aktive_workbook_path(path)
    sheet_names = get_sheet_names_safely(workbook_path)
    if not sheet_names:
        raise ValueError(f"workbook has no sheets: {workbook_path.name}")
    sheet_name = _member_sheet_name(sheet_names)
    raw = read_excel_safely(workbook_path, sheet_name=sheet_name, header=None)
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
                season=season,
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

    Seasons are applied oldest-first; later seasons refresh canonical names and
    accumulate prior spellings as aliases.

    ``min_season`` drops older *Aktive* seasons (see ``discover_local_aktive_workbooks``).
    """
    from database.paths import legacy_scrape_dir

    scrape_root = (root or legacy_scrape_dir()).resolve()
    if workbook_paths is None:
        selected = discover_local_aktive_workbooks(scrape_root, min_season=min_season)
    else:
        selected = list(workbook_paths)
        if min_season:
            selected = [(season, path) for season, path in selected if season >= min_season]
    stats = AktiveParseStats(seasons_selected=len(selected))

    entries: Dict[str, Dict[str, object]] = {}
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
            pid = row.player_id
            name = normalize_player_name(row.canonical_name)
            slot = entries.get(pid)
            if slot is None:
                entries[pid] = {
                    "player_id": pid,
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
            entries[pid] = slot

    stats.unique_player_ids = len(entries)
    if not entries:
        return pd.DataFrame(columns=list(REGISTRY_COLUMNS)), stats

    rows: List[Dict[str, str]] = []
    for pid in sorted(entries):
        slot = entries[pid]
        aliases = _join_aliases(set(slot.get("aliases") or set()))
        rows.append(
            {
                "player_id": pid,
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
