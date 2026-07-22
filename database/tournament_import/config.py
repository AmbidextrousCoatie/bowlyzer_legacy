"""Import job configuration (database/config/tournament_imports.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping

from database.paths import REPO_ROOT, get_data_dir, get_work_data_dir, tournament_staging_dir

DEFAULT_CONFIG_PATH = REPO_ROOT / "database" / "config" / "tournament_imports.json"

MERGE_TARGETS = frozenset({"manual", "gf_regional", "none"})


@dataclass(frozen=True)
class FormatSpec:
    id: str
    adapter: str
    description: str = ""


@dataclass(frozen=True)
class ImportEntry:
    id: str
    format: str
    source: str
    enabled: bool = True
    merge_target: str = "manual"
    output: str = ""
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TournamentImportConfig:
    schema_version: int
    formats: Dict[str, FormatSpec]
    imports: List[ImportEntry]


def _resolve_template(value: str) -> str:
    replacements = {
        "{repo_root}": str(REPO_ROOT),
        "{data_dir}": str(get_data_dir()),
        "{work_dir}": str(get_work_data_dir()),
        "{staging_dir}": str(tournament_staging_dir()),
        "{raw_dir}": str(get_work_data_dir() / "raw"),
    }
    out = value
    for key, repl in replacements.items():
        out = out.replace(key, repl)
    return out


def resolve_config_path(path: str | Path) -> Path:
    raw = Path(path)
    if raw.is_file():
        return raw.resolve()
    candidate = REPO_ROOT / raw
    if candidate.is_file():
        return candidate.resolve()
    return raw.resolve()


def resolve_source_path(source: str) -> Path:
    expanded = _resolve_template(source)
    path = Path(expanded)
    if path.is_file():
        return path.resolve()
    alt = get_work_data_dir() / source
    if alt.is_file():
        return alt.resolve()
    return path.resolve()


def resolve_output_path(entry: ImportEntry, event_names: List[str]) -> Path:
    if entry.output.strip():
        return Path(_resolve_template(entry.output)).resolve()
    slug = entry.id.replace("/", "-")
    return tournament_staging_dir() / f"tournament_import_{slug}_postprocessed.csv"


def load_config(path: str | Path | None = None) -> TournamentImportConfig:
    config_path = resolve_config_path(path or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise FileNotFoundError(f"Tournament import config not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    schema_version = int(raw.get("schema_version", 1))

    formats: Dict[str, FormatSpec] = {}
    for fmt_id, spec in (raw.get("formats") or {}).items():
        if not isinstance(spec, Mapping):
            continue
        formats[fmt_id] = FormatSpec(
            id=fmt_id,
            adapter=str(spec.get("adapter") or fmt_id),
            description=str(spec.get("description") or ""),
        )

    imports: List[ImportEntry] = []
    for item in raw.get("imports") or []:
        if not isinstance(item, Mapping):
            continue
        merge_target = str(item.get("merge_target") or "manual").strip().lower()
        if merge_target not in MERGE_TARGETS:
            raise ValueError(f"Invalid merge_target '{merge_target}' for import {item.get('id')}")
        imports.append(
            ImportEntry(
                id=str(item["id"]),
                format=str(item["format"]),
                source=str(item["source"]),
                enabled=bool(item.get("enabled", True)),
                merge_target=merge_target,
                output=str(item.get("output") or ""),
                options=dict(item.get("options") or {}),
            )
        )

    return TournamentImportConfig(schema_version=schema_version, formats=formats, imports=imports)


def get_format_spec(config: TournamentImportConfig, entry: ImportEntry) -> FormatSpec:
    spec = config.formats.get(entry.format)
    if spec is None:
        raise KeyError(f"Unknown format '{entry.format}' for import '{entry.id}'")
    return spec
