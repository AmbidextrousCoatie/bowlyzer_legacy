#!/usr/bin/env python3
"""
Script to extract data from BYL_Maenner-5-6.xlsx and map it to the existing CSV format.
Based on correct understanding: 9 teams, 30 rows each, 4 positions, up to 3 players per position.
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, UTC
import re
import argparse
import hashlib
import json
from pathlib import Path
import warnings
import shutil
import subprocess
import io
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Dict
from contextlib import contextmanager, redirect_stdout


dict_of_match_numbers = {}

_LEAGUE_MAPPING_PATH = Path(__file__).resolve().parent / "database" / "relational_csv" / "league_mapping.csv"
_LEAGUE_MAPPING_CACHE = None
_ANALYSIS_LOG_PATH = Path(__file__).resolve().parent / "database" / "data" / "extract_excel_analysis_log.json"
_OVERRIDES_PATH = Path(__file__).resolve().parent / "database" / "config" / "extract_excel_overrides.csv"
_TEAM_NAME_NORMALIZATION_PATH = Path(__file__).resolve().parent / "database" / "config" / "team_name_normalization.json"
_TEAM_NUMBER_OVERRIDES_PATH = Path(__file__).resolve().parent / "database" / "config" / "team_number_overrides.csv"
_TEAM_NAME_NORMALIZATION_CACHE = None
_TEAM_NAME_PREFIX_NORMALIZATION_CACHE = None
_TEAM_NAME_PREFIX_OPTIONS_CACHE = None
_TEAM_NAME_SUFFIX_NORMALIZATION_CACHE = None
_TEAM_NORMALIZATION_STATS = None
_LEAGUE_GENDER_SCOPE_CACHE = None

# Bump these when analysis/extraction logic changes in a way that should invalidate prior cache entries.
ANALYZER_VERSION = "analyzer-v1.2.7"
EXTRACTOR_VERSION = "extractor-v1.2.6"
PROCESSOR_VERSION = "processor-v1.2.7"


def compute_file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA256 hash for a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def load_analysis_log(log_path: Path = _ANALYSIS_LOG_PATH):
    """Load persistent analysis log JSON; return default structure on missing/corrupt file."""
    if not log_path.is_file():
        return {"schema_version": 1, "files": {}}
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"schema_version": 1, "files": {}}
        files = payload.get("files")
        if not isinstance(files, dict):
            payload["files"] = {}
        return payload
    except Exception:
        return {"schema_version": 1, "files": {}}


def save_analysis_log(payload, log_path: Path = _ANALYSIS_LOG_PATH):
    """Persist analysis log JSON."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload["analyzer_version"] = ANALYZER_VERSION
    payload["extractor_version"] = EXTRACTOR_VERSION
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_bool(value) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def load_extract_overrides(path: Path = _OVERRIDES_PATH) -> pd.DataFrame:
    """Load optional extraction overrides manifest."""
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
        for required_col in ["match_type", "match_value"]:
            if required_col not in df.columns:
                raise ValueError(f"Missing required override column: {required_col}")
        return df
    except Exception as exc:
        print(f"Warning: could not load overrides from {path}: {exc}")
        return pd.DataFrame()


def compute_overrides_manifest_fingerprint(overrides_df: pd.DataFrame) -> str:
    """Compute deterministic fingerprint for the full overrides manifest."""
    if overrides_df is None or overrides_df.empty:
        return ""
    normalized = overrides_df.fillna("").astype(str).copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    records = normalized.to_dict(orient="records")
    records = sorted(records, key=lambda rec: json.dumps(rec, ensure_ascii=False, sort_keys=True))
    payload = json.dumps(records, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _override_row_dict(row) -> dict:
    return {str(k): str(v) for k, v in row.to_dict().items()}


def _fingerprint_override_rows(override_rows: list) -> str:
    if not override_rows:
        return ""
    payload = json.dumps(override_rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_all_matching_overrides(
    overrides_df: pd.DataFrame,
    file_path: Path,
    file_hash: str,
    analysis_result: dict = None,
):
    """
    Return all matching override rows in apply order.
    Path rules: file_hash -> exact_path -> path_regex.
    Post-analyze rules: data_format_pre_2022 (requires analysis_result).
    """
    if overrides_df is None or overrides_df.empty:
        return []

    file_str = str(file_path.resolve())
    matches = []
    seen = set()

    def _append_row(row):
        row_dict = _override_row_dict(row)
        key = json.dumps(row_dict, ensure_ascii=False, sort_keys=True)
        if key in seen:
            return
        seen.add(key)
        matches.append(row_dict)

    def _iter_path_matches(match_type: str):
        subset = overrides_df[overrides_df["match_type"].astype(str).str.strip().str.lower() == match_type]
        for _, row in subset.iterrows():
            match_value = str(row.get("match_value", "")).strip()
            if not match_value:
                continue
            if match_type == "file_hash" and file_hash == match_value:
                yield row
            elif match_type == "exact_path" and file_str == str(Path(match_value).resolve()):
                yield row
            elif match_type == "path_regex":
                try:
                    if re.search(match_value, file_str):
                        yield row
                except re.error:
                    continue

    for match_type in ["file_hash", "exact_path", "path_regex"]:
        for row in _iter_path_matches(match_type):
            _append_row(row)

    if analysis_result:
        data_format = str(analysis_result.get("data_format") or "").strip()
        subset = overrides_df[
            overrides_df["match_type"].astype(str).str.strip().str.lower() == "data_format_pre_2022"
        ]
        for _, row in subset.iterrows():
            match_value = str(row.get("match_value", "")).strip()
            if not match_value or match_value == data_format:
                _append_row(row)

    return matches


def find_matching_override(overrides_df: pd.DataFrame, file_path: Path, file_hash: str):
    """Return first matching override row dict and fingerprint (legacy helper)."""
    rows = find_all_matching_overrides(overrides_df, file_path, file_hash)
    if not rows:
        return None, ""
    return rows[0], _fingerprint_override_rows(rows)


def apply_override_to_analysis_result(result: dict, override_row: dict, file_path: Path = None):
    """Mutate analysis result by override rule; attach audit metadata."""
    if not override_row:
        return result

    reason = (override_row.get("reason") or "").strip()
    exclude_file = _parse_bool(override_row.get("exclude_file"))
    force_season = (override_row.get("force_season") or "").strip()
    force_league = (override_row.get("force_league") or "").strip()
    force_available_weeks = (override_row.get("force_available_weeks") or "").strip()
    force_season_from_path_if_week = (override_row.get("force_season_from_path_if_week") or "").strip()

    if force_season:
        result["season"] = force_season
        result["season_source"] = "override_manifest"
    if force_league:
        result["league"] = force_league
        result["league_source"] = "override_manifest"
    if force_available_weeks:
        result["available_weeks"] = force_available_weeks
        result["weeks_source"] = "override_manifest"

    if force_season_from_path_if_week and file_path is not None:
        trigger_weeks = set()
        for token in force_season_from_path_if_week.split(","):
            token = token.strip()
            if token.isdigit():
                trigger_weeks.add(int(token))
        file_weeks = set(parse_available_weeks(result.get("available_weeks")))
        if trigger_weeks & file_weeks:
            path_season = infer_season_from_path(file_path)
            if path_season and path_season.get("season_short"):
                path_short = path_season["season_short"]
                content_short = str(result.get("season") or "").strip()
                if path_short and path_short != content_short:
                    result["season"] = path_short
                    result["season_source"] = "override_manifest:season_from_path_if_week"

    if exclude_file:
        result["eligible_for_processing"] = False
        issue_text = str(result.get("issues") or "").strip()
        exclude_msg = "Excluded by override manifest"
        result["issues"] = f"{issue_text} | {exclude_msg}".strip(" | ")

    result["override_applied"] = True
    applied_reasons = [
        part.strip()
        for part in str(result.get("override_reason") or "").split("|")
        if part.strip()
    ]
    if reason and reason not in applied_reasons:
        applied_reasons.append(reason)
    result["override_reason"] = " | ".join(applied_reasons)
    result["override_match_type"] = (override_row.get("match_type") or "").strip()
    result["override_match_value"] = (override_row.get("match_value") or "").strip()
    return result


def apply_all_overrides_to_analysis_result(result: dict, override_rows: list, file_path: Path):
    """Apply every matching override row; set combined audit fields."""
    if not override_rows:
        result["override_applied"] = False
        result["override_reason"] = ""
        return result
    for override_row in override_rows:
        result = apply_override_to_analysis_result(result, override_row, file_path)
    return result


def _analyze_with_cache(
    excel_file: Path,
    analysis_log,
    old_format_sheet_threshold=15,
    force_reanalyze=False,
    overrides_df=None,
):
    """Analyze file with persistent cache short-circuiting."""
    file_path = Path(excel_file).resolve()
    file_key = str(file_path)
    file_hash = compute_file_sha256(file_path)
    overrides_manifest_fingerprint = compute_overrides_manifest_fingerprint(overrides_df)
    files_map = analysis_log.setdefault("files", {})
    cached = files_map.get(file_key, {})
    cached_result = cached.get("analysis_result")
    cached_file_hash = str(cached.get("file_hash") or (cached_result or {}).get("file_hash") or "")
    cached_analyzer_version = str(
        cached.get("analyzer_version") or (cached_result or {}).get("analyzer_version") or ""
    )
    cached_override_fingerprint = str(cached.get("override_fingerprint") or "")
    if not cached_override_fingerprint:
        cached_override_fingerprint = str((cached_result or {}).get("override_fingerprint") or "")
    cached_manifest_fingerprint = str(cached.get("overrides_manifest_fingerprint") or "")
    cached_threshold_raw = cached.get("old_format_sheet_threshold")
    try:
        cached_threshold = int(cached_threshold_raw) if cached_threshold_raw is not None else None
    except (TypeError, ValueError):
        cached_threshold = None

    probe_result = cached_result if isinstance(cached_result, dict) else {}
    override_rows_probe = find_all_matching_overrides(
        overrides_df, file_path, file_hash, analysis_result=probe_result
    )
    override_fingerprint_probe = _fingerprint_override_rows(override_rows_probe)

    criteria = {
        "has_cached_result": isinstance(cached_result, dict),
        "file_hash_match": cached_file_hash == file_hash,
        "analyzer_version_match": cached_analyzer_version == ANALYZER_VERSION,
        "threshold_match": cached_threshold == old_format_sheet_threshold,
        "override_fingerprint_match": cached_override_fingerprint == override_fingerprint_probe,
        "overrides_manifest_match": cached_manifest_fingerprint == overrides_manifest_fingerprint,
    }
    can_reuse = all(criteria.values())

    if can_reuse and not force_reanalyze:
        result = dict(cached_result)
        result["from_cache"] = True
        result["analysis_skip_reason"] = (
            "Skipped due to unchanged file hash + analyzer version + threshold + override fingerprint"
        )
        result["analysis_reexecute_reason"] = ""
    else:
        failed_criteria = [name for name, ok in criteria.items() if not ok]
        if force_reanalyze:
            reexecute_reason = "forced via --force_reanalyze"
        elif failed_criteria:
            reexecute_reason = "cache miss: " + ", ".join(failed_criteria)
        else:
            reexecute_reason = "cache miss: unknown"
        print(f"  analyzing: {file_path}", flush=True)
        print(f"    reason: {reexecute_reason}", flush=True)
        result = analyze_excel_file(file_path, old_format_sheet_threshold=old_format_sheet_threshold)
        result["from_cache"] = False
        result["analysis_skip_reason"] = ""
        result["analysis_reexecute_reason"] = reexecute_reason
        if str(result.get("issues", "")).startswith("Workbook could not be analyzed:"):
            print(f"  analyze failed: {file_path}", flush=True)
            print(f"    {result['issues']}", flush=True)
    override_rows = find_all_matching_overrides(overrides_df, file_path, file_hash, analysis_result=result)
    result = apply_all_overrides_to_analysis_result(result, override_rows, file_path)
    override_fingerprint = _fingerprint_override_rows(override_rows)

    result["file"] = str(file_path)
    result["file_hash"] = file_hash
    result["override_fingerprint"] = override_fingerprint
    result["analyzer_version"] = ANALYZER_VERSION
    result["extractor_version"] = EXTRACTOR_VERSION

    files_map[file_key] = {
        "file_hash": file_hash,
        "analyzer_version": ANALYZER_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "old_format_sheet_threshold": old_format_sheet_threshold,
        "override_fingerprint": override_fingerprint,
        "overrides_manifest_fingerprint": overrides_manifest_fingerprint,
        "last_analyzed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "analysis_result": result,
    }
    return result


def _build_processing_input_signature(
    eligible_df: pd.DataFrame,
    overrides_manifest_fingerprint: str = "",
) -> str:
    """Build deterministic signature for current process-mode eligible inputs."""
    if eligible_df.empty:
        return ""
    records = []
    for row in eligible_df.itertuples(index=False):
        records.append(
            {
                "file": str(getattr(row, "file", "")),
                "file_hash": str(getattr(row, "file_hash", "")),
                "available_weeks": str(getattr(row, "available_weeks", "")),
                "league": str(getattr(row, "league", "")),
                "season": str(getattr(row, "season", "")),
                "games_per_week": str(getattr(row, "games_per_week", "")),
            }
        )
    records = sorted(records, key=lambda rec: rec["file"])
    payload = json.dumps(
        {
            "analyzer_version": ANALYZER_VERSION,
            "processor_version": PROCESSOR_VERSION,
            "overrides_manifest_fingerprint": overrides_manifest_fingerprint,
            "eligible_inputs": records,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_combo_processing_signature(
    combo_df: pd.DataFrame,
    season_value: str,
    league_value: str,
) -> str:
    """Build deterministic signature for one season+league processing output."""
    payload = json.dumps(
        {
            "season": str(season_value),
            "league": str(league_value),
            "processor_version": PROCESSOR_VERSION,
            "analyzer_version": ANALYZER_VERSION,
            "input_signature": _build_processing_input_signature(combo_df),
            # Per-file override fingerprints keep cache invalidation local to affected files.
            "override_fingerprints": sorted(
                {
                    str(getattr(row, "override_fingerprint", "") or "")
                    for row in combo_df.itertuples(index=False)
                }
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_female_league_id(league_id: str) -> bool:
    lid = league_id.strip()
    return lid.endswith("(D)") or lid.endswith("(d)")


def _load_league_mapping():
    """Load league pools and display aliases from relational league_mapping.csv."""
    global _LEAGUE_MAPPING_CACHE
    if _LEAGUE_MAPPING_CACHE is not None:
        return _LEAGUE_MAPPING_CACHE
    rows = []
    alias_to_id = {}
    if not _LEAGUE_MAPPING_PATH.is_file():
        _LEAGUE_MAPPING_CACHE = ([], [], set(), alias_to_id, [])
        return _LEAGUE_MAPPING_CACHE

    mapping_df = pd.read_csv(_LEAGUE_MAPPING_PATH, encoding="utf-8")
    if "aliases" not in mapping_df.columns:
        mapping_df["aliases"] = ""
    seen_ids = set()
    for rec in mapping_df.itertuples(index=False):
        lid = normalize_optional_text(getattr(rec, "id", None))
        lng = normalize_optional_text(getattr(rec, "long_name", None))
        if lid and lng:
            rows.append((lid, lng))
            seen_ids.add(lid.lower())
        alias_field = normalize_optional_text(getattr(rec, "aliases", None)) or ""
        for alias in alias_field.split("|"):
            alias_key = _squish_league_text(alias)
            if alias_key and lid:
                alias_to_id[alias_key] = lid
    male = [(lid, lng) for lid, lng in rows if not _is_female_league_id(lid)]
    female = [(lid, lng) for lid, lng in rows if _is_female_league_id(lid)]
    entries = _build_league_mapping_entries(mapping_df)
    _LEAGUE_MAPPING_CACHE = (male, female, seen_ids, alias_to_id, entries)
    return _LEAGUE_MAPPING_CACHE


def _build_league_mapping_entries(mapping_df: pd.DataFrame) -> list[dict]:
    """Rows from league_mapping.csv with all labels used for long_name matching."""
    if "aliases" not in mapping_df.columns:
        mapping_df = mapping_df.copy()
        mapping_df["aliases"] = ""
    entries: list[dict] = []
    for rec in mapping_df.itertuples(index=False):
        league_id = normalize_optional_text(getattr(rec, "id", None))
        long_name = normalize_optional_text(getattr(rec, "long_name", None))
        if not league_id or not long_name:
            continue
        gender_scope = "female" if _is_female_league_id(league_id) else "male"
        labels = [long_name]
        alias_field = normalize_optional_text(getattr(rec, "aliases", None)) or ""
        for alias in alias_field.split("|"):
            alias = normalize_optional_text(alias)
            if alias and alias not in labels:
                labels.append(alias)
        entries.append(
            {
                "id": league_id,
                "long_name": long_name,
                "gender_scope": gender_scope,
                "labels": labels,
            }
        )
    return entries


def _squish_league_text(value: str) -> str:
    """Lowercase, collapse whitespace."""
    text = normalize_optional_text(value)
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_team_key(value: str) -> str:
    text = normalize_optional_text(value)
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"\.+$", "", text)  # trailing punctuation variants, e.g. "Unterf."
    text = re.sub(r"\s+", " ", text)
    return text


def _load_team_name_regex_map() -> Dict[str, str]:
    global _TEAM_NAME_NORMALIZATION_CACHE
    if _TEAM_NAME_NORMALIZATION_CACHE is not None:
        return _TEAM_NAME_NORMALIZATION_CACHE

    if not _TEAM_NAME_NORMALIZATION_PATH.is_file():
        _TEAM_NAME_NORMALIZATION_CACHE = {}
        return _TEAM_NAME_NORMALIZATION_CACHE

    try:
        payload = json.loads(_TEAM_NAME_NORMALIZATION_PATH.read_text(encoding="utf-8"))
        mapping_raw = payload.get("team_name_regex_map", {}) if isinstance(payload, dict) else {}
        normalized = {}
        for source, target in mapping_raw.items():
            src_key = normalize_optional_text(source)
            tgt_val = normalize_optional_text(target)
            if src_key and tgt_val:
                normalized[src_key] = tgt_val
        _TEAM_NAME_NORMALIZATION_CACHE = normalized
    except Exception as exc:
        print(f"Warning: failed to load team name regex map: {exc}")
        _TEAM_NAME_NORMALIZATION_CACHE = {}

    return _TEAM_NAME_NORMALIZATION_CACHE


def _load_team_name_prefix_normalization_map() -> Dict[str, str]:
    global _TEAM_NAME_PREFIX_NORMALIZATION_CACHE
    if _TEAM_NAME_PREFIX_NORMALIZATION_CACHE is not None:
        return _TEAM_NAME_PREFIX_NORMALIZATION_CACHE

    if not _TEAM_NAME_NORMALIZATION_PATH.is_file():
        _TEAM_NAME_PREFIX_NORMALIZATION_CACHE = {}
        return _TEAM_NAME_PREFIX_NORMALIZATION_CACHE

    try:
        payload = json.loads(_TEAM_NAME_NORMALIZATION_PATH.read_text(encoding="utf-8"))
        prefix_raw = payload.get("team_name_prefix_map", {}) if isinstance(payload, dict) else {}
        normalized = {}
        for source, target in prefix_raw.items():
            src_val = normalize_optional_text(source)
            tgt_val = normalize_optional_text(target)
            if src_val and tgt_val:
                normalized[src_val] = tgt_val
        _TEAM_NAME_PREFIX_NORMALIZATION_CACHE = normalized
    except Exception as exc:
        print(f"Warning: failed to load team name prefix normalization map: {exc}")
        _TEAM_NAME_PREFIX_NORMALIZATION_CACHE = {}

    return _TEAM_NAME_PREFIX_NORMALIZATION_CACHE


def _load_team_name_prefix_options_map() -> Dict[str, Dict[str, object]]:
    global _TEAM_NAME_PREFIX_OPTIONS_CACHE
    if _TEAM_NAME_PREFIX_OPTIONS_CACHE is not None:
        return _TEAM_NAME_PREFIX_OPTIONS_CACHE

    if not _TEAM_NAME_NORMALIZATION_PATH.is_file():
        _TEAM_NAME_PREFIX_OPTIONS_CACHE = {}
        return _TEAM_NAME_PREFIX_OPTIONS_CACHE

    try:
        payload = json.loads(_TEAM_NAME_NORMALIZATION_PATH.read_text(encoding="utf-8"))
        options_raw = payload.get("team_name_prefix_options", {}) if isinstance(payload, dict) else {}
        normalized = {}
        for source, options in options_raw.items():
            src_val = normalize_optional_text(source)
            if not src_val:
                continue
            normalized[src_val] = options if isinstance(options, dict) else {}
        _TEAM_NAME_PREFIX_OPTIONS_CACHE = normalized
    except Exception as exc:
        print(f"Warning: failed to load team name prefix options map: {exc}")
        _TEAM_NAME_PREFIX_OPTIONS_CACHE = {}

    return _TEAM_NAME_PREFIX_OPTIONS_CACHE


def _load_team_name_suffix_normalization_map() -> Dict[str, str]:
    global _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE
    if _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE is not None:
        return _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE

    if not _TEAM_NAME_NORMALIZATION_PATH.is_file():
        _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE = {}
        return _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE

    try:
        payload = json.loads(_TEAM_NAME_NORMALIZATION_PATH.read_text(encoding="utf-8"))
        suffix_raw = payload.get("team_name_suffix_map", {}) if isinstance(payload, dict) else {}
        normalized = {}
        for source, target in suffix_raw.items():
            src_val = normalize_optional_text(source)
            tgt_val = normalize_optional_text(target)
            if src_val and tgt_val:
                normalized[src_val] = tgt_val
        _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE = normalized
    except Exception as exc:
        print(f"Warning: failed to load team name suffix normalization map: {exc}")
        _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE = {}

    return _TEAM_NAME_SUFFIX_NORMALIZATION_CACHE


def reset_team_normalization_stats():
    global _TEAM_NORMALIZATION_STATS
    _TEAM_NORMALIZATION_STATS = {
        "regex_total": 0,
        "regex_by_source": {},
    }


def _bump_team_normalization_stat(kind: str, source_key: str):
    global _TEAM_NORMALIZATION_STATS
    if _TEAM_NORMALIZATION_STATS is None:
        reset_team_normalization_stats()
    if kind == "regex":
        total_key, map_key = "regex_total", "regex_by_source"
    else:
        return
    _TEAM_NORMALIZATION_STATS[total_key] += 1
    _TEAM_NORMALIZATION_STATS[map_key][source_key] = _TEAM_NORMALIZATION_STATS[map_key].get(source_key, 0) + 1


def print_team_normalization_summary():
    stats = _TEAM_NORMALIZATION_STATS or {}
    regex_total = int(stats.get("regex_total", 0))
    total = regex_total
    print("\nTeam Name Normalization Summary:")
    print(f"  replacements total: {total}")
    print(f"  regex replacements: {regex_total}")
    if regex_total:
        print("  regex replacement hits:")
        for source, count in sorted((stats.get("regex_by_source") or {}).items(), key=lambda item: (-item[1], item[0])):
            print(f"    - {source}: {count}")


def normalize_team_name(value):
    text = normalize_optional_text(value)
    if not text:
        return value
    regex_map = _load_team_name_regex_map()
    for pattern, replacement in regex_map.items():
        try:
            updated = re.sub(pattern, replacement, text, count=1)
        except re.error:
            continue
        if updated != text:
            updated = re.sub(r"\s+", " ", updated).strip()
            _bump_team_normalization_stat("regex", pattern)
            return updated

    return text


def normalize_extracted_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Separate normalization stage:
    extracted rows -> normalized rows.
    """
    if df is None or df.empty:
        return df
    normalized = df.copy()
    if "Bonus Points" not in normalized.columns:
        normalized["Bonus Points"] = "0"
    else:
        normalized["Bonus Points"] = normalized["Bonus Points"].fillna("0")
    for col in ["Team", "Opponent"]:
        if col in normalized.columns:
            normalized[col] = normalized[col].apply(normalize_team_name)
    if "League" in normalized.columns:
        normalized["League"] = normalized["League"].apply(
            lambda value: normalize_league_display_to_canonical(value)
            or normalize_optional_text(value)
            or value
        )
    return normalized


def _split_team_base_and_number(value: str):
    text = normalize_optional_text(value)
    if not text:
        return "", ""
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", text)
    if not match:
        return text, ""
    return str(match.group(1) or "").strip(), str(match.group(2) or "").strip()


def load_team_number_overrides(path: Path = _TEAM_NUMBER_OVERRIDES_PATH) -> pd.DataFrame:
    """Load optional team-number override manifest."""
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
        required = ["club", "season", "from_team_number", "to_team_number"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required team number override column: {col}")
        if "league" not in df.columns:
            df["league"] = ""
        if "reason" not in df.columns:
            df["reason"] = ""
        return df
    except Exception as exc:
        print(f"Warning: could not load team number overrides from {path}: {exc}")
        return pd.DataFrame()


def load_league_gender_scope_map(path: Path = _LEAGUE_MAPPING_PATH) -> Dict[str, str]:
    """Load league -> gender_scope map from relational league mapping."""
    global _LEAGUE_GENDER_SCOPE_CACHE
    if _LEAGUE_GENDER_SCOPE_CACHE is not None:
        return _LEAGUE_GENDER_SCOPE_CACHE

    if not path.is_file():
        _LEAGUE_GENDER_SCOPE_CACHE = {}
        return _LEAGUE_GENDER_SCOPE_CACHE

    try:
        mapping_df = pd.read_csv(path, dtype=str).fillna("")
        out = {}
        for row in mapping_df.itertuples(index=False):
            league_id = normalize_optional_text(getattr(row, "id", ""))
            gender_scope = str(getattr(row, "gender_scope", "") or "").strip().lower()
            if league_id and gender_scope:
                out[league_id] = gender_scope
        _LEAGUE_GENDER_SCOPE_CACHE = out
    except Exception as exc:
        print(f"Warning: could not load league gender scope map: {exc}")
        _LEAGUE_GENDER_SCOPE_CACHE = {}

    return _LEAGUE_GENDER_SCOPE_CACHE


def normalize_team_numbering_dataframe(df: pd.DataFrame, overrides_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Post-normalization stage:
    - default unnumbered teams to team 1.
    - apply explicit overrides (e.g. base -> team 2 for exceptional seasons).
    """
    if df is None or df.empty:
        return df
    required_cols = {"Season", "League"}
    if not required_cols.issubset(set(df.columns)):
        return df

    normalized = df.copy()
    applicable_cols = [col for col in ["Team", "Opponent"] if col in normalized.columns]
    if not applicable_cols:
        return normalized

    overrides_df = overrides_df if isinstance(overrides_df, pd.DataFrame) else pd.DataFrame()
    override_map = {}
    if not overrides_df.empty:
        for row in overrides_df.itertuples(index=False):
            club = normalize_optional_text(getattr(row, "club", ""))
            season = normalize_optional_text(getattr(row, "season", ""))
            from_num = normalize_optional_text(getattr(row, "from_team_number", ""))
            to_num = normalize_optional_text(getattr(row, "to_team_number", ""))
            league = normalize_optional_text(getattr(row, "league", ""))
            if not club or not season or to_num is None:
                continue
            from_norm = from_num or ""
            override_map[(club, season, league or "", from_norm)] = str(to_num)

    def _normalize_team_cell(row, col_name: str):
        team_raw = normalize_optional_text(row.get(col_name))
        if not team_raw:
            return row.get(col_name)
        season = normalize_optional_text(row.get("Season"))
        league = normalize_optional_text(row.get("League"))
        if not season or not league:
            return team_raw

        base, num = _split_team_base_and_number(team_raw)
        if not base:
            return team_raw

        current_num = num or ""
        override_target = (
            override_map.get((base, season, league, current_num))
            or override_map.get((base, season, "", current_num))
        )
        if override_target is not None:
            target_num = str(override_target).strip()
            return f"{base} {target_num}".strip() if target_num else base

        if current_num:
            return team_raw

        return f"{base} 1"

    for col in applicable_cols:
        normalized[col] = normalized.apply(lambda row: _normalize_team_cell(row, col), axis=1)

    return normalized


def export_unique_team_names_after_merge(
    merged_df: pd.DataFrame,
    output_path: Path = Path("database/data/unique_team_names_after_merge.csv"),
):
    """Export unique normalized team names from merged output."""
    if merged_df is None or merged_df.empty:
        print("Unique team names export skipped: merged dataframe is empty.")
        return

    candidate_columns = [col for col in ["Team", "Opponent"] if col in merged_df.columns]
    if not candidate_columns:
        print("Unique team names export skipped: Team/Opponent columns missing.")
        return

    names = set()
    for col in candidate_columns:
        for value in merged_df[col].dropna().astype(str):
            text = re.sub(r"\s+", " ", value).strip()
            if text:
                names.add(text)

    sorted_names = sorted(names, key=lambda item: item.lower())
    export_df = pd.DataFrame({"team_name": sorted_names})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_df.to_csv(output_path, sep=";", index=False, encoding="utf-8")
    print(f"Unique team names exported: {output_path} ({len(sorted_names)} names)")


def compute_team_name_normalization_fingerprint() -> str:
    """Fingerprint team name normalization config for cache invalidation."""
    if not _TEAM_NAME_NORMALIZATION_PATH.is_file():
        return ""
    try:
        payload = json.loads(_TEAM_NAME_NORMALIZATION_PATH.read_text(encoding="utf-8"))
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return ""


# Gender tokens in sheet titles — flexible on dashes / whitespace (pre-2022 Ligabericht).
_LEAGUE_GENDER_FEMALE_RE = re.compile(
    r"(?:^|[\s\-–—/]+)(?:frauen|damen)(?:[\s\-–—/]+|$)",
    re.IGNORECASE,
)
_LEAGUE_GENDER_MALE_RE = re.compile(
    r"(?:^|[\s\-–—/]+)(?:herren|männer|maenner)(?:[\s\-–—/]+|$)",
    re.IGNORECASE,
)


def _normalize_league_match_text(value: str) -> str:
    """Lowercase title/label with dashes and whitespace collapsed for substring match."""
    text = normalize_optional_text(value)
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[\s\-–—_/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _derive_league_gender_scope(raw: str) -> str:
    """Damen/Frauen → female; Herren/Männer or no gender marker → male."""
    text = normalize_optional_text(raw)
    if not text:
        return "male"
    if _LEAGUE_GENDER_FEMALE_RE.search(text):
        return "female"
    return "male"


def _long_name_matches_title(long_name_norm: str, title_norm: str) -> bool:
    if not long_name_norm or not title_norm:
        return False
    if title_norm == long_name_norm:
        return True
    padded = f" {title_norm} "
    return f" {long_name_norm} " in padded


def _strip_trailing_league_gender_suffix(raw: str) -> str:
    """Drop trailing gender label from pre-2022 titles (unmapped fallback display only)."""
    text = normalize_optional_text(raw)
    if not text:
        return ""
    stripped = re.sub(
        r"[\s\-–—/]+(?:frauen|damen|männer|maenner|herren)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" -–—/")
    return stripped or text


def _fallback_league_display(display_name: str, gender_scope: str) -> str:
    base = _strip_trailing_league_gender_suffix(display_name) or display_name
    if gender_scope == "female" and not _is_female_league_id(base):
        if not re.search(r"\(D\)\s*$", base, flags=re.IGNORECASE):
            return f"{base} (D)"
    return base


def expand_league_region_shorthand(league_display: str) -> str:
    """
    Sheets often shorten ``… N1 …`` to ``Nord 1``. CSV long_names spell out Nord/Süd.

    Examples: ``Bezirksliga N1`` → ``Bezirksliga Nord 1``,
    ``Bezirksoberliga S2`` → ``Bezirksoberliga Süd 2``.
    """
    text = normalize_optional_text(league_display)
    if not text:
        return league_display or ""

    def repl(match):
        level = match.group(1)
        compass = match.group(2).upper()
        num = match.group(3)
        region_name = "Nord" if compass == "N" else "Süd"
        return f"{level} {region_name} {num}"

    pattern = re.compile(
        r"(?i)\b(Landesliga|Bezirksliga|Bezirksoberliga|Kreisliga)\s+([NS])(\d+)\b"
    )
    return pattern.sub(repl, text)


def _match_league_id_by_long_name(title: str, entries: list[dict], gender_scope: str) -> str | None:
    """Longest long_name (or alias) contained in title, within the derived gender pool."""
    title_norm = _normalize_league_match_text(title)
    if not title_norm:
        return None

    best_id = None
    best_len = -1
    for entry in entries:
        if entry.get("gender_scope") != gender_scope:
            continue
        for label in entry.get("labels") or []:
            label_norm = _normalize_league_match_text(label)
            if not _long_name_matches_title(label_norm, title_norm):
                continue
            if len(label_norm) > best_len:
                best_len = len(label_norm)
                best_id = entry["id"]
    return best_id


def normalize_league_display_to_canonical(raw_league_display):
    """
    Map Ligabericht/Spielzettel league titles to canonical ids.

    1. Match longest ``long_name`` (or alias) from league_mapping.csv in the title.
    2. Derive gender from title wording: Damen/Frauen → female pool; otherwise male.
    """
    text = normalize_optional_text(raw_league_display)
    if not text:
        return None

    cleaned = clean_league_name(text)
    if not cleaned:
        return None

    cleaned = expand_league_region_shorthand(cleaned)
    gender_scope = _derive_league_gender_scope(cleaned)

    cache = _load_league_mapping()
    entries = cache[4] if len(cache) > 4 else []
    if not entries:
        return _fallback_league_display(cleaned, gender_scope)

    known_ids = cache[2]
    clean_lower = cleaned.strip().lower()
    if clean_lower in known_ids:
        for entry in entries:
            if entry["id"].lower() == clean_lower:
                return entry["id"]
        return cleaned

    league_id = _match_league_id_by_long_name(cleaned, entries, gender_scope)
    if league_id:
        return league_id

    return _fallback_league_display(cleaned, gender_scope)


# Analyze-mode read bounds (avoid full-sheet loads when metadata / row counts suffice).
_ANALYZE_WEEK_SHEET_NROWS = 20
_ANALYZE_WEEK_SHEET_USECOLS = "A:G"
_ANALYZE_TAGesschnitt_NROWS = 25
_ANALYZE_LIGABERICHT_NROWS = 12
# Do not set usecols on Ligabericht: regional sheets are often A:Q only; A:T breaks pandas read.
_ANALYZE_TABELLE_NROWS = 5
_ANALYZE_SPIELORTE_NROWS = 25
_ANALYZE_SCHLUESSEL_NROWS = 2
_ANALYZE_SCHLUESSEL_USECOLS = "A:C"


def _excel_engine_candidates(excel_path: Path):
    """Return ordered pandas Excel engine names to try for a file suffix."""
    suffix = excel_path.suffix.lower()
    return {
        ".xls": [None, "xlrd", "calamine"],
        ".xlsx": [None, "openpyxl", "calamine"],
        ".xlsm": [None, "openpyxl", "calamine"],
        ".xlsb": [None, "pyxlsb", "calamine"],
    }.get(suffix, [None, "openpyxl", "calamine", "xlrd"])


@contextmanager
def _excel_read_warning_filters():
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Print area cannot be set to Defined name: .*",
            category=UserWarning,
            module=r"openpyxl\.reader\.workbook",
        )
        yield


@contextmanager
def open_workbook_session(excel_file):
    """
    Open one pandas ExcelFile for a path and reuse it across sheet reads.

    Yields pd.ExcelFile; closes on exit. Use in analyze (and similar) to avoid
    re-parsing the same workbook for every sheet.
    """
    excel_path = Path(excel_file)
    errors = []
    workbook = None
    for engine in _excel_engine_candidates(excel_path):
        try:
            with _excel_read_warning_filters():
                kwargs = {}
                if engine is not None:
                    kwargs["engine"] = engine
                workbook = pd.ExcelFile(excel_path, **kwargs)
                break
        except Exception as exc:
            engine_label = engine or "default"
            errors.append(f"{engine_label}: {exc}")

    if workbook is None:
        detail = " | ".join(errors)
        if excel_path.suffix.lower() == ".xls":
            raise RuntimeError(
                "Legacy .xls workbook could not be opened with available engines. "
                "Install/use an .xls-capable engine (xlrd or calamine). "
                f"Details: {detail}"
            )
        raise RuntimeError(f"Workbook could not be opened. Details: {detail}")

    try:
        yield workbook
    finally:
        workbook.close()


def read_excel_safely(
    excel_file,
    sheet_name,
    header=None,
    *,
    workbook=None,
    nrows=None,
    usecols=None,
):
    """Read worksheet with format-aware engine fallbacks and clean warnings."""
    read_kwargs = {"sheet_name": sheet_name, "header": header}
    if nrows is not None:
        read_kwargs["nrows"] = nrows
    if usecols is not None:
        read_kwargs["usecols"] = usecols

    if workbook is not None:
        with _excel_read_warning_filters():
            return pd.read_excel(workbook, **read_kwargs)

    excel_path = Path(excel_file)
    suffix = excel_path.suffix.lower()
    errors = []
    for engine in _excel_engine_candidates(excel_path):
        try:
            with _excel_read_warning_filters():
                kwargs = dict(read_kwargs)
                if engine is not None:
                    kwargs["engine"] = engine
                return pd.read_excel(excel_path, **kwargs)
        except Exception as exc:
            engine_label = engine or "default"
            errors.append(f"{engine_label}: {exc}")

    detail = " | ".join(errors)
    if suffix == ".xls":
        raise RuntimeError(
            "Legacy .xls workbook could not be read with available engines. "
            "Install/use an .xls-capable engine (xlrd or calamine). "
            f"Details: {detail}"
        )
    raise RuntimeError(f"Workbook could not be read. Details: {detail}")


def get_sheet_names_safely(excel_file, workbook=None):
    """Get worksheet names with format-aware engine fallbacks."""
    if workbook is not None:
        return list(workbook.sheet_names)

    excel_path = Path(excel_file)
    errors = []
    for engine in _excel_engine_candidates(excel_path):
        try:
            with _excel_read_warning_filters():
                kwargs = {}
                if engine is not None:
                    kwargs["engine"] = engine
                with pd.ExcelFile(excel_path, **kwargs) as opened:
                    return list(opened.sheet_names)
        except Exception as exc:
            engine_label = engine or "default"
            errors.append(f"{engine_label}: {exc}")
    raise RuntimeError(f"Could not read workbook sheet names. Details: {' | '.join(errors)}")


def get_match_number(round_idx, team_name, team_name_opponent):
    """Get the match number for a given round, team name, and opponent."""
    
    my_team_tuple = frozenset([team_name, team_name_opponent])

    if round_idx not in dict_of_match_numbers:
        dict_of_match_numbers[round_idx] = {my_team_tuple: 0}

    elif my_team_tuple not in dict_of_match_numbers[round_idx]:
        max_match_number = max(dict_of_match_numbers[round_idx].values())
        dict_of_match_numbers[round_idx][my_team_tuple] = max_match_number + 1

    return dict_of_match_numbers[round_idx][my_team_tuple]


def extract_season_info(excel_file, sheet_name):
    """Extract season information from specified sheet."""
    try:
        # Read the specified sheet
        df = read_excel_safely(excel_file, sheet_name=sheet_name, header=None)
        
        # Look for season information in the first row
        first_row = df.iloc[0]
        for col, value in first_row.items():
            if pd.notna(value) and isinstance(value, str):
                # Look for pattern like "Saison 2025/2026"
                season_match = re.search(r'Saison\s+(\d{4})/(\d{4})', str(value))
                if season_match:
                    year1 = season_match.group(1)
                    year2 = season_match.group(2)
                    # Convert YYYY/YYYY to YY/YY format
                    season_short = f"{year1[-2:]}/{year2[-2:]}"
                    return {
                        'season_short': season_short,
                        'year1': year1,
                        'year2': year2
                    }
        
        print("Warning: Could not find season information in Schiedsrichterinfos sheet")
        return {'season_short': '??/??', 'year1': '????', 'year2': '????'}  # Default fallback
        
    except Exception as e:
        print(f"Error reading Schiedsrichterinfos sheet: {e}")
        return {'season_short': '??/??', 'year1': '????', 'year2': '????'}  # Default fallback


def extract_date_info(df):
    """Extract date information from first row of team sheet."""
    try:
        # Look in the first row for date pattern like "04.10. / 05.10." or "12.11."
        first_row = df.iloc[0]
        for col, value in first_row.items():
            if pd.notna(value) and isinstance(value, str):
                # Look for DD.MM. pattern (with optional slash and more)
                date_match = re.search(r'(\d{2})\.(\d{2})\.', str(value))
                if date_match:
                    day = date_match.group(1)
                    month = date_match.group(2)
                    return {
                        'day': day,
                        'month': month
                    }
        
        print("Warning: Could not find date information in first row")
        return {'day': '04', 'month': '10'}  # Default fallback
        
    except Exception as e:
        print(f"Error extracting date info: {e}")
        return {'day': 'n/a', 'month': 'n/a'}  # Default fallback


def infer_season_from_path(excel_file):
    """
    Parse segments like ``Liga 2023-24`` → ``season_short`` ``23/24`` with full calendar years.

    Expects ``YYYY-YY`` (second part is last two digits of end year); requires ``year2 == year1 + 1``.
    """
    path_ref = Path(excel_file).resolve()
    path_blob = str(path_ref).replace(" ", "")
    pattern = re.compile(r"\b(19\d{2}|20\d{2})-(\d{2})\b")

    def candidate_from_match(match):
        y1_full = int(match.group(1))
        yy_end = int(match.group(2))
        century_base = (y1_full // 100) * 100
        y2_full = century_base + yy_end
        if y2_full <= y1_full:
            y2_full += 100
        if y2_full != y1_full + 1:
            return None
        y1_str, y2_str = str(y1_full), str(y2_full)
        return {
            "season_short": f"{y1_str[-2:]}/{y2_str[-2:]}",
            "year1": y1_str,
            "year2": y2_str,
        }

    segments = []
    current = path_ref
    while current != current.parent:
        segments.append(current.name)
        current = current.parent

    for seg in segments:
        match = pattern.search(seg)
        if match:
            info = candidate_from_match(match)
            if info:
                return info
        # Folder names like ``Bayernliga2019-20`` (no space before year).
        glued_pattern = re.compile(r"(19\d{2}|20\d{2})-(\d{2})")
        match = glued_pattern.search(seg.replace(" ", ""))
        if match:
            info = candidate_from_match(match)
            if info:
                return info

    for match in re.finditer(r"(19\d{2}|20\d{2})-(\d{2})", path_blob):
        info = candidate_from_match(match)
        if info:
            return info

    return None


def normalize_season_cell_to_short(season_text):
    """Map ``YYYY/YYYY`` from Spielorte to ``YY/YY`` when consecutive years."""
    text = normalize_optional_text(season_text)
    if not text:
        return None
    match = re.match(r"^(\d{4})\s*/\s*(\d{4})$", text)
    if not match:
        return text
    y1_full, y2_full = match.group(1), match.group(2)
    if int(y2_full) != int(y1_full) + 1:
        return text
    return f"{y1_full[-2:]}/{y2_full[-2:]}"


def season_label_to_season_info(season_text):
    """Build ``season_info`` fragment from ``YY/YY`` or ``YYYY/YYYY`` labels."""
    text = normalize_optional_text(season_text)
    if not text:
        return None
    match = re.match(r"^(\d{4})\s*/\s*(\d{4})$", text)
    if match:
        y1s, y2s = match.group(1), match.group(2)
        if int(y2s) != int(y1s) + 1:
            return None
        return {
            "season_short": f"{y1s[-2:]}/{y2s[-2:]}",
            "year1": y1s,
            "year2": y2s,
        }
    match = re.match(r"^(\d{2})\s*/\s*(\d{2})$", text)
    if not match:
        return None
    y1s, y2s = match.group(1), match.group(2)
    if int(y2s) != int(y1s) + 1:
        return None
    y1_full = 2000 + int(y1s)
    y2_full = 2000 + int(y2s)
    return {
        "season_short": f"{y1s}/{y2s}",
        "year1": str(y1_full),
        "year2": str(y2_full),
    }


def _season_from_content_is_uncertain(season_text):
    """Returns True when season from spreadsheet metadata should be supplemented by path fallback."""
    if season_text is None:
        return True
    s = normalize_optional_text(season_text)
    if not s:
        return True
    lowered = s.lower()
    if "?" in lowered:
        return True
    if "unknown" in lowered:
        return True
    return False


def _old_format_year_from_season_month(month: int, season_info: dict) -> int:
    """Sports season folder rule: month > 8 → first year, month <= 8 → second year."""
    if int(month) > 8:
        return int(season_info["year1"])
    return int(season_info["year2"])


def _excel_date_year_is_placeholder(year: int) -> bool:
    """Excel often stores 1899/1900 when the sheet cell has no calendar year."""
    return int(year) < 1980


def complete_old_format_date_info(date_info: dict | None, season_info: dict | None) -> dict | None:
    """Fill missing/placeholder year from ``saisonYYYY-YY`` (or other path) season_info."""
    if not date_info or not season_info:
        return date_info
    month = int(date_info.get("month") or 0)
    if month < 1 or month > 12:
        return date_info
    year_full = date_info.get("year_full")
    if year_full is None or _excel_date_year_is_placeholder(int(year_full)):
        year_full = _old_format_year_from_season_month(month, season_info)
        date_info = dict(date_info)
        date_info["year_full"] = int(year_full)
        day = int(date_info["day"])
        date_info["raw"] = f"{day:02d}.{month:02d}.{year_full}"
    return date_info


def old_format_date_is_usable(date_info: dict | None, season_info: dict | None) -> bool:
    completed = complete_old_format_date_info(date_info, season_info)
    if not completed:
        return False
    try:
        day = int(completed["day"])
        month = int(completed["month"])
        year = int(completed["year_full"])
    except (KeyError, TypeError, ValueError):
        return False
    return 1 <= day <= 31 and 1 <= month <= 12 and year >= 1980


def combine_season_and_date(season_info, date_info):
    """Combine season and date information to create full date."""
    try:
        day = date_info["day"]
        month = int(date_info["month"])
        year = _old_format_year_from_season_month(month, season_info)
        return f"{year}-{month:02d}-{int(day):02d}"
    except Exception as e:
        print(f"Error combining season and date: {e}")
        return "could not extract date"  # Default fallback


def detect_team_anchor_start_col(raw_df, default_start_col=25):
    """Detect team block anchor column by locating 'Team-Nr.' in sheet."""
    anchor_cols = []
    for _, row in raw_df.iterrows():
        for col_idx, value in row.items():
            if pd.notna(value) and "Team-Nr." in str(value):
                anchor_cols.append(col_idx)
    if anchor_cols:
        detected = int(min(anchor_cols))
        print(f"Detected team anchor column from 'Team-Nr.': {detected}")
        return detected
    print(f"Could not detect 'Team-Nr.' anchor column, using fallback: {default_start_col}")
    return default_start_col


def extract_excel_data(excel_file='2025_BYL_M-1.xlsx', team_sheet='Erfassung1', season_sheet='Schiedsrichterinfos'):
    """Extract data from Excel file and map to CSV format."""
    
    print(f"Reading Excel file - {team_sheet} sheet...")
    try:
        # Read the specific sheet without header
        df = read_excel_safely(excel_file, sheet_name=team_sheet, header=None)
        print(f"Excel file shape: {df.shape}")
        
        # Slice from detected team anchor column onwards.
        start_col_idx = detect_team_anchor_start_col(df, default_start_col=25)
        end_col_idx = min(start_col_idx + 24, len(df.columns))
        df = df.iloc[:, start_col_idx:end_col_idx]
        print(f"After slicing from col {start_col_idx} - shape: {df.shape}")
        
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return None
    
    # Extract season information from specified sheet
    season_info = extract_season_info(excel_file, season_sheet)
    print(f"Extracted season info: {season_info}")
    
    # Extract date information from first row of team sheet
    date_info = extract_date_info(df)
    print(f"Extracted date info: {date_info}")
    
    # Combine season and date to get full date
    full_date = combine_season_and_date(season_info, date_info)
    print(f"Combined full date: {full_date}")
    
    return df, season_info, full_date


def parse_teams(
    excel_df,
    season_info,
    full_date,
    league_override=None,
    week_override=None,
    max_games_per_week=None,
):
    """Parse all teams in the Excel file."""
    
    csv_data = []
    season = season_info['season_short']
    league = league_override if league_override else "BayL"
    players_per_team = 4
    date = full_date
    
    # Find team sections (rows containing "Team-Nr.")
    team_start_rows = []
    for idx, row in excel_df.iterrows():
        for col, value in row.items():
            if pd.notna(value) and "Team-Nr." in str(value):
                team_start_rows.append(idx)
                break
    
    print(f"Found {len(team_start_rows)} team sections starting at rows: {team_start_rows}")
    
    for team_idx, start_row in enumerate(team_start_rows):
        print(f"\n=== Processing Team {team_idx + 1} ===")
        
        # Extract 30 rows for this team
        end_row = start_row + 30
        team_data = excel_df.iloc[start_row:end_row]
        
        # Extract team information
        team_info = extract_team_info(team_data)
        if week_override is not None:
            team_info["week"] = str(week_override)
        print(f"Team: {team_info['team_name']}")
        print(f"Location: {team_info['location']}")
        print(f"Week: {team_info['week']}")
        
        # Extract player data for this team
        team_players = extract_team_players(
            team_data,
            team_info,
            season,
            league,
            players_per_team,
            date,
            max_games_per_week=max_games_per_week,
        )
        
        # Add to CSV data
        csv_data.extend(team_players)
    
    return csv_data


def extract_team_info(team_data):
    """Extract basic team information from the first few rows."""
    
    team_info = {
        'team_name': 'Unknown Team',
        'location': 'Unknown',
        'week': '1',
        'opponent': 'Unknown'
    }
    
    # Debug: Print the actual row 2 (index 1) to see what's there
    if len(team_data) > 1:
        print(f"Row 2 (index 1) contents:")
        row_2 = team_data.iloc[1]
        for i, value in enumerate(row_2):
            if pd.notna(value):
                print(f"  Col {i}: '{value}'")
    
    # Location is always in column 30 (index 29) of row 2 (index 1)
    if len(team_data) > 1 and len(team_data.columns) > 5:
        location_value = team_data.iloc[1, 5]  # Row 2, Column 30 (index 29)
        print(f"Location value at col 30: '{location_value}' (type: {type(location_value)})")
        if pd.notna(location_value):
            team_info['location'] = str(location_value).strip()
            print(f"Location (col 30): {team_info['location']}")

    # Week is always in column 44 (index 43) of row 2 (index 1)
    if len(team_data) > 1 and len(team_data.columns) > 19:
        week_value = team_data.iloc[1, 19]  # Row 2, Column 44 (index 43)
        print(f"Week value at col 44: '{week_value}' (type: {type(week_value)})")
        if pd.notna(week_value):
            if isinstance(week_value, (int, float)) or (isinstance(week_value, str) and week_value.isdigit()):
                team_info['week'] = str(int(float(week_value)))
                print(f"Week (col 44): {team_info['week']}")
    
    # Row 3 (index 2): Team name
    team_name_row = team_data.iloc[2]
    for col, value in team_name_row.items():
        if pd.notna(value) and isinstance(value, str) and len(str(value).strip()) > 0:
            team_info['team_name'] = str(value).strip()
            break
    
    # Row 23 (index 22): Opponent team name
    opponent_row = team_data.iloc[22]
    print(f"\nOpponent row (row 23) values:")
    for col_idx, value in opponent_row.items():
        if pd.notna(value):
            print(f"  Col {col_idx}: '{value}'")
            # Look for team name patterns
            if isinstance(value, str) and len(str(value).strip()) > 0 and "Team" not in str(value):
                team_info['opponent'] = str(value).strip()
                break
        
        # Also check rows 25-29 for opponent info
        print(f"\nOpponent verification rows (25-29):")
        for row_idx in range(24, 29):
            row = team_data.iloc[row_idx]
            print(f"  Row {row_idx+1}: {[str(v) for v in row.values if pd.notna(v)]}")
        
        return team_info

def detect_game_count_from_anchor(team_data):
    """
    Detect game count from anchor layout:
    - Team anchor row is row 0 in team_data.
    - Game labels are expected at row +4 and col + 2*n (starting at +2).
    - Stop when value contains 'Gesamt' or is empty/non-game.
    """
    if team_data.shape[0] <= 4:
        return None
    header_row = team_data.iloc[4]
    count = 0
    game_number = 1
    while True:
        col_idx = 2 * game_number
        if col_idx >= team_data.shape[1]:
            break
        cell_value = header_row.iloc[col_idx]
        if pd.isna(cell_value):
            break
        value = str(cell_value).strip().lower()
        if "gesamt" in value:
            break
        if f"spiel {game_number}" in value:
            count += 1
            game_number += 1
            continue
        break
    return count if count > 0 else None


def extract_team_players(
    team_data,
    team_info,
    season,
    league,
    players_per_team,
    date,
    max_games_per_week=None,
):
    """Extract all player data for a team."""
    
    players = []
    
    # Find column headers (row 6, index 5)
    header_row = team_data.iloc[5]
    
    # Find important columns
    name_col = None
    id_col = None
    score_cols = []
    points_cols = []
    
    # Find Name and ID columns
    for col_idx, value in header_row.items():
        if pd.notna(value):
            value_str = str(value).lower()
            if "name" in value_str:
                name_col = col_idx
            elif "rl" in value_str:
                id_col = col_idx
    
    # Find individual round columns
    for col_idx, value in header_row.items():
        if pd.notna(value):
            value_str = str(value).lower()
            if "pins" in value_str and "gesamt" not in value_str:
                score_cols.append(col_idx)
            elif "pkt" in value_str and "gesamt" not in value_str:
                points_cols.append(col_idx)
    
    # Limit rounds conservatively.
    if len(score_cols) > 9:
        score_cols = score_cols[:9]
    if len(points_cols) > 9:
        points_cols = points_cols[:9]

    anchor_game_count = detect_game_count_from_anchor(team_data)
    candidate_limits = [len(score_cols)]
    if max_games_per_week is not None:
        try:
            mgpw = int(max_games_per_week)
            if mgpw > 0:
                candidate_limits.append(mgpw)
        except (TypeError, ValueError):
            pass
    if anchor_game_count is not None:
        candidate_limits.append(anchor_game_count)
    effective_round_limit = min(candidate_limits) if candidate_limits else len(score_cols)
    if effective_round_limit < len(score_cols):
        score_cols = score_cols[:effective_round_limit]
    if effective_round_limit < len(points_cols):
        points_cols = points_cols[:effective_round_limit]
    
    # Find opponent columns (same as score columns)
    opponent_row = team_data.iloc[22]
    opponent_cols = [col for col in score_cols if col in opponent_row.index and pd.notna(opponent_row[col])]
    
    # Find team total scores and points
    team_total_row = team_data.iloc[18]
    team_total_scores = {}
    team_total_points = {}
    
    for col_idx, value in team_total_row.items():
        if pd.notna(value) and col_idx in score_cols:
            round_idx = score_cols.index(col_idx)
            try:
                team_total_scores[round_idx] = int(value)
                if round_idx < len(points_cols):
                    points_col = points_cols[round_idx]
                    if pd.notna(team_total_row[points_col]):
                        team_total_points[round_idx] = float(team_total_row[points_col])
                    else:
                        team_total_points[round_idx] = 0.0
                else:
                    team_total_points[round_idx] = 0.0
            except (ValueError, TypeError):
                pass
    
    print(f"Found columns: Name={name_col}, ID={id_col}")
    print(f"Score columns (rounds): {score_cols}")
    print(f"Points columns (rounds): {points_cols}")
    print(f"Opponent columns (rounds): {opponent_cols}")
    print(f"Team total scores: {team_total_scores}")
    print(f"Team total points: {team_total_points}")
    
    # Define position ranges
    positions = [
        (6, 8),   # Position 1: rows 7-9
        (9, 11),  # Position 2: rows 10-12
        (12, 14), # Position 3: rows 13-15
        (15, 17)  # Position 4: rows 16-18
    ]
    
    for pos_idx, (start_row, end_row) in enumerate(positions):
        print(f"\nProcessing Position {pos_idx + 1} (rows {start_row+1}-{end_row+1})")
        
        pos_rows = team_data.iloc[start_row:end_row+1]
        
        for player_row_idx, row in pos_rows.iterrows():
            if name_col is not None and pd.notna(row[name_col]):
                player_name = str(row[name_col]).strip()
                
                # Get player ID
                player_id = 0
                if id_col is not None and pd.notna(row[id_col]):
                    try:
                        player_id = int(row[id_col])
                    except (ValueError, TypeError):
                        player_id = hash(f"{team_info['team_name']}_{player_name}_{pos_idx}") % 100000
                    
                print(f"  Player: {player_name} (ID: {player_id})")
                
                # Process each round (Spiel 1-9) - only individual rounds, not totals
                for round_idx, (score_col, points_col) in enumerate(zip(score_cols, points_cols)):
                    if pd.notna(row[score_col]):
                        try:
                            score = int(row[score_col])

                            points = float(pos_rows[points_col].sum()) if pd.notna(pos_rows[points_col].sum()) else 0.0
                            
                            # Get opponent
                            opponent = "Unknown"
                            if round_idx < len(opponent_cols):
                                opponent_col = opponent_cols[round_idx]
                                if pd.notna(opponent_row[opponent_col]):
                                    opponent = str(opponent_row[opponent_col]).strip()
                            
                            match_number = get_match_number(round_idx, team_info['team_name'], opponent)
                            
                            # Create CSV row
                            csv_row = {
                                'Season': season,
                                'Week': team_info['week'],
                                'Date': date,
                                'League': league,
                                'Players per Team': players_per_team,
                                'Location': team_info['location'],
                                'Round Number': round_idx + 1,
                                'Match Number': match_number,
                                'Team': team_info['team_name'],
                                'Position': pos_idx,
                                'Player': player_name,
                                'Player ID': player_id,
                                'Opponent': opponent,
                                'Score': score,
                                'Points': str(points),
                                'Bonus Points': '0',
                                'Input Data': 'True',
                                'Computed Data': 'False'
                            }
                            
                            players.append(csv_row)
                            print(f"    Round {round_idx + 1}: Score={score}, Points={points}, Opponent={opponent}")
                            
                        except (ValueError, TypeError) as e:
                            print(f"    Invalid data for round {round_idx + 1}: {e}")
    
    # Add team total rows
    for round_idx in range(len(score_cols)):
        if round_idx in team_total_scores:
            # Get opponent
            opponent = "Unknown"
            if round_idx < len(opponent_cols):
                opponent_col = opponent_cols[round_idx]
                if pd.notna(opponent_row[opponent_col]):
                    opponent = str(opponent_row[opponent_col]).strip()
            
            match_number = get_match_number(round_idx, team_info['team_name'], opponent)
            
            # Create CSV row for team total
            csv_row = {
                'Season': season,
                'Week': team_info['week'],
                'Date': date,
                'League': league,
                'Players per Team': players_per_team,
                'Location': team_info['location'],
                'Round Number': round_idx + 1,
                'Match Number': match_number,
                'Team': team_info['team_name'],
                'Position': 0,  # Team total
                'Player': 'Team Total',
                'Player ID': 0,
                'Opponent': opponent,
                'Score': team_total_scores[round_idx],
                'Points': str(team_total_points[round_idx]),
                'Bonus Points': '0',
                'Input Data': 'False',
                'Computed Data': 'True'
            }
            
            players.append(csv_row)
            print(f"  Team Total Round {round_idx + 1}: Score={team_total_scores[round_idx]}, Points={team_total_points[round_idx]}, Opponent={opponent}")

    return players


def parse_args():
    """Parse CLI args for analyze/process workflows."""
    parser = argparse.ArgumentParser(
        description="Analyze or process historic league Excel files."
    )
    parser.add_argument(
        "--mode",
        choices=["analyze", "process", "normalize_data", "convert_legacy_xls"],
        required=False,
        help="Run in analyze, process, normalize_data, or convert_legacy_xls mode.",
    )
    parser.add_argument(
        "--normalize_data",
        action="store_true",
        help="Alias for --mode normalize_data. Rebuild normalized merged output only.",
    )
    parser.add_argument(
        "--file",
        dest="excel_file",
        help="Single Excel file to analyze/process.",
    )
    parser.add_argument(
        "--folder",
        help="Folder to scan for Excel files.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively search for Excel files in --folder.",
    )
    parser.add_argument(
        "--team-sheet-prefix",
        default="Erfassung",
        help="Team sheet prefix used in process mode (default: Erfassung).",
    )
    parser.add_argument(
        "--season-sheet",
        default="Schiedsrichterinfos",
        help="Season sheet name (default: Schiedsrichterinfos).",
    )
    parser.add_argument(
        "--input",
        dest="input_files",
        nargs="+",
        default=None,
        help=(
            "normalize_data mode: one or more semicolon-separated CSVs to normalize "
            "(skips processing-cache merge). Default output is the first input file "
            "(in-place); use --output-file to write elsewhere."
        ),
    )
    parser.add_argument(
        "--output-file",
        default="database/data/historical_league_results.csv",
        help=(
            "Merged CSV path for process mode (all league/season combos in the run scope). "
            "normalize_data: destination when using --input (required if multiple inputs). "
            "Use a dedicated path for legacy scrape batches, then merge sources separately."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for per league/season combo CSVs in process mode. "
            "Default: <output-file parent>/<output-file stem>_combos"
        ),
    )
    parser.add_argument(
        "--weeks",
        help="Comma-separated week numbers for process mode (e.g. 1,2,3).",
    )
    parser.add_argument(
        "--analysis-output",
        help="Optional CSV path for analyze mode results.",
    )
    parser.add_argument(
        "--skip_xls",
        action="store_true",
        help="Skip legacy .xls files during analyze/process.",
    )
    parser.add_argument(
        "--old-format-sheet-threshold",
        type=int,
        default=15,
        help="If sheet count is below this and Spielorte is missing, mark as old 1-week format.",
    )
    parser.add_argument(
        "--force_reanalyze",
        action="store_true",
        help="Ignore analysis cache and re-analyze all files for this run.",
    )
    parser.add_argument(
        "--no-parallel-subdirs",
        action="store_true",
        help=(
            "process mode: disable one worker per top-level folder under --folder "
            "(default: on when there are 2+ such subfolders)."
        ),
    )
    parser.add_argument(
        "--force_convert_xls",
        action="store_true",
        help=(
            "convert_legacy_xls: overwrite existing .xlsx siblings. "
            "Default is to skip conversion when <stem>.xlsx already exists."
        ),
    )
    return parser.parse_args()


def validate_args(args):
    """Validate mutually dependent CLI args."""
    if args.normalize_data:
        args.mode = "normalize_data"

    if not args.mode:
        raise ValueError("Provide --mode (or use --normalize_data alias).")

    if args.mode == "normalize_data":
        if args.excel_file or args.folder:
            raise ValueError("normalize_data mode does not accept --file/--folder.")
        if args.input_files:
            if len(args.input_files) > 1 and not _cli_flag_passed("--output-file"):
                raise ValueError(
                    "normalize_data with multiple --input files requires --output-file."
                )
            for input_path in args.input_files:
                if not Path(input_path).is_file():
                    raise ValueError(f"Input file not found: {input_path}")
        return

    if not args.excel_file and not args.folder:
        raise ValueError("Provide either --file or --folder.")
    if args.excel_file and args.folder:
        raise ValueError("Use either --file or --folder, not both.")
    if args.recursive and not args.folder:
        raise ValueError("--recursive requires --folder.")

    if args.excel_file and not Path(args.excel_file).is_file():
        raise ValueError(f"File not found: {args.excel_file}")
    if args.folder and not Path(args.folder).is_dir():
        raise ValueError(f"Folder not found: {args.folder}")


def parse_weeks(weeks_arg):
    """Parse week list from CLI argument."""
    if not weeks_arg:
        return [1]
    weeks = []
    for token in weeks_arg.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            weeks.append(int(token))
        except ValueError as exc:
            raise ValueError(f"Invalid week value '{token}' in --weeks.") from exc
    if not weeks:
        raise ValueError("No valid week values supplied in --weeks.")
    return weeks


def discover_excel_files(args):
    """Return deterministic list of .xls/.xlsx files and skipped-by-keyword files."""
    if args.excel_file:
        file_path = Path(args.excel_file)
        excluded_keywords = ["fehlerhaft", "logdatei"]
        if any(keyword in str(file_path).lower() for keyword in excluded_keywords):
            return [], [file_path]
        return [file_path], []

    folder = Path(args.folder)
    patterns = ["*.xlsx", "*.xls"]
    files = []
    for pattern in patterns:
        if args.recursive:
            files.extend(folder.rglob(pattern))
        else:
            files.extend(folder.glob(pattern))
    files = [path for path in files if path.is_file()]
    excluded_keywords = ["fehlerhaft", "logdatei"]
    skipped_files = [
        path
        for path in files
        if any(keyword in str(path).lower() for keyword in excluded_keywords)
    ]
    files = [
        path
        for path in files
        if not any(keyword in str(path).lower() for keyword in excluded_keywords)
    ]
    files = sorted(set(files))
    skipped_files = sorted(set(skipped_files))
    return files, skipped_files


def dedupe_xls_when_xlsx_present(excel_files):
    """Drop .xls paths when a same-stem .xlsx exists (avoids double process after conversion)."""
    xlsx_stems = {path.stem.lower() for path in excel_files if path.suffix.lower() == ".xlsx"}
    return [
        path
        for path in excel_files
        if path.suffix.lower() != ".xls" or path.stem.lower() not in xlsx_stems
    ]


def filter_xls_for_mode(excel_files, mode, skip_xls):
    """Optionally filter .xls files for analyze/process modes."""
    if not skip_xls or mode == "convert_legacy_xls":
        return excel_files
    return [file_path for file_path in excel_files if file_path.suffix.lower() != ".xls"]


def print_progress_bar(current, total, prefix, bar_width=30):
    """Print a simple in-place console progress bar."""
    if total <= 0:
        return
    ratio = min(max(current / total, 0), 1)
    filled = int(bar_width * ratio)
    bar = "#" * filled + "-" * (bar_width - filled)
    percent = ratio * 100
    print(f"\r{prefix} [{bar}] {current}/{total} ({percent:5.1f}%)", end="", flush=True)
    if current >= total:
        print()


def parse_metadata_int(value):
    """Convert metadata cell to integer if possible."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        if np.isnan(value):
            return None
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        return int(float(text))
    except ValueError:
        return None


def normalize_optional_text(value):
    """Normalize metadata text value."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def clean_league_name(value):
    """Normalize league label and strip season fragments like 25/26 or 2025/2026."""
    text = normalize_optional_text(value)
    if not text:
        return None
    cleaned = re.sub(r"\b\d{2}/\d{2}(?:\+1)?\b", "", text)
    cleaned = re.sub(r"\b\d{4}/\d{4}\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -_/;:,")
    return cleaned or None


def get_cell_value(df, row_idx, col_idx):
    """Safely return dataframe cell value or NaN."""
    if df.shape[0] > row_idx and df.shape[1] > col_idx:
        return df.iloc[row_idx, col_idx]
    return np.nan


def get_cells_text(df, row_idx: int, col_start: int, col_end: int) -> str | None:
    """Join non-empty cells on one row (merged Excel ranges like C1:F1)."""
    parts: list[str] = []
    for col_idx in range(col_start, col_end + 1):
        text = normalize_optional_text(get_cell_value(df, row_idx, col_idx))
        if text:
            parts.append(text)
    if not parts:
        return None
    return " ".join(parts).strip()


def resolve_with_fallbacks(resolvers):
    """Return first non-empty resolver value with source tag."""
    for source, resolver in resolvers:
        try:
            value = resolver()
        except Exception:
            value = None
        if value is not None:
            return value, source
    return None, None


def detect_league_from_filename(excel_file):
    """Detect league code from input filename."""
    stem = Path(excel_file).stem
    match = re.match(r"([A-Za-z]{2,})", stem)
    if match:
        return match.group(1).upper()
    return "UNKNOWN"


def extract_league_from_schluessel(excel_file, workbook=None):
    """Read league name from default location: Schlüssel!C1."""
    read_bounds = (
        {"workbook": workbook, "nrows": _ANALYZE_SCHLUESSEL_NROWS, "usecols": _ANALYZE_SCHLUESSEL_USECOLS}
        if workbook is not None
        else {}
    )
    schluessel_df = read_excel_safely(excel_file, sheet_name="Schlüssel", header=None, **read_bounds)
    raw = get_cell_value(schluessel_df, 0, 2)
    mapped = normalize_league_display_to_canonical(raw)
    return mapped if mapped else clean_league_name(raw)


def is_valid_data_value(value):
    """Return whether a worksheet cell counts as actual data."""
    if pd.isna(value):
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "n/a", "na", "nan", "-", "--", "none"}:
            return False
    return True


def week_sheet_has_valid_data(excel_file, week_number, workbook=None):
    """Check if Schnitt{week_number} has at least 10 data rows in columns A..G."""
    possible_sheet_names = [f"Schnitt#{week_number}", f"Schnitt{week_number}"]
    read_bounds = (
        {
            "workbook": workbook,
            "nrows": _ANALYZE_WEEK_SHEET_NROWS,
            "usecols": _ANALYZE_WEEK_SHEET_USECOLS,
        }
        if workbook is not None
        else {}
    )
    week_df = None
    for sheet_name in possible_sheet_names:
        try:
            week_df = read_excel_safely(
                excel_file,
                sheet_name=sheet_name,
                header=None,
                **read_bounds,
            )
            break
        except Exception:
            continue
    if week_df is None:
        return False
    cols_a_to_g = week_df.iloc[:, :7] if week_df.shape[1] >= 7 else week_df
    valid_rows = cols_a_to_g.apply(
        lambda row: any(is_valid_data_value(cell) for cell in row),
        axis=1,
    ).sum()
    return int(valid_rows) >= 10


def parse_week_from_text(value):
    """Extract week number from free text."""
    text = normalize_optional_text(value)
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    try:
        week = int(match.group(0))
        return week if week > 0 else None
    except ValueError:
        return None


def parse_old_format_date(value):
    """Parse old-format Ligabericht dates: German text or Excel/LibreOffice datetime cells."""
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        dt = None
    if dt is not None:
        year_full = int(dt.year)
        if _excel_date_year_is_placeholder(year_full):
            year_full = None
        return {
            "day": dt.day,
            "month": dt.month,
            "year_full": year_full,
            "raw": dt.strftime("%Y-%m-%d"),
        }

    text = normalize_optional_text(value)
    if not text:
        return None
    # Find all date-like tokens and use the last one (usually main match day).
    matches = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if matches:
        day_str, month_str, year_str = matches[-1]
        day = int(day_str)
        month = int(month_str)
        if len(year_str) == 2:
            year_full = 2000 + int(year_str)
        else:
            year_full = int(year_str)
        return {
            "day": day,
            "month": month,
            "year_full": year_full,
            "raw": text,
        }
    short_matches = re.findall(r"(\d{1,2})\.(\d{1,2})\.(?!\d)", text)
    if short_matches:
        day_str, month_str = short_matches[-1]
        return {
            "day": int(day_str),
            "month": int(month_str),
            "year_full": None,
            "raw": text,
        }
    # e.g. "4./5.10.08" — use the main match day (second date).
    range_match = re.search(r"(?:\d{1,2}\./)?(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if range_match:
        day_str, month_str, year_str = range_match.groups()
        year_full = 2000 + int(year_str) if len(year_str) == 2 else int(year_str)
        if _excel_date_year_is_placeholder(year_full):
            year_full = None
        return {
            "day": int(day_str),
            "month": int(month_str),
            "year_full": year_full,
            "raw": text,
        }
    return None


def _pre_2022_metadata_value_present(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return bool(str(value).strip())


def _pre_2022_value_beside_label(df, row_idx: int, col_idx: int, max_col: int):
    """Read the first non-empty cell to the right of a label (typical Ligabericht layout)."""
    for offset in (2, 1, 3, 4):
        c = col_idx + offset
        if c >= max_col:
            continue
        value = get_cell_value(df, row_idx, c)
        if _pre_2022_metadata_value_present(value):
            return value
    return None


def _parse_ligabericht_metadata_df(df) -> dict:
    """
    Parse Ligabericht header fields.

    Supports two layouts seen in Bavarian exports:
    - Classic: league P8, week E6, date Q6, location E8 (0-based row/col 7/15, 5/4, 5/16, 7/4)
    - Spielberichtsbogen: label row with Spieltag (~row 4), Anlage/Liga (~row 6)
    """
    meta = {
        "source": "ligabericht",
        "league_raw": get_cell_value(df, 7, 15),
        "location_raw": get_cell_value(df, 7, 4),
        "week_raw": get_cell_value(df, 5, 4),
        "date_raw": get_cell_value(df, 5, 16),
    }
    max_row = min(len(df), 15)
    max_col = min(int(df.shape[1]), 22) if getattr(df, "shape", None) else 22

    for row_idx in range(max_row):
        for col_idx in range(max_col):
            label = (normalize_optional_text(get_cell_value(df, row_idx, col_idx)) or "").rstrip(
                ":"
            ).lower()
            if not label:
                continue
            if label == "spieltag" and not _pre_2022_metadata_value_present(meta["week_raw"]):
                meta["week_raw"] = _pre_2022_value_beside_label(df, row_idx, col_idx, max_col)
            elif label == "anlage" and not _pre_2022_metadata_value_present(meta["location_raw"]):
                meta["location_raw"] = _pre_2022_value_beside_label(df, row_idx, col_idx, max_col)
            elif label == "liga" and not _pre_2022_metadata_value_present(meta["league_raw"]):
                meta["league_raw"] = _pre_2022_value_beside_label(df, row_idx, col_idx, max_col)
            elif label == "datum" and not _pre_2022_metadata_value_present(meta["date_raw"]):
                meta["date_raw"] = _pre_2022_value_beside_label(df, row_idx, col_idx, max_col)
    return meta


def _pre_2022_metadata_core_fields_ok(meta: dict) -> bool:
    return (
        _pre_2022_metadata_value_present(meta.get("league_raw"))
        and _pre_2022_metadata_value_present(meta.get("week_raw"))
        and _pre_2022_metadata_value_present(meta.get("location_raw"))
    )


def _merge_pre_2022_metadata(primary: dict, fallback: dict) -> dict:
    """Fill empty primary fields from fallback (e.g. date from Spielzettel)."""
    merged = dict(primary)
    for key in ("league_raw", "week_raw", "date_raw", "location_raw"):
        if not _pre_2022_metadata_value_present(merged.get(key)) and _pre_2022_metadata_value_present(
            fallback.get(key)
        ):
            merged[key] = fallback[key]
    return merged


def read_pre_2022_metadata_from_spielzettel(excel_path, workbook=None) -> dict | None:
    """
    Four-sheet legacy exports (no Ligabericht): Spielzettel header block.

    Excel layout (1-based rows/cols):
      C1:F1 season, D2:F2 league, D3 date, D4:F4 venue; Spieltag value beside date (F3).
    """
    read_kwargs: dict = {"sheet_name": "Spielzettel", "header": None, "nrows": 8}
    if workbook is not None:
        read_kwargs["workbook"] = workbook
    try:
        df = read_excel_safely(excel_path, **read_kwargs)
    except Exception:
        return None
    # 0-based: row 0 = Excel 1, col C = 2 …
    week_raw = get_cell_value(df, 2, 5)
    if not _pre_2022_metadata_value_present(week_raw):
        for col_idx in range(4, 7):
            label = (normalize_optional_text(get_cell_value(df, 2, col_idx)) or "").rstrip(":").lower()
            if label == "spieltag":
                week_raw = _pre_2022_value_beside_label(df, 2, col_idx, min(int(df.shape[1]), 12))
                break
    return {
        "source": "spielzettel",
        "season_raw": get_cells_text(df, 0, 2, 5),
        "league_raw": get_cells_text(df, 1, 3, 5),
        "date_raw": get_cell_value(df, 2, 3),
        "week_raw": week_raw,
        "location_raw": get_cells_text(df, 3, 3, 5),
    }


def infer_pre_2022_number_of_teams(
    excel_path,
    tabelle_df: pd.DataFrame | None = None,
    *,
    workbook=None,
) -> int | None:
    """Team count from Tabelle N3:Q3, title-row integer, or Spielzettel block count."""
    if tabelle_df is not None:
        classic = parse_metadata_int(get_cell_value(tabelle_df, 2, 13))
        if classic is not None and classic > 0:
            return int(classic)
        max_col = min(int(tabelle_df.shape[1]), 8)
        for col_idx in range(max_col):
            candidate = parse_metadata_int(get_cell_value(tabelle_df, 2, col_idx))
            if candidate is not None and 4 <= int(candidate) <= 24:
                return int(candidate)

    if "Spielzettel" not in get_sheet_names_safely(excel_path, workbook=workbook):
        return None
    read_kwargs: dict = {"sheet_name": "Spielzettel", "header": None}
    if workbook is not None:
        read_kwargs["workbook"] = workbook
    try:
        spielzettel_df = read_excel_safely(excel_path, **read_kwargs)
        block_count = len(list(_find_spielzettel_block_starts(spielzettel_df)))
        if block_count >= 4:
            return int(block_count)
    except Exception:
        return None
    return None


def read_pre_2022_metadata_from_ligabericht(excel_path, workbook=None) -> dict | None:
    read_kwargs: dict = {"sheet_name": "Ligabericht", "header": None, "nrows": _ANALYZE_LIGABERICHT_NROWS}
    if workbook is not None:
        read_kwargs["workbook"] = workbook
    try:
        df = read_excel_safely(excel_path, **read_kwargs)
    except Exception:
        return None
    meta = _parse_ligabericht_metadata_df(df)
    if _pre_2022_metadata_core_fields_ok(meta):
        return meta
    return None


def resolve_pre_2022_workbook_metadata(
    excel_path, sheet_names: list[str], workbook=None
) -> dict | None:
    """Prefer Ligabericht; merge date from Spielzettel when Ligabericht omits it."""
    spielzettel_meta = None
    if "Spielzettel" in sheet_names:
        spielzettel_meta = read_pre_2022_metadata_from_spielzettel(excel_path, workbook=workbook)

    if "Ligabericht" in sheet_names:
        ligabericht_meta = read_pre_2022_metadata_from_ligabericht(excel_path, workbook=workbook)
        if ligabericht_meta is not None:
            if spielzettel_meta is not None:
                return _merge_pre_2022_metadata(ligabericht_meta, spielzettel_meta)
            return ligabericht_meta

    return spielzettel_meta


def derive_season_from_old_date(date_info):
    """Derive sports season YY/YY from parsed old-format date."""
    if not date_info:
        return None
    month = date_info["month"]
    year_full = date_info["year_full"]
    if month <= 9:
        start_year = year_full - 1
        end_year = year_full
    else:
        start_year = year_full
        end_year = year_full + 1
    return f"{str(start_year)[-2:]}/{str(end_year)[-2:]}"


def old_format_results_are_valid(excel_file, workbook=None):
    """Validate old-format result presence in Tagesschnittliste."""
    read_bounds = (
        {
            "workbook": workbook,
            "nrows": _ANALYZE_TAGesschnitt_NROWS,
            "usecols": _ANALYZE_WEEK_SHEET_USECOLS,
        }
        if workbook is not None
        else {}
    )
    try:
        df = read_excel_safely(
            excel_file,
            sheet_name="Tagesschnittliste",
            header=None,
            **read_bounds,
        )
    except Exception:
        return False
    valid_rows = df.apply(
        lambda row: any(is_valid_data_value(cell) for cell in row),
        axis=1,
    ).sum()
    return int(valid_rows) >= 10


# Pre-2022 extract conventions (Spielzettel / Tabelle; no Erfassung blocks):
# - Spielzettel layout: each team block (~20 rows). Player columns G..L (0-based 6..11):
#   name on Liga row, EDV-Nr. on row below, one pin score per opponent row from row 9+.
#   Opponent name in C, opponent team total in F (required), own team total in O (scores only).
#   Match rounds 1..(teams-1) per Spieltag; round 0 = weekly placement bonus row.
# - Points are never read from Excel — computed via database/relational_csv/scoring_system.csv
#   (default liga_bayern_2pt): team totals W-T-L → 2/1/0; weekly placement 1..N by pin rank.
# - Lineup Position is not in source data; assign 0..(players_per_team-1) left-to-right
#   in the team's player columns on Spielzettel (same 0-based scheme as post-2022
#   extract_team_players). Scoring ignores position; values are for CSV compatibility only.
# - Team Total rows: Position 0, Player "Team Total", Computed Data True (unchanged).
# - Bonus Points column: weekly placement on round-0 Team Total row; match points in Points only.


def pre_2022_lineup_position_from_column_order(player_column_index: int) -> int:
    """Map left-to-right player column index (0-based) to legacy Position field."""
    return player_column_index


PRE_2022_PLACEMENT_BONUS_ROUND = 0
PRE_2022_SCORING_SYSTEM_ID = "liga_bayern_2pt"
_PRE_2022_SCORING_SYSTEM_PATH = (
    Path(__file__).resolve().parent / "database" / "relational_csv" / "scoring_system.csv"
)
_PRE_2022_SCORING_CACHE: Dict[str, dict] = {}
# Typical player columns on Spielzettel (Excel G..L); M/N used when roster is larger.
PRE_2022_PLAYER_COL_START = 6
PRE_2022_PLAYER_COL_END = 14
PRE_2022_OPPONENT_NAME_COL = 2
PRE_2022_OPPONENT_TOTAL_COL = 5
PRE_2022_TEAM_TOTAL_COL = 14


def get_pre_2022_scoring(scoring_system_id: str = PRE_2022_SCORING_SYSTEM_ID) -> dict:
    """Load team-match scoring from scoring_system.csv (liga_bayern_2pt for pre-2022 BayL)."""
    if scoring_system_id in _PRE_2022_SCORING_CACHE:
        return _PRE_2022_SCORING_CACHE[scoring_system_id]
    if not _PRE_2022_SCORING_SYSTEM_PATH.is_file():
        raise FileNotFoundError(f"Missing scoring system table: {_PRE_2022_SCORING_SYSTEM_PATH}")
    scoring_df = pd.read_csv(_PRE_2022_SCORING_SYSTEM_PATH)
    row = scoring_df[scoring_df["id"].astype(str) == scoring_system_id]
    if row.empty:
        raise ValueError(f"Unknown scoring_system id: {scoring_system_id}")
    record = row.iloc[0]
    scoring = {
        "id": str(record["id"]),
        "team_win": float(record["points_per_team_match_win"]),
        "team_tie": float(record["points_per_team_match_tie"]),
        "team_loss": float(record["points_per_team_match_loss"]),
    }
    _PRE_2022_SCORING_CACHE[scoring_system_id] = scoring
    return scoring


def _parse_numeric_cell(value):
    """Parse worksheet cell to int/float; return None when not numeric."""
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if float(value).is_integer():
            return int(value)
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def _cell_text_equals(value, label: str) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().lower() == label.strip().lower()


def _metric_left_of_label(block_df: pd.DataFrame, row_start: int, row_end: int, label: str):
    """Read numeric value in the cell immediately left of a label (e.g. 12 | Punkte)."""
    for row_idx in range(row_start, min(row_end, len(block_df))):
        for col_idx in range(1, block_df.shape[1]):
            if _cell_text_equals(block_df.iat[row_idx, col_idx], label):
                return _parse_numeric_cell(block_df.iat[row_idx, col_idx - 1])
    return None


def _find_spielzettel_block_starts(df: pd.DataFrame):
    """Yield (row_index, team_name) for each Spielzettel team block."""
    for row_idx in range(len(df)):
        for col_idx in range(df.shape[1]):
            if not _cell_text_equals(df.iat[row_idx, col_idx], "Team:"):
                continue
            team_name = normalize_optional_text(
                df.iat[row_idx, col_idx + 1] if col_idx + 1 < df.shape[1] else np.nan
            )
            if team_name:
                yield row_idx, team_name
            break


def _pre_2022_players_for_block(df: pd.DataFrame, block_start: int, block_end: int):
    """Players ordered left-to-right from EDV-Nr. row (Position 0..n-1)."""
    edv_row = None
    for row_idx in range(block_start, min(block_start + 12, block_end)):
        for col_idx in range(df.shape[1]):
            if _cell_text_equals(df.iat[row_idx, col_idx], "EDV-Nr.:"):
                edv_row = row_idx
                break
        if edv_row is not None:
            break
    if edv_row is None:
        return [], None

    names_row = None
    for row_idx in range(block_start, edv_row):
        if _cell_text_equals(df.iat[row_idx, 2], "Liga:"):
            names_row = row_idx
            break
    if names_row is None:
        names_row = block_start + 1

    players = []
    for col_idx in range(PRE_2022_PLAYER_COL_START, min(PRE_2022_PLAYER_COL_END, df.shape[1])):
        player_id = _parse_numeric_cell(df.iat[edv_row, col_idx])
        if player_id is None or player_id == 0:
            continue
        player_name = normalize_optional_text(df.iat[names_row, col_idx])
        if not player_name:
            continue
        lowered = player_name.lower()
        if lowered.startswith("liga:") or "ligasaison" in lowered:
            continue
        players.append(
            {
                "position": pre_2022_lineup_position_from_column_order(len(players)),
                "player_name": player_name,
                "player_id": int(player_id),
                "col_idx": col_idx,
            }
        )
    header_row = edv_row + 1
    return players, header_row


def _pre_2022_team_match_points(team_total, opponent_total, scoring: dict) -> float:
    """W-T-L on team vs opponent pin totals using scoring_system team-match columns."""
    if team_total is None or opponent_total is None:
        return 0.0
    if team_total > opponent_total:
        return scoring["team_win"]
    if team_total < opponent_total:
        return scoring["team_loss"]
    return scoring["team_tie"]


def _pre_2022_weekly_placement_bonuses(
    team_weekly_pins: dict[str, int],
    number_of_teams: int | None,
) -> dict[str, float]:
    """
    Rank teams by Spieltag pinfall; 1st gets N, last gets 1 (N = number_of_teams in league).
    """
    team_count = int(number_of_teams) if number_of_teams and int(number_of_teams) > 0 else len(team_weekly_pins)
    if team_count <= 0:
        return {}
    ordered = sorted(team_weekly_pins.items(), key=lambda item: (-item[1], item[0]))
    return {team: float(max(1, team_count - rank_idx)) for rank_idx, (team, _) in enumerate(ordered)}


def _pre_2022_max_opponent_rows(number_of_teams) -> int:
    """Round-robin opponents per Spieltag (teams in league minus self)."""
    if number_of_teams is not None and int(number_of_teams) > 1:
        return int(number_of_teams) - 1
    return 9


def _pre_2022_row_is_opponent_match(df: pd.DataFrame, row_idx: int, opponent: str) -> bool:
    """True when row looks like a scored opponent matchup, not a secretary note."""
    if not opponent:
        return False
    stripped = opponent.strip()
    if stripped.startswith("*"):
        return False
    lowered = stripped.lower()
    if "abweichender" in lowered or "wertungsschnitt" in lowered:
        return False
    if lowered.startswith("summe") or lowered.startswith("anzahl"):
        return False
    if "ligasaison" in lowered or lowered.startswith("liga:"):
        return False
    if "bbu e.v" in lowered:
        return False
    if df.shape[1] <= PRE_2022_OPPONENT_TOTAL_COL:
        return False
    if _parse_numeric_cell(df.iat[row_idx, PRE_2022_OPPONENT_TOTAL_COL]) is None:
        return False
    return True


def _pre_2022_team_total_column(df: pd.DataFrame, header_row: int) -> int:
    """Column index for per-match own-team pin total (Gesamt, usually col O)."""
    for col_idx in range(df.shape[1]):
        if _cell_text_equals(df.iat[header_row, col_idx], "Gesamt"):
            return col_idx
    return PRE_2022_TEAM_TOTAL_COL


def _pre_2022_build_row(
    *,
    season,
    week,
    full_date,
    league,
    players_per_team,
    location,
    round_number,
    match_number,
    team,
    opponent,
    position,
    player,
    player_id,
    score,
    points,
    bonus_points=0,
    input_data,
    computed_data,
):
    return {
        "Season": season,
        "Week": str(week),
        "Date": full_date,
        "League": league,
        "Players per Team": players_per_team,
        "Location": location,
        "Round Number": round_number,
        "Match Number": match_number,
        "Team": team,
        "Position": position,
        "Player": player,
        "Player ID": player_id,
        "Opponent": opponent,
        "Score": score,
        "Points": str(points),
        "Bonus Points": str(bonus_points),
        "Input Data": "True" if input_data else "False",
        "Computed Data": "True" if computed_data else "False",
    }


def _extract_pre_2022_spielzettel_block(
    df: pd.DataFrame,
    block_start: int,
    block_end: int,
    *,
    season: str,
    week: int,
    full_date: str,
    league: str,
    location: str,
    team_name: str,
    players_per_team: int,
    number_of_teams: int | None = None,
    scoring: dict | None = None,
):
    rows = []
    players, header_row = _pre_2022_players_for_block(df, block_start, block_end)
    if header_row is None or not players:
        return rows, 0

    if scoring is None:
        scoring = get_pre_2022_scoring()

    gesamt_col = _pre_2022_team_total_column(df, header_row)
    max_opponent_rows = _pre_2022_max_opponent_rows(number_of_teams)

    global dict_of_match_numbers
    games_parsed = 0
    weekly_pinfall = 0
    for row_idx in range(header_row + 1, block_end):
        if games_parsed >= max_opponent_rows:
            break

        opponent = normalize_optional_text(
            df.iat[row_idx, PRE_2022_OPPONENT_NAME_COL]
            if df.shape[1] > PRE_2022_OPPONENT_NAME_COL
            else None
        )
        if not _pre_2022_row_is_opponent_match(df, row_idx, opponent):
            continue

        # Round 1..N within Spieltag (round 0 reserved for weekly placement bonus).
        round_number = games_parsed + 1
        games_parsed += 1

        opponent_total = _parse_numeric_cell(
            df.iat[row_idx, PRE_2022_OPPONENT_TOTAL_COL]
            if df.shape[1] > PRE_2022_OPPONENT_TOTAL_COL
            else None
        )
        team_match_score = _parse_numeric_cell(
            df.iat[row_idx, gesamt_col] if df.shape[1] > gesamt_col else None
        )
        team_match_points = _pre_2022_team_match_points(team_match_score, opponent_total, scoring)
        if team_match_score is not None:
            weekly_pinfall += int(team_match_score)

        match_number = get_match_number(round_number - 1, team_name, opponent)

        for player in players:
            col_idx = player["col_idx"]
            score = _parse_numeric_cell(df.iat[row_idx, col_idx])
            if score is None:
                continue
            rows.append(
                _pre_2022_build_row(
                    season=season,
                    week=week,
                    full_date=full_date,
                    league=league,
                    players_per_team=players_per_team,
                    location=location,
                    round_number=round_number,
                    match_number=match_number,
                    team=team_name,
                    opponent=opponent,
                    position=player["position"],
                    player=player["player_name"],
                    player_id=player["player_id"],
                    score=int(score),
                    points=0,
                    bonus_points=0,
                    input_data=True,
                    computed_data=False,
                )
            )

        if team_match_score is not None or team_match_points is not None:
            rows.append(
                _pre_2022_build_row(
                    season=season,
                    week=week,
                    full_date=full_date,
                    league=league,
                    players_per_team=players_per_team,
                    location=location,
                    round_number=round_number,
                    match_number=match_number,
                    team=team_name,
                    opponent=opponent,
                    position=0,
                    player="Team Total",
                    player_id=0,
                    score=int(team_match_score or 0),
                    points=float(team_match_points or 0),
                    bonus_points=0,
                    input_data=False,
                    computed_data=True,
                )
            )

    return rows, weekly_pinfall


def _pre_2022_placement_bonus_row(
    *,
    season: str,
    week: int,
    full_date: str,
    league: str,
    location: str,
    team_name: str,
    players_per_team: int,
    weekly_pinfall: int,
    placement_bonus: float,
):
    return _pre_2022_build_row(
        season=season,
        week=week,
        full_date=full_date,
        league=league,
        players_per_team=players_per_team,
        location=location,
        round_number=PRE_2022_PLACEMENT_BONUS_ROUND,
        match_number=0,
        team=team_name,
        opponent="",
        position=0,
        player="Team Total",
        player_id=0,
        score=int(weekly_pinfall),
        points=0,
        bonus_points=float(placement_bonus),
        input_data=False,
        computed_data=True,
    )


def pre_2022_full_date(season_short: str, date_raw, excel_file: Path) -> str:
    """Build YYYY-MM-DD from Ligabericht date text and season label or folder path."""
    path_season = infer_season_from_path(excel_file)
    season_info = path_season or (
        season_label_to_season_info(season_short) if season_short else None
    )
    if season_info is None or _season_from_content_is_uncertain(season_short or ""):
        if path_season:
            season_info = path_season
    if season_info is None:
        season_info = {"season_short": season_short or "??/??", "year1": "????", "year2": "????"}

    date_info = complete_old_format_date_info(
        parse_old_format_date(date_raw), season_info
    )
    if old_format_date_is_usable(date_info, season_info):
        return combine_season_and_date(
            season_info,
            {"day": str(date_info["day"]).zfill(2), "month": str(date_info["month"]).zfill(2)},
        )
    return "could not extract date"


def extract_pre_2022_file(
    excel_file,
    *,
    league: str,
    season: str,
    week: int,
    location: str,
    players_per_team: int = 4,
    number_of_teams: int | None = None,
    scoring_system_id: str = PRE_2022_SCORING_SYSTEM_ID,
):
    """Extract one pre-2022 workbook (single Spieltag) into legacy flat CSV rows."""
    scoring = get_pre_2022_scoring(scoring_system_id)
    excel_path = Path(excel_file)
    sheet_names = get_sheet_names_safely(excel_path)
    if "Spielzettel" not in sheet_names:
        print(f"Warning: no Spielzettel sheet in {excel_path}")
        return []

    header_meta = resolve_pre_2022_workbook_metadata(excel_path, sheet_names)
    date_raw = header_meta["date_raw"] if header_meta else None
    full_date = pre_2022_full_date(season, date_raw, excel_path)

    spielzettel_df = read_excel_safely(excel_path, sheet_name="Spielzettel", header=None)
    block_starts = list(_find_spielzettel_block_starts(spielzettel_df))
    if not block_starts:
        print(f"Warning: no team blocks found on Spielzettel in {excel_path}")
        return []

    csv_rows = []
    team_weekly_pins: dict[str, int] = {}
    for index, (block_start, team_name) in enumerate(block_starts):
        block_end = block_starts[index + 1][0] if index + 1 < len(block_starts) else len(spielzettel_df)
        block_rows, weekly_pinfall = _extract_pre_2022_spielzettel_block(
            spielzettel_df,
            block_start,
            block_end,
            season=season,
            week=int(week),
            full_date=full_date,
            league=league,
            location=location or "Unknown",
            team_name=team_name,
            players_per_team=int(players_per_team or 4),
            number_of_teams=number_of_teams,
            scoring=scoring,
        )
        csv_rows.extend(block_rows)
        if weekly_pinfall > 0:
            team_weekly_pins[team_name] = weekly_pinfall

    placement_bonuses = _pre_2022_weekly_placement_bonuses(team_weekly_pins, number_of_teams)
    for team_name, bonus_points in placement_bonuses.items():
        csv_rows.append(
            _pre_2022_placement_bonus_row(
                season=season,
                week=int(week),
                full_date=full_date,
                league=league,
                location=location or "Unknown",
                team_name=team_name,
                players_per_team=int(players_per_team or 4),
                weekly_pinfall=team_weekly_pins[team_name],
                placement_bonus=bonus_points,
            )
        )
    return csv_rows


def _analysis_error_result(excel_path: Path, error: Exception | str) -> dict:
    """Return a full analyze row when the workbook cannot be opened or parsed."""
    message = str(error).strip() or error.__class__.__name__
    return {
        "file": str(excel_path),
        "data_format": "unknown",
        "league": None,
        "season": None,
        "location": None,
        "number_of_teams": None,
        "number_of_weeks": None,
        "games_per_week": None,
        "players_per_team": 4,
        "sheet_count": None,
        "available_weeks": "",
        "league_source": "",
        "season_source": "",
        "teams_source": "",
        "weeks_source": "",
        "games_per_week_source": "",
        "degradation_trace": "",
        "debug_league_raw": "",
        "debug_week_raw": "",
        "debug_date_raw": "",
        "debug_location_raw": "",
        "debug_teams_raw": "",
        "eligible_for_processing": False,
        "issues": f"Workbook could not be analyzed: {message}",
    }


def analyze_excel_file(excel_file, old_format_sheet_threshold=15):
    """Analyze one Excel file for metadata and processing eligibility."""
    excel_path = Path(excel_file)
    try:
        with open_workbook_session(excel_path) as workbook:
            return _analyze_excel_file_with_workbook(
                excel_path,
                workbook,
                old_format_sheet_threshold=old_format_sheet_threshold,
            )
    except Exception as exc:
        return _analysis_error_result(excel_path, exc)


def _analyze_excel_file_with_workbook(excel_path, workbook, old_format_sheet_threshold=15):
    """Analyze one workbook using a single open ExcelFile session."""
    result = {
        "file": str(excel_path),
        "data_format": "data_format_post_2022",
        "league": None,
        "season": None,
        "location": None,
        "number_of_teams": None,
        "number_of_weeks": None,
        "games_per_week": None,
        "players_per_team": 4,
        "sheet_count": None,
        "available_weeks": "",
        "league_source": "",
        "season_source": "",
        "teams_source": "",
        "weeks_source": "",
        "games_per_week_source": "",
        "degradation_trace": "",
        "debug_league_raw": "",
        "debug_week_raw": "",
        "debug_date_raw": "",
        "debug_location_raw": "",
        "debug_teams_raw": "",
        "eligible_for_processing": False,
        "issues": "",
    }
    issues = []

    sheet_names = []
    try:
        sheet_names = get_sheet_names_safely(excel_path, workbook=workbook)
        result["sheet_count"] = len(sheet_names)
    except Exception as exc:
        issues.append(str(exc))

    if (
        result["sheet_count"] is not None
        and result["sheet_count"] < old_format_sheet_threshold
        and "Spielorte" not in sheet_names
    ):
        result["data_format"] = "data_format_pre_2022"
        old_issues = []
        tabelle_df = None

        try:
            tabelle_df = read_excel_safely(
                excel_path,
                sheet_name="Tabelle",
                header=None,
                workbook=workbook,
                nrows=_ANALYZE_TABELLE_NROWS,
            )
        except Exception:
            old_issues.append("Missing or unreadable 'Tabelle' sheet")

        header_meta = resolve_pre_2022_workbook_metadata(
            excel_path, sheet_names, workbook=workbook
        )
        if header_meta is None:
            old_issues.append("Missing metadata (no Ligabericht or Spielzettel header)")
        else:
            league_raw = header_meta["league_raw"]
            location_raw = header_meta["location_raw"]
            week_raw = header_meta["week_raw"]
            date_raw = header_meta["date_raw"]
            meta_src = header_meta["source"]

            result["debug_league_raw"] = "" if pd.isna(league_raw) else str(league_raw)
            result["debug_location_raw"] = "" if pd.isna(location_raw) else str(location_raw)
            result["debug_week_raw"] = "" if pd.isna(week_raw) else str(week_raw)
            result["debug_date_raw"] = "" if pd.isna(date_raw) else str(date_raw)

            result["league"] = normalize_league_display_to_canonical(league_raw) or normalize_optional_text(league_raw)
            result["location"] = normalize_optional_text(location_raw)
            week_value = parse_week_from_text(week_raw)
            if week_value is not None:
                result["available_weeks"] = str(week_value)
            path_si = infer_season_from_path(excel_path)
            if path_si:
                result["season"] = path_si["season_short"]
                result["season_source"] = "folder_path"
            season_from_sheet = normalize_season_cell_to_short(
                header_meta.get("season_raw") if header_meta else None
            )
            if season_from_sheet and (
                not result.get("season") or _season_from_content_is_uncertain(result.get("season"))
            ):
                result["season"] = season_from_sheet
                result["season_source"] = f"{meta_src}:season"
            date_info = parse_old_format_date(date_raw)
            season_info = path_si or season_label_to_season_info(result.get("season") or "")
            date_info = complete_old_format_date_info(date_info, season_info)
            if not result.get("season"):
                result["season"] = derive_season_from_old_date(date_info)
            result["games_per_week"] = None
            result["degradation_trace"] = (
                f"old_format source={meta_src}, league_raw='{result['debug_league_raw'] or 'missing'}', "
                f"week_raw='{result['debug_week_raw'] or 'missing'}', "
                f"date_raw='{result['debug_date_raw'] or 'missing'}', "
                f"location_raw='{result['debug_location_raw'] or 'missing'}'"
            )

            if not result["league"]:
                old_issues.append(f"Missing league in {meta_src} header")
            if week_value is None:
                old_issues.append(f"Missing week in {meta_src} header")
            if not old_format_date_is_usable(date_info, season_info):
                old_issues.append(f"Missing/invalid date in {meta_src} header")
            if not result["season"]:
                old_issues.append("Could not derive season from date or folder path")
            if not result["location"]:
                old_issues.append(f"Missing location in {meta_src} header")

        team_count = infer_pre_2022_number_of_teams(
            excel_path, tabelle_df=tabelle_df, workbook=workbook
        )
        result["number_of_teams"] = team_count
        result["debug_teams_raw"] = str(team_count) if team_count is not None else ""
        if team_count is None:
            old_issues.append("Missing number of teams (Tabelle and Spielzettel)")

        if not old_format_results_are_valid(excel_path, workbook=workbook):
            old_issues.append("Tagesschnittliste has fewer than 10 valid data rows")

        result["number_of_weeks"] = None  # Computed later across files via max(week)
        if not old_issues:
            result["issues"] = "History file format: 1 week per file"
            result["eligible_for_processing"] = True
        else:
            result["issues"] = "History file format: 1 week per file | " + " | ".join(old_issues)
            result["eligible_for_processing"] = False
        return result

    try:
        spielorte_df = read_excel_safely(
            excel_path,
            sheet_name="Spielorte",
            header=None,
            workbook=workbook,
            nrows=_ANALYZE_SPIELORTE_NROWS,
        )
    except Exception as exc:
        if issues:
            issues.append(f"Missing or unreadable 'Spielorte' sheet: {exc}")
            result["issues"] = " | ".join(issues)
        else:
            result["issues"] = f"Missing or unreadable 'Spielorte' sheet: {exc}"
        return result

    league = None
    league_source = "schluessel_c1"
    try:
        league = extract_league_from_schluessel(excel_path, workbook=workbook)
    except Exception:
        league = None
        league_source = ""
    season, season_source = resolve_with_fallbacks(
        [("spielorte_c18", lambda: normalize_optional_text(get_cell_value(spielorte_df, 17, 2)))]
    )
    if season:
        season = normalize_season_cell_to_short(season)
    teams, teams_source = resolve_with_fallbacks(
        [("spielorte_a21", lambda: parse_metadata_int(get_cell_value(spielorte_df, 20, 0)))]
    )
    weeks, weeks_source = resolve_with_fallbacks(
        [("spielorte_a22", lambda: parse_metadata_int(get_cell_value(spielorte_df, 21, 0)))]
    )
    games_per_week, games_per_week_source = resolve_with_fallbacks(
        [("spielorte_a23", lambda: parse_metadata_int(get_cell_value(spielorte_df, 22, 0)))]
    )

    if _season_from_content_is_uncertain(season):
        path_si = infer_season_from_path(excel_path)
        if path_si:
            season = path_si["season_short"]
            season_source = "path_yyyy_yy"

    result["league"] = league
    result["season"] = season
    result["number_of_teams"] = teams
    result["number_of_weeks"] = weeks
    result["games_per_week"] = games_per_week
    result["league_source"] = league_source or ""
    result["season_source"] = season_source or ""
    result["teams_source"] = teams_source or ""
    result["weeks_source"] = weeks_source or ""
    result["games_per_week_source"] = games_per_week_source or ""
    result["degradation_trace"] = (
        f"league={league_source or 'missing'}; "
        f"season={season_source or 'missing'}; "
        f"teams={teams_source or 'missing'}; "
        f"weeks={weeks_source or 'missing'}; "
        f"games_per_week={games_per_week_source or 'missing'}"
    )

    if not league:
        issues.append("Missing league name in Schlüssel C1")
    if not season:
        issues.append("Missing season in Spielorte C18 and folder path")
    if teams is None:
        issues.append("Missing number of teams in Spielorte A21")
    if weeks is None:
        issues.append("Missing number of weeks in Spielorte A22")
    if games_per_week is None:
        issues.append("Missing games per week in Spielorte A23")

    available_weeks = []
    if weeks is not None and weeks > 0:
        for week in range(1, weeks + 1):
            if week_sheet_has_valid_data(excel_path, week, workbook=workbook):
                available_weeks.append(week)
    elif weeks is not None:
        issues.append("Number of weeks must be > 0")

    if not available_weeks:
        issues.append("No available week sheets with valid data")

    result["available_weeks"] = ",".join(str(week) for week in available_weeks)
    result["eligible_for_processing"] = len(issues) == 0
    result["issues"] = " | ".join(issues)
    return result


def run_analyze_mode(
    excel_files,
    analysis_output=None,
    old_format_sheet_threshold=15,
    skipped_files=None,
    force_reanalyze=False,
):
    """Run analyze mode for all discovered files."""
    skipped_files = skipped_files or []
    analysis_log = load_analysis_log()
    overrides_df = load_extract_overrides()
    analysis_rows = []
    cache_hits = 0
    total_files = len(excel_files)
    for index, file_path in enumerate(excel_files, start=1):
        print(f"[{index}/{total_files}] {file_path}", flush=True)
        row = _analyze_with_cache(
            file_path,
            analysis_log,
            old_format_sheet_threshold=old_format_sheet_threshold,
            force_reanalyze=force_reanalyze,
            overrides_df=overrides_df,
        )
        if row.get("from_cache"):
            cache_hits += 1
        analysis_rows.append(row)
        print_progress_bar(index, total_files, "Analyzing files")
    save_analysis_log(analysis_log)
    analysis_df = pd.DataFrame(analysis_rows)
    if analysis_df.empty:
        analysis_df = pd.DataFrame(
            columns=[
                "file",
                "data_format",
                "league",
                "season",
                "location",
                "sheet_count",
                "number_of_teams",
                "number_of_weeks",
                "games_per_week",
                "available_weeks",
                "eligible_for_processing",
                "issues",
                "league_source",
                "season_source",
                "teams_source",
                "weeks_source",
                "games_per_week_source",
                "debug_league_raw",
                "debug_week_raw",
                "debug_date_raw",
                "debug_location_raw",
                "debug_teams_raw",
                "file_hash",
                "analyzer_version",
                "extractor_version",
                "from_cache",
                "analysis_skip_reason",
                "analysis_reexecute_reason",
                "override_applied",
                "override_reason",
                "override_match_type",
                "override_match_value",
            ]
        )
    display_df = analysis_df.copy()
    if "file" in display_df.columns:
        display_df["file"] = display_df["file"].apply(lambda value: str(value)[-20:])

    print("\nAnalyze Results:")
    display_columns = [
        "file",
        "data_format",
        "league",
        "season",
        "location",
        "sheet_count",
        "number_of_teams",
        "number_of_weeks",
        "games_per_week",
        "available_weeks",
        "eligible_for_processing",
        "issues",
    ]
    print(display_df[display_columns].to_string(index=False))

    if analysis_output:
        output_path = Path(analysis_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_df.to_csv(output_path, sep=";", index=False)
        print(f"\nAnalyze CSV written to: {output_path}")

    eligibility_mask = analysis_df["eligible_for_processing"].fillna(False).astype(bool)
    eligible_files = analysis_df.loc[eligibility_mask, "file"].astype(str).tolist()
    not_eligible_files = analysis_df.loc[~eligibility_mask, "file"].astype(str).tolist()
    eligible_count = len(eligible_files)
    analyzed_count = len(analysis_df)
    not_eligible_count = len(not_eligible_files)
    skipped_count = len(skipped_files)
    total_discovered_count = analyzed_count + skipped_count

    issue_to_files = {}
    for _, row in analysis_df.iterrows():
        issue_text = str(row["issues"]).strip() if pd.notna(row["issues"]) else ""
        if not issue_text:
            issue_text = "No issues"
        issue_to_files.setdefault(issue_text, []).append(str(row["file"]))
    if skipped_files:
        issue_to_files["Skipped (path contains 'Fehlerhaft' or 'Logdatei')"] = [
            str(path) for path in skipped_files
        ]

    print("\nIssues Grouped by Files:")
    for issue_text, files in sorted(issue_to_files.items(), key=lambda item: (item[0] == "No issues", item[0])):
        print(f'\nissue: "{issue_text}"')
        for file_path in files:
            print(f"  - {file_path}")

    print("\nFiles by Category:")
    print("\ncategory: eligible")
    for file_path in eligible_files:
        print(f"  - {file_path}")
    print("\ncategory: not eligible")
    for file_path in not_eligible_files:
        print(f"  - {file_path}")
    print("\ncategory: skipped")
    for file_path in [str(path) for path in skipped_files]:
        print(f"  - {file_path}")

    print("\nFinal Metrics:")
    print(f"  total discovered files: {total_discovered_count}")
    print(f"  analyzed: {analyzed_count}")
    print(f"  cache hits: {cache_hits}")
    print(f"  skipped: {skipped_count}")
    print(f"  eligible: {eligible_count}")
    print(f"  not eligible: {not_eligible_count}")
    if analyzed_count > 0:
        eligible_pct = (eligible_count / analyzed_count) * 100
        not_eligible_pct = (not_eligible_count / analyzed_count) * 100
        print(f"  eligible %: {eligible_pct:.1f}")
        print(f"  not eligible %: {not_eligible_pct:.1f}")

    if not analysis_df.empty and "from_cache" in analysis_df.columns:
        cache_skipped_df = analysis_df[analysis_df["from_cache"] == True]
    else:
        cache_skipped_df = pd.DataFrame()
    if not cache_skipped_df.empty:
        print("\nAnalysis Skips:")
        for row in cache_skipped_df.itertuples(index=False):
            reason = getattr(row, "analysis_skip_reason", "") or "Skipped due to cache reuse"
            print(f"  - {row.file}: {reason}")


def run_convert_legacy_xls_mode(excel_files, skip_existing_xlsx=True):
    """
    Convert legacy .xls files to .xlsx in place via LibreOffice headless.

    By default skips each .xls when a same-stem .xlsx already exists so native or
    good exports (e.g. Ligaprogramme Süd) are not overwritten. Use skip_existing_xlsx=False
    (CLI: --force_convert_xls) to reconvert anyway.
    """
    soffice_binary = shutil.which("soffice")
    if not soffice_binary:
        fallback = Path("C:/Program Files/LibreOffice/program/soffice.exe")
        if fallback.exists():
            soffice_binary = str(fallback)

    if not soffice_binary:
        raise RuntimeError(
            "LibreOffice 'soffice' binary not found. Install LibreOffice or add soffice to PATH."
        )

    xls_files = [file_path for file_path in excel_files if file_path.suffix.lower() == ".xls"]
    if not xls_files:
        print("No .xls files found to convert.")
        return

    converted = 0
    failed = 0
    skipped_existing = 0
    mode_label = "skip existing .xlsx" if skip_existing_xlsx else "overwrite existing .xlsx"
    print(f"Converting {len(xls_files)} legacy .xls file(s) ({mode_label})...")
    for source_file in xls_files:
        target_file = source_file.with_suffix(".xlsx")
        if skip_existing_xlsx and target_file.is_file():
            skipped_existing += 1
            print(f"  skipped (xlsx exists): {source_file}")
            continue
        command = [
            soffice_binary,
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(source_file.parent),
            str(source_file),
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and target_file.exists():
                converted += 1
                print(f"  converted: {source_file} -> {target_file.name}")
            else:
                failed += 1
                stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
                print(f"  failed: {source_file} ({stderr})")
        except Exception as exc:
            failed += 1
            print(f"  failed: {source_file} ({exc})")

    print("\nConversion Summary:")
    print(f"  total xls files: {len(xls_files)}")
    print(f"  skipped (xlsx already present): {skipped_existing}")
    print(f"  converted: {converted}")
    print(f"  failed: {failed}")


def parse_available_weeks(available_weeks_value):
    """Parse comma-separated week list from analysis result."""
    if not available_weeks_value:
        return []
    weeks = []
    for token in str(available_weeks_value).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            weeks.append(int(token))
        except ValueError:
            continue
    return sorted(set(weeks))


def sanitize_filename_component(value):
    """Make a string safe for filename usage."""
    sanitized = re.sub(r'[<>:"/\\|?*]+', "_", str(value).strip())
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized or "unknown"


DEFAULT_PROCESS_OUTPUT_FILE = Path("database/data/historical_league_results.csv")


def _cli_flag_passed(flag: str) -> bool:
    """True if flag appears on the command line (not merely argparse default)."""
    prefix = f"{flag}="
    return flag in sys.argv or any(arg.startswith(prefix) for arg in sys.argv)


def _resolve_cli_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_process_output_paths(args) -> tuple[Path, Path]:
    """Resolve merged output CSV and per-combo CSV directory for process mode."""
    continuous_output_file = _resolve_cli_path(args.output_file)
    if args.output_dir:
        output_dir = _resolve_cli_path(args.output_dir)
    else:
        output_dir = (continuous_output_file.parent / f"{continuous_output_file.stem}_combos").resolve()
    return output_dir, continuous_output_file


def process_scope_cache_key(continuous_output_file: Path) -> str:
    """Cache bucket id for a process run's merged output file."""
    repo_default = (Path(__file__).resolve().parent / DEFAULT_PROCESS_OUTPUT_FILE).resolve()
    if continuous_output_file.resolve() == repo_default:
        return "historical_league_results"
    return f"scope::{sanitize_filename_component(continuous_output_file.stem)}"


def combo_processing_cache_key(process_scope_key: str, season_part: str, league_part: str) -> str:
    """Per league/season cache key; default historical scope keeps legacy key shape."""
    season_league = f"{season_part}::{league_part}"
    if process_scope_key == "historical_league_results":
        return season_league
    return f"{process_scope_key}::{season_part}::{league_part}"


def top_level_subdir_key(file_path: Path, folder_root: Path) -> str:
    """First path segment under folder_root, or _root for files directly in folder_root."""
    folder_root = folder_root.resolve()
    file_path = Path(file_path).resolve()
    try:
        relative = file_path.relative_to(folder_root)
    except ValueError:
        return "_external"
    if len(relative.parts) <= 1:
        return "_root"
    return relative.parts[0]


def _combo_csv_paths_for_eligible(eligible_df: pd.DataFrame, output_dir: Path) -> list[Path]:
    paths = []
    for row in eligible_df.itertuples(index=False):
        season_value = getattr(row, "season", None)
        league_value = getattr(row, "league", None)
        if pd.isna(season_value) or pd.isna(league_value):
            continue
        season_part = sanitize_filename_component(season_value)
        league_part = sanitize_filename_component(league_value)
        paths.append(output_dir / f"{season_part} {league_part}.csv")
    return sorted(set(paths))


def _merge_combo_csvs(
    combo_csv_paths: list[Path],
    *,
    continuous_output_file: Path,
    apply_team_numbering: bool = True,
) -> pd.DataFrame | None:
    merged_frames = []
    missing = []
    for csv_file in combo_csv_paths:
        if csv_file.is_file():
            try:
                merged_frames.append(pd.read_csv(csv_file, sep=";", dtype=str))
            except Exception as exc:
                print(f"Warning: failed to read combo CSV during merge: {csv_file} ({exc})")
        else:
            missing.append(csv_file)

    if not merged_frames:
        if missing:
            print("Missing combo CSVs:")
            for missing_file in missing:
                print(f"  - {missing_file}")
        return None

    merged_df = pd.concat(merged_frames, ignore_index=True)
    merged_df = normalize_extracted_dataframe(merged_df)
    if apply_team_numbering:
        merged_df = normalize_team_numbering_dataframe(merged_df, overrides_df=load_team_number_overrides())
    merged_df = merged_df.sort_values(
        by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"],
        key=lambda col: col.astype(str),
    )
    continuous_output_file.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(continuous_output_file, sep=";", index=False)
    if missing:
        print("\nCombo CSVs missing (excluded from merge):")
        for missing_file in missing:
            print(f"  - {missing_file}")
    return merged_df


def process_eligible_combos(
    eligible_df: pd.DataFrame,
    *,
    output_dir: Path,
    team_sheet_prefix: str,
    season_sheet: str,
    combo_cache: dict | None,
    process_scope_key: str,
    force_reanalyze: bool,
    log: Callable[[str], None] = print,
) -> tuple[list[tuple[Path, int]], int, list[Path]]:
    """
    Extract all season/league combos for eligible files into output_dir.

    When combo_cache is None, combo processing cache is skipped (for parallel workers).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files: list[tuple[Path, int]] = []
    skipped_combo_count = 0
    combo_keys = (
        eligible_df[["Season", "League"]]
        if "Season" in eligible_df.columns and "League" in eligible_df.columns
        else eligible_df[["season", "league"]].rename(columns={"season": "Season", "league": "League"})
    )
    combo_count = len(combo_keys.drop_duplicates())
    processed_combos = 0
    use_cache = combo_cache is not None

    for (season_value, league_value), combo_df in eligible_df.groupby(["season", "league"], dropna=False):
        processed_combos += 1
        season_part = sanitize_filename_component(season_value if pd.notna(season_value) else "unknown_season")
        league_part = sanitize_filename_component(league_value if pd.notna(league_value) else "unknown_league")
        combo_output_file = output_dir / f"{season_part} {league_part}.csv"
        combo_cache_key = combo_processing_cache_key(process_scope_key, season_part, league_part)
        combo_signature = _build_combo_processing_signature(
            combo_df,
            season_value=season_value,
            league_value=league_value,
        )

        cached_combo = (combo_cache or {}).get(combo_cache_key, {})
        combo_cache_hit = (
            use_cache
            and not force_reanalyze
            and isinstance(cached_combo, dict)
            and cached_combo.get("combo_signature") == combo_signature
            and cached_combo.get("analyzer_version") == ANALYZER_VERSION
            and cached_combo.get("processor_version") == PROCESSOR_VERSION
            and combo_output_file.is_file()
        )

        if combo_cache_hit:
            current_combo_hash = compute_file_sha256(combo_output_file)
            if current_combo_hash == cached_combo.get("output_hash"):
                skipped_combo_count += 1
                combo_cache[combo_cache_key] = {
                    **cached_combo,
                    "last_skip_reason": "Skipped due to unchanged combo signature + versions + output hash",
                    "last_skipped_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                }
                print_progress_bar(processed_combos, combo_count, "Processing combos")
                continue

        if use_cache:
            combo_criteria = {
                "force_reanalyze_disabled": not force_reanalyze,
                "has_cached_combo": isinstance(cached_combo, dict),
                "combo_signature_match": cached_combo.get("combo_signature") == combo_signature,
                "analyzer_version_match": cached_combo.get("analyzer_version") == ANALYZER_VERSION,
                "processor_version_match": cached_combo.get("processor_version") == PROCESSOR_VERSION,
                "output_file_exists": combo_output_file.is_file(),
            }
            if force_reanalyze:
                combo_reexecute_reason = "forced via --force_reanalyze"
            else:
                failed_combo_criteria = [name for name, ok in combo_criteria.items() if not ok]
                combo_reexecute_reason = (
                    "cache miss: " + ", ".join(failed_combo_criteria)
                    if failed_combo_criteria
                    else "output_hash_mismatch"
                )
            log(f"  reprocess combo [{season_part} | {league_part}] -> {combo_reexecute_reason}")

        combo_output_df = pd.DataFrame()
        total_files_in_combo = len(combo_df)
        for row in combo_df.itertuples(index=False):
            input_file = Path(row.file)
            data_format = getattr(row, "data_format", "data_format_post_2022")
            available_weeks = parse_available_weeks(row.available_weeks)
            if not available_weeks:
                continue

            for week in available_weeks:
                global dict_of_match_numbers
                dict_of_match_numbers = {}
                csv_data = []
                if data_format == "data_format_pre_2022":
                    with redirect_stdout(io.StringIO()):
                        csv_data = extract_pre_2022_file(
                            str(input_file),
                            league=row.league,
                            season=row.season,
                            week=week,
                            location=getattr(row, "location", None) or "Unknown",
                            players_per_team=int(getattr(row, "players_per_team", None) or 4),
                            number_of_teams=getattr(row, "number_of_teams", None),
                        )
                else:
                    with redirect_stdout(io.StringIO()):
                        result = extract_excel_data(
                            str(input_file),
                            team_sheet_prefix + str(week),
                            season_sheet,
                        )
                    if result is None:
                        continue
                    df, season_info, full_date = result
                    placeholder_season = season_info.get("season_short") in (None, "??/??") or season_info.get(
                        "year1"
                    ) in (None, "????")

                    merged_season = None
                    if getattr(row, "season", None) and not _season_from_content_is_uncertain(row.season):
                        merged_season = season_label_to_season_info(row.season)
                    if merged_season is None and placeholder_season:
                        merged_season = infer_season_from_path(input_file)
                    if merged_season is not None:
                        season_info = dict(merged_season)
                        with redirect_stdout(io.StringIO()):
                            recomputed_date_info = extract_date_info(df)
                        full_date = combine_season_and_date(season_info, recomputed_date_info)

                    with redirect_stdout(io.StringIO()):
                        csv_data = parse_teams(
                            df,
                            season_info,
                            full_date,
                            league_override=row.league,
                            week_override=week,
                            max_games_per_week=row.games_per_week,
                        )
                if csv_data:
                    temp_df = pd.DataFrame(csv_data)
                    combo_output_df = pd.concat([combo_output_df, temp_df], ignore_index=True)

        if not combo_output_df.empty:
            combo_output_df = normalize_extracted_dataframe(combo_output_df)
            combo_output_df = combo_output_df.sort_values(
                by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"]
            )
            combo_output_df.to_csv(combo_output_file, sep=";", index=False)
            combo_hash = compute_file_sha256(combo_output_file)
            created_files.append((combo_output_file, len(combo_output_df)))
            if use_cache:
                combo_cache[combo_cache_key] = {
                    "combo_signature": combo_signature,
                    "analyzer_version": ANALYZER_VERSION,
                    "processor_version": PROCESSOR_VERSION,
                    "output_file": str(combo_output_file.resolve()),
                    "output_hash": combo_hash,
                    "season": str(season_value),
                    "league": str(league_value),
                    "last_processed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "eligible_file_count": int(total_files_in_combo),
                    "last_skip_reason": "",
                    "last_reexecute_reason": combo_reexecute_reason if use_cache else "",
                }

        print_progress_bar(processed_combos, combo_count, "Processing combos")

    target_output_files = _combo_csv_paths_for_eligible(eligible_df, output_dir)
    return created_files, skipped_combo_count, target_output_files


def _process_subdir_worker(job: dict) -> dict:
    """Process one top-level subfolder (multiprocessing entry point)."""
    log_lines: list[str] = []

    def log(message: str) -> None:
        log_lines.append(str(message))

    subdir_key = str(job["subdir_key"])
    try:
        eligible_df = pd.DataFrame(job["eligible_records"])
        combo_output_dir = Path(job["combo_output_dir"])
        partial_output_csv = Path(job["partial_output_csv"])
        log(f"subdir={subdir_key} files={len(eligible_df)} combo_dir={combo_output_dir}")

        process_scope_key = str(job["process_scope_key"])
        created_files, _, target_output_files = process_eligible_combos(
            eligible_df,
            output_dir=combo_output_dir,
            team_sheet_prefix=str(job["team_sheet_prefix"]),
            season_sheet=str(job["season_sheet"]),
            combo_cache=None,
            process_scope_key=process_scope_key,
            force_reanalyze=True,
            log=log,
        )
        for combo_path, row_count in created_files:
            log(f"  wrote {combo_path} ({row_count} rows)")

        merged_df = _merge_combo_csvs(
            target_output_files,
            continuous_output_file=partial_output_csv,
            apply_team_numbering=False,
        )
        if merged_df is None:
            return {
                "subdir_key": subdir_key,
                "ok": False,
                "error": "no combo CSVs produced",
                "partial_output_csv": "",
                "row_count": 0,
            }
        log(f"partial {partial_output_csv} ({len(merged_df)} rows)")
        return {
            "subdir_key": subdir_key,
            "ok": True,
            "error": "",
            "partial_output_csv": str(partial_output_csv.resolve()),
            "row_count": int(len(merged_df)),
        }
    except Exception as exc:
        log(f"ERROR: {exc}")
        return {
            "subdir_key": subdir_key,
            "ok": False,
            "error": str(exc),
            "partial_output_csv": "",
            "row_count": 0,
        }
    finally:
        log_path = Path(job["log_path"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def _run_parallel_subdir_processing(
    eligible_df: pd.DataFrame,
    *,
    folder_root: Path,
    output_dir: Path,
    continuous_output_file: Path,
    process_scope_key: str,
    args,
) -> tuple[pd.DataFrame | None, list[Path]]:
    eligible_df = eligible_df.copy()
    eligible_df["__subdir"] = eligible_df["file"].map(
        lambda file_value: top_level_subdir_key(Path(file_value), folder_root)
    )
    subdir_groups = list(eligible_df.groupby("__subdir", sort=True))
    partials_dir = continuous_output_file.parent / f"{continuous_output_file.stem}_partials"
    logs_dir = continuous_output_file.parent / f"{continuous_output_file.stem}_parallel_logs"
    partials_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    jobs = []
    for subdir_key, subdir_df in subdir_groups:
        subdir_df = subdir_df.drop(columns=["__subdir"])
        safe_subdir = sanitize_filename_component(subdir_key)
        jobs.append(
            {
                "subdir_key": subdir_key,
                "eligible_records": subdir_df.to_dict(orient="records"),
                "combo_output_dir": str((output_dir / safe_subdir).resolve()),
                "partial_output_csv": str((partials_dir / f"{safe_subdir}.csv").resolve()),
                "log_path": str((logs_dir / f"{safe_subdir}.log").resolve()),
                "team_sheet_prefix": args.team_sheet_prefix,
                "season_sheet": args.season_sheet,
                "process_scope_key": process_scope_key,
            }
        )

    max_workers = min(len(jobs), os.cpu_count() or 4)
    print(
        f"Parallel process: {len(jobs)} subdir job(s), max_workers={max_workers}, "
        f"partials={partials_dir}, logs={logs_dir}"
    )

    partial_paths: list[Path] = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_subdir_worker, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            subdir_key = result.get("subdir_key", "?")
            if result.get("ok"):
                partial_path = Path(result["partial_output_csv"])
                partial_paths.append(partial_path)
                print(f"  done {subdir_key}: {partial_path} ({result.get('row_count', 0)} rows)")
            else:
                print(f"  FAILED {subdir_key}: {result.get('error', 'unknown error')}")

    if not partial_paths:
        print("Parallel process: no partial CSVs produced.")
        return None, []

    merged_frames = []
    for partial_path in sorted(partial_paths):
        try:
            merged_frames.append(pd.read_csv(partial_path, sep=";", dtype=str))
        except Exception as exc:
            print(f"Warning: failed to read partial CSV {partial_path}: {exc}")

    if not merged_frames:
        return None, partial_paths

    merged_df = pd.concat(merged_frames, ignore_index=True)
    merged_df = normalize_extracted_dataframe(merged_df)
    merged_df = normalize_team_numbering_dataframe(merged_df, overrides_df=load_team_number_overrides())
    merged_df = merged_df.sort_values(
        by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"],
        key=lambda col: col.astype(str),
    )
    return merged_df, partial_paths


def run_process_mode_with_analysis(excel_files, args):
    """Analyze first, then process eligible post-2022 and pre-2022 files."""
    reset_team_normalization_stats()
    analysis_log = load_analysis_log()
    overrides_df = load_extract_overrides()
    overrides_manifest_fingerprint = compute_overrides_manifest_fingerprint(overrides_df)
    analysis_rows = []
    cache_hits = 0
    total_analysis_files = len(excel_files)
    for index, file_path in enumerate(excel_files, start=1):
        print(f"[{index}/{total_analysis_files}] {file_path}", flush=True)
        row = _analyze_with_cache(
            file_path,
            analysis_log,
            old_format_sheet_threshold=args.old_format_sheet_threshold,
            force_reanalyze=args.force_reanalyze,
            overrides_df=overrides_df,
        )
        if row.get("from_cache"):
            cache_hits += 1
        analysis_rows.append(row)
        print_progress_bar(index, total_analysis_files, "Analyzing files")
    save_analysis_log(analysis_log)
    analysis_df = pd.DataFrame(analysis_rows)
    if analysis_df.empty:
        print("No files available for processing.")
        return

    unreadable_mask = analysis_df["issues"].fillna("").astype(str).str.startswith(
        "Workbook could not be analyzed:"
    )
    unreadable_count = int(unreadable_mask.sum())
    if unreadable_count:
        print(f"\nAnalyze: {unreadable_count} file(s) could not be opened (skipped for processing):")
        for file_path in analysis_df.loc[unreadable_mask, "file"].astype(str):
            print(f"  - {file_path}")

    if args.analysis_output:
        output_path = Path(args.analysis_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_df.to_csv(output_path, sep=";", index=False)
        print(f"Process-mode analysis CSV written to: {output_path}")

    eligible_df = analysis_df[analysis_df["eligible_for_processing"] == True].copy()
    eligible_post_df = eligible_df[eligible_df["data_format"] == "data_format_post_2022"].copy()
    eligible_pre_df = eligible_df[eligible_df["data_format"] == "data_format_pre_2022"].copy()

    print(
        f"Eligible files for processing: {len(eligible_df)}/{len(analysis_df)} "
        f"(post_2022={len(eligible_post_df)}, pre_2022={len(eligible_pre_df)}, cache hits: {cache_hits})"
    )
    if eligible_df.empty:
        print("No eligible files to process.")
        return

    output_dir, continuous_output_file = resolve_process_output_paths(args)
    process_scope_key = process_scope_cache_key(continuous_output_file)
    process_cache = analysis_log.setdefault("processing_cache", {})
    combo_cache = process_cache.setdefault("league_season_outputs", {})

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Process merged output: {continuous_output_file}")
    print(f"Process combo CSV dir: {output_dir} (scope={process_scope_key})")

    folder_root = Path(args.folder).resolve() if args.folder else None
    use_parallel_subdirs = (
        folder_root is not None
        and not args.no_parallel_subdirs
        and len({top_level_subdir_key(Path(file_value), folder_root) for file_value in eligible_df["file"]}) > 1
    )

    created_files: list[tuple[Path, int]] = []
    skipped_combo_count = 0
    target_output_files: list[Path] = []

    if use_parallel_subdirs:
        merged_df, partial_paths = _run_parallel_subdir_processing(
            eligible_df,
            folder_root=folder_root,
            output_dir=output_dir,
            continuous_output_file=continuous_output_file,
            process_scope_key=process_scope_key,
            args=args,
        )
        if merged_df is None:
            return
        continuous_output_file.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(continuous_output_file, sep=";", index=False)
        target_output_files = partial_paths
    else:
        created_files, skipped_combo_count, target_output_files = process_eligible_combos(
            eligible_df,
            output_dir=output_dir,
            team_sheet_prefix=args.team_sheet_prefix,
            season_sheet=args.season_sheet,
            combo_cache=combo_cache,
            process_scope_key=process_scope_key,
            force_reanalyze=args.force_reanalyze,
        )
        merged_df = _merge_combo_csvs(
            target_output_files,
            continuous_output_file=continuous_output_file,
            apply_team_numbering=True,
        )
        if merged_df is None:
            print("No data extracted and no existing target CSVs found for eligible process scope.")
            return
    output_hash = compute_file_sha256(continuous_output_file)
    export_unique_team_names_after_merge(merged_df)

    scope_signature = hashlib.sha256(
        "|".join(sorted(eligible_df["file"].astype(str))).encode("utf-8")
    ).hexdigest()
    process_cache[process_scope_key] = {
        "scope_signature": scope_signature,
        "output_file": str(continuous_output_file.resolve()),
        "combo_output_dir": str(output_dir.resolve()),
        "output_hash": output_hash,
        "last_processed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "eligible_count": int(len(eligible_df)),
        "combo_cache_entries": int(len(combo_cache)),
        "skipped_combo_count": int(skipped_combo_count),
        "parallel_subdirs": bool(use_parallel_subdirs),
    }
    save_analysis_log(analysis_log)

    if created_files:
        print("\nCreated combo CSV files:")
        for output_file, row_count in created_files:
            print(f"  - {output_file} ({row_count} rows)")
    print(f"  - {continuous_output_file} ({len(merged_df)} rows, continuous, hash={output_hash[:12]}...)")

    summary_df = (
        merged_df.groupby(["League", "Season"], dropna=False)["Week"]
        .apply(lambda weeks: ",".join(str(w) for w in sorted({str(w) for w in weeks if pd.notna(w)})))
        .reset_index(name="extracted_weeks")
    )
    summary_df = summary_df.sort_values(
        by=["League", "Season"],
        key=lambda col: col.astype(str),
    ).reset_index(drop=True)
    print("\nExtraction Summary:")
    for row in summary_df.itertuples(index=False):
        league_label = row.League if pd.notna(row.League) else "unknown"
        season_label = row.Season if pd.notna(row.Season) else "unknown"
        print(
            f"  league={str(league_label).ljust(8)}, "
            f"season={season_label}, "
            f"extracted_weeks={row.extracted_weeks or 'none'}"
        )
    print_team_normalization_summary()


def _normalize_merged_extract_frame(merged_df: pd.DataFrame) -> pd.DataFrame:
    """Apply league/team normalization and standard sort order to extracted rows."""
    merged_df = normalize_extracted_dataframe(merged_df)
    merged_df = normalize_team_numbering_dataframe(merged_df, overrides_df=load_team_number_overrides())
    return merged_df.sort_values(
        by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"],
        key=lambda col: col.astype(str),
    )


def run_normalize_data_mode(args):
    """Rebuild normalized output from --input CSV(s) or existing combo CSVs in the processing cache."""
    reset_team_normalization_stats()

    if args.input_files:
        input_paths = [_resolve_cli_path(path_value) for path_value in args.input_files]
        merged_frames = []
        for csv_file in input_paths:
            try:
                merged_frames.append(pd.read_csv(csv_file, sep=";", dtype=str))
            except Exception as exc:
                raise ValueError(f"Failed to read input CSV {csv_file}: {exc}") from exc

        merged_df = _normalize_merged_extract_frame(pd.concat(merged_frames, ignore_index=True))
        if len(input_paths) > 1 or _cli_flag_passed("--output-file"):
            continuous_output_file = _resolve_cli_path(args.output_file)
        else:
            continuous_output_file = input_paths[0]

        continuous_output_file.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(continuous_output_file, sep=";", index=False)
        output_hash = compute_file_sha256(continuous_output_file)
        unique_names_path = continuous_output_file.parent / f"{continuous_output_file.stem}_unique_teams.csv"
        export_unique_team_names_after_merge(merged_df, unique_names_path)

        print(
            f"\nnormalize_data: normalized {len(input_paths)} input file(s) -> {continuous_output_file} "
            f"({len(merged_df)} rows, hash={output_hash[:12]}...)"
        )
        for input_path in input_paths:
            print(f"  input: {input_path}")
        print_team_normalization_summary()
        return

    analysis_log = load_analysis_log()
    process_cache = analysis_log.setdefault("processing_cache", {})
    combo_cache = process_cache.setdefault("league_season_outputs", {})

    target_output_files = []
    for combo_key, cached_combo in combo_cache.items():
        if not isinstance(cached_combo, dict):
            continue
        output_file = str(cached_combo.get("output_file") or "").strip()
        if output_file:
            target_output_files.append(Path(output_file))
            continue
        season_part, _, league_part = str(combo_key).partition("::")
        if season_part and league_part:
            target_output_files.append(Path("C:/tmp/csvs") / f"{season_part} {league_part}.csv")
    target_output_files = sorted(set(target_output_files))

    if not target_output_files:
        print("normalize_data: no combo outputs registered in processing cache.")
        return

    merged_frames = []
    missing_target_outputs = []
    for csv_file in target_output_files:
        if csv_file.is_file():
            try:
                merged_frames.append(pd.read_csv(csv_file, sep=";", dtype=str))
            except Exception as exc:
                print(f"Warning: failed to read target CSV during normalize_data merge: {csv_file} ({exc})")
        else:
            missing_target_outputs.append(csv_file)

    if not merged_frames:
        print("normalize_data: no existing combo CSVs found to merge.")
        if missing_target_outputs:
            print("Missing target CSVs:")
            for missing_file in missing_target_outputs:
                print(f"  - {missing_file}")
        return

    merged_df = _normalize_merged_extract_frame(pd.concat(merged_frames, ignore_index=True))

    continuous_output_file = _resolve_cli_path(args.output_file)
    continuous_output_file.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(continuous_output_file, sep=";", index=False)
    output_hash = compute_file_sha256(continuous_output_file)
    export_unique_team_names_after_merge(merged_df)

    process_cache["historical_league_results"] = {
        "scope_signature": hashlib.sha256(
            "|".join(str(p.resolve()) for p in target_output_files).encode("utf-8")
        ).hexdigest()
        if target_output_files
        else "",
        "output_file": str(continuous_output_file.resolve()),
        "output_hash": output_hash,
        "last_processed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "eligible_count": int(len(target_output_files)),
        "combo_cache_entries": int(len(combo_cache)),
        "skipped_combo_count": 0,
        "mode": "normalize_data",
    }
    save_analysis_log(analysis_log)

    if missing_target_outputs:
        print("\nnormalize_data: missing combo CSVs (excluded from merge):")
        for missing_file in missing_target_outputs:
            print(f"  - {missing_file}")

    print(
        f"\nnormalize_data: rebuilt {continuous_output_file} "
        f"({len(merged_df)} rows, hash={output_hash[:12]}...)"
    )
    print_team_normalization_summary()


if __name__ == "__main__":
    print("Starting Excel data extraction...")

    try:
        args = parse_args()
        validate_args(args)
    except ValueError as error:
        print(f"Argument error: {error}")
        raise SystemExit(2) from error

    print(f"Mode: {args.mode}")
    if args.mode == "normalize_data":
        run_normalize_data_mode(args)
        raise SystemExit(0)

    excel_files, skipped_discovery_files = discover_excel_files(args)
    if args.mode == "convert_legacy_xls":
        xls_candidates = [path for path in excel_files if path.suffix.lower() == ".xls"]
        print(f"Excel .xls files discovered: {len(xls_candidates)} (of {len(excel_files)} total workbooks)")
        run_convert_legacy_xls_mode(
            excel_files,
            skip_existing_xlsx=not args.force_convert_xls,
        )
        raise SystemExit(0)

    excel_files = dedupe_xls_when_xlsx_present(excel_files)
    excel_files = filter_xls_for_mode(excel_files, args.mode, args.skip_xls)
    if not excel_files and not (args.mode == "analyze" and skipped_discovery_files):
        print("No Excel files found for given input.")
        raise SystemExit(1)

    print(f"Excel files discovered: {len(excel_files)}")
    for file_path in excel_files:
        print(f"  - {file_path}")

    if args.mode == "analyze":
        run_analyze_mode(
            excel_files,
            args.analysis_output,
            old_format_sheet_threshold=args.old_format_sheet_threshold,
            skipped_files=skipped_discovery_files,
            force_reanalyze=args.force_reanalyze,
        )
        raise SystemExit(0)

    run_process_mode_with_analysis(excel_files, args)
    