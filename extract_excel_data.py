#!/usr/bin/env python3
"""
Script to extract data from BYL_Maenner-5-6.xlsx and map it to the existing CSV format.
Based on correct understanding: 9 teams, 30 rows each, 4 positions, up to 3 players per position.
"""

import pandas as pd
import numpy as np
from datetime import datetime, UTC
import re
import argparse
import hashlib
import json
from pathlib import Path
import warnings
import shutil
import subprocess
import io
from typing import Dict
from contextlib import redirect_stdout


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
ANALYZER_VERSION = "analyzer-v1.1.0"
EXTRACTOR_VERSION = "extractor-v1.1.0"
PROCESSOR_VERSION = "processor-v1.1.0"


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


def find_matching_override(overrides_df: pd.DataFrame, file_path: Path, file_hash: str):
    """
    Return first matching override row dict and deterministic fingerprint.
    Match precedence: file_hash -> exact_path -> path_regex.
    """
    if overrides_df is None or overrides_df.empty:
        return None, ""

    file_str = str(file_path.resolve())

    def _iter_matches(match_type: str):
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
        for row in _iter_matches(match_type):
            row_dict = {str(k): str(v) for k, v in row.to_dict().items()}
            fingerprint = hashlib.sha256(
                json.dumps(row_dict, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            return row_dict, fingerprint

    return None, ""


def apply_override_to_analysis_result(result: dict, override_row: dict):
    """Mutate analysis result by override rule; attach audit metadata."""
    if not override_row:
        result["override_applied"] = False
        result["override_reason"] = ""
        return result

    reason = (override_row.get("reason") or "").strip()
    exclude_file = _parse_bool(override_row.get("exclude_file"))
    force_season = (override_row.get("force_season") or "").strip()
    force_league = (override_row.get("force_league") or "").strip()
    force_available_weeks = (override_row.get("force_available_weeks") or "").strip()

    if force_season:
        result["season"] = force_season
        result["season_source"] = "override_manifest"
    if force_league:
        result["league"] = force_league
        result["league_source"] = "override_manifest"
    if force_available_weeks:
        result["available_weeks"] = force_available_weeks
        result["weeks_source"] = "override_manifest"

    if exclude_file:
        result["eligible_for_processing"] = False
        issue_text = str(result.get("issues") or "").strip()
        exclude_msg = "Excluded by override manifest"
        result["issues"] = f"{issue_text} | {exclude_msg}".strip(" |")

    result["override_applied"] = True
    result["override_reason"] = reason
    result["override_match_type"] = (override_row.get("match_type") or "").strip()
    result["override_match_value"] = (override_row.get("match_value") or "").strip()
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
    override_row, override_fingerprint = find_matching_override(overrides_df, file_path, file_hash)
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
    cached_threshold_raw = cached.get("old_format_sheet_threshold")
    try:
        cached_threshold = int(cached_threshold_raw) if cached_threshold_raw is not None else None
    except (TypeError, ValueError):
        cached_threshold = None

    criteria = {
        "has_cached_result": isinstance(cached_result, dict),
        "file_hash_match": cached_file_hash == file_hash,
        "analyzer_version_match": cached_analyzer_version == ANALYZER_VERSION,
        "threshold_match": cached_threshold == old_format_sheet_threshold,
        "override_fingerprint_match": cached_override_fingerprint == override_fingerprint,
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
        result = analyze_excel_file(file_path, old_format_sheet_threshold=old_format_sheet_threshold)
        result["from_cache"] = False
        result["analysis_skip_reason"] = ""
        failed_criteria = [name for name, ok in criteria.items() if not ok]
        if force_reanalyze:
            result["analysis_reexecute_reason"] = "forced via --force_reanalyze"
        elif failed_criteria:
            result["analysis_reexecute_reason"] = "cache miss: " + ", ".join(failed_criteria)
        else:
            result["analysis_reexecute_reason"] = "cache miss: unknown"
    result = apply_override_to_analysis_result(result, override_row)

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
    """Load (id, long_name) tuples from relational league_mapping.csv."""
    global _LEAGUE_MAPPING_CACHE
    if _LEAGUE_MAPPING_CACHE is not None:
        return _LEAGUE_MAPPING_CACHE
    rows = []
    if not _LEAGUE_MAPPING_PATH.is_file():
        _LEAGUE_MAPPING_CACHE = ([], [], set())
        return _LEAGUE_MAPPING_CACHE

    mapping_df = pd.read_csv(_LEAGUE_MAPPING_PATH, encoding="utf-8")
    seen_ids = set()
    for rec in mapping_df.itertuples(index=False):
        lid = normalize_optional_text(getattr(rec, "id", None))
        lng = normalize_optional_text(getattr(rec, "long_name", None))
        if lid and lng:
            rows.append((lid, lng))
            seen_ids.add(lid.lower())
    male = [(lid, lng) for lid, lng in rows if not _is_female_league_id(lid)]
    female = [(lid, lng) for lid, lng in rows if _is_female_league_id(lid)]
    _LEAGUE_MAPPING_CACHE = (male, female, seen_ids)
    return _LEAGUE_MAPPING_CACHE


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
    for col in ["Team", "Opponent"]:
        if col in normalized.columns:
            normalized[col] = normalized[col].apply(normalize_team_name)
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


def _detect_league_gender_bias(raw: str):
    """Return 'female', 'male', or 'neutral' from explicit gender wording."""
    lc = raw.lower()
    has_frauen_or_damen = bool(re.search(r"\b(frauen|damen)\b", lc, re.IGNORECASE))
    has_herren_or_maenner = bool(re.search(r"\b(herren|männer|maenner)\b", lc, re.IGNORECASE))
    if has_frauen_or_damen and not has_herren_or_maenner:
        return "female"
    if has_herren_or_maenner and not has_frauen_or_damen:
        return "male"
    if has_frauen_or_damen and has_herren_or_maenner:
        return "neutral"
    return "neutral"


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


def _match_candidate_to_mapping_pool(candidate: str, pool):
    """Longest-long_name-first match against candidate substring rules."""
    if not candidate or not pool:
        return None
    cand = _squish_league_text(candidate)
    best_match = None
    best_long_len = -1
    for league_id, long_name in sorted(pool, key=lambda item: len(item[1]), reverse=True):
        ln = _squish_league_text(long_name)
        if not ln:
            continue
        if cand == ln or ln in cand or cand in ln:
            if len(ln) > best_long_len:
                best_long_len = len(ln)
                best_match = league_id
    return best_match


def normalize_league_display_to_canonical(raw_league_display):
    """Map verbose league titles to canonical IDs from relational_csv/league_mapping.csv."""
    text = normalize_optional_text(raw_league_display)
    if not text:
        return None

    cleaned = clean_league_name(text)
    if not cleaned:
        return None

    cleaned = expand_league_region_shorthand(cleaned)

    male_rows, female_rows, known_ids = _load_league_mapping()
    if not male_rows:
        return cleaned

    clean_lower = cleaned.strip().lower()
    if clean_lower in known_ids:
        for lid, _ in male_rows + female_rows:
            if lid.lower() == clean_lower:
                return lid
        return cleaned

    gender = _detect_league_gender_bias(cleaned)
    lc_full = _squish_league_text(cleaned)
    lc_unify_female = re.sub(r"\bfrauen\b", "damen", lc_full, flags=re.IGNORECASE)
    lc_no_male = re.sub(r"\b(herren|männer|maenner)\b", " ", lc_unify_female, flags=re.IGNORECASE)
    lc_no_male = re.sub(r"\s+", " ", lc_no_male).strip()
    lc_no_gender_words = re.sub(r"\b(herren|männer|maenner|frauen|damen)\b", " ", lc_full, flags=re.IGNORECASE)
    lc_no_gender_words = re.sub(r"\s+", " ", lc_no_gender_words).strip()

    if gender == "female":
        hit = _match_candidate_to_mapping_pool(lc_unify_female, female_rows)
        if hit:
            return hit
        hit = _match_candidate_to_mapping_pool(lc_no_male, female_rows)
        if hit:
            return hit

    if gender == "male":
        hit = _match_candidate_to_mapping_pool(lc_no_male, male_rows)
        if hit:
            return hit

    if gender == "neutral":
        hit = _match_candidate_to_mapping_pool(lc_no_gender_words, male_rows)
        if hit:
            return hit

    if gender != "female":
        hit = _match_candidate_to_mapping_pool(lc_unify_female, female_rows)
        if hit:
            return hit

    return cleaned


def read_excel_safely(excel_file, sheet_name, header=None):
    """Read worksheet with format-aware engine fallbacks and clean warnings."""
    excel_path = Path(excel_file)
    suffix = excel_path.suffix.lower()
    engine_candidates = {
        ".xls": [None, "xlrd", "calamine"],
        ".xlsx": [None, "openpyxl", "calamine"],
        ".xlsm": [None, "openpyxl", "calamine"],
        ".xlsb": [None, "pyxlsb", "calamine"],
    }.get(suffix, [None, "openpyxl", "calamine", "xlrd"])

    errors = []
    for engine in engine_candidates:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"Print area cannot be set to Defined name: .*",
                    category=UserWarning,
                    module=r"openpyxl\.reader\.workbook",
                )
                kwargs = {"sheet_name": sheet_name, "header": header}
                if engine is not None:
                    kwargs["engine"] = engine
                return pd.read_excel(excel_file, **kwargs)
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


def get_sheet_names_safely(excel_file):
    """Get worksheet names with format-aware engine fallbacks."""
    excel_path = Path(excel_file)
    suffix = excel_path.suffix.lower()
    engine_candidates = {
        ".xls": [None, "xlrd", "calamine"],
        ".xlsx": [None, "openpyxl", "calamine"],
        ".xlsm": [None, "openpyxl", "calamine"],
        ".xlsb": [None, "pyxlsb", "calamine"],
    }.get(suffix, [None, "openpyxl", "calamine", "xlrd"])

    errors = []
    for engine in engine_candidates:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"Print area cannot be set to Defined name: .*",
                    category=UserWarning,
                    module=r"openpyxl\.reader\.workbook",
                )
                kwargs = {}
                if engine is not None:
                    kwargs["engine"] = engine
                with pd.ExcelFile(excel_file, **kwargs) as workbook:
                    return list(workbook.sheet_names)
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
        segments.append(current.name.replace(" ", ""))
        current = current.parent

    for seg in segments:
        match = pattern.search(seg)
        if match:
            info = candidate_from_match(match)
            if info:
                return info

    for match in pattern.finditer(path_blob):
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


def combine_season_and_date(season_info, date_info):
    """Combine season and date information to create full date."""
    try:
        day = date_info['day']
        month = int(date_info['month'])
        year1 = season_info['year1']
        year2 = season_info['year2']
        
        # Determine which year to use based on month
        if month >= 9:
            year = year1  # Use first year for months 9-12
        else:
            year = year2  # Use second year for months 1-8
        
        # Create full date in YYYY-MM-DD format
        full_date = f"{year}-{month:02d}-{day}"
        return full_date
        
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
        "--output-file",
        default="database/data/bowling_ergebnisse_real_2025_new.csv",
        help="Output CSV path for process mode.",
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


def extract_league_from_schluessel(excel_file):
    """Read league name from default location: Schlüssel!C1."""
    schluessel_df = read_excel_safely(excel_file, sheet_name="Schlüssel", header=None)
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


def week_sheet_has_valid_data(excel_file, week_number):
    """Check if Schnitt{week_number} has at least 10 data rows in columns A..G."""
    possible_sheet_names = [f"Schnitt#{week_number}", f"Schnitt{week_number}"]
    week_df = None
    for sheet_name in possible_sheet_names:
        try:
            week_df = read_excel_safely(excel_file, sheet_name=sheet_name, header=None)
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
    """Parse old format date strings like '28./29.9.19' or '8./9.2.20'."""
    text = normalize_optional_text(value)
    if not text:
        return None
    # Find all date-like tokens and use the last one (usually main match day).
    matches = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text)
    if not matches:
        return None
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


def old_format_results_are_valid(excel_file):
    """Validate old-format result presence in Tagesschnittliste."""
    try:
        df = read_excel_safely(excel_file, sheet_name="Tagesschnittliste", header=None)
    except Exception:
        return False
    valid_rows = df.apply(
        lambda row: any(is_valid_data_value(cell) for cell in row),
        axis=1,
    ).sum()
    return int(valid_rows) >= 10


def analyze_excel_file(excel_file, old_format_sheet_threshold=15):
    """Analyze one Excel file for metadata and processing eligibility."""
    result = {
        "file": str(excel_file),
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
        sheet_names = get_sheet_names_safely(excel_file)
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
        ligabericht_df = None
        tabelle_df = None

        try:
            ligabericht_df = read_excel_safely(excel_file, sheet_name="Ligabericht", header=None)
        except Exception:
            old_issues.append("Missing or unreadable 'Ligabericht' sheet")

        try:
            tabelle_df = read_excel_safely(excel_file, sheet_name="Tabelle", header=None)
        except Exception:
            old_issues.append("Missing or unreadable 'Tabelle' sheet")

        if ligabericht_df is not None:
            league_raw = get_cell_value(ligabericht_df, 7, 15)  # P8:T8
            location_raw = get_cell_value(ligabericht_df, 7, 4)  # E8:J8
            week_raw = get_cell_value(ligabericht_df, 5, 4)  # E6:F6
            date_raw = get_cell_value(ligabericht_df, 5, 16)  # Q6:T6

            result["debug_league_raw"] = "" if pd.isna(league_raw) else str(league_raw)
            result["debug_location_raw"] = "" if pd.isna(location_raw) else str(location_raw)
            result["debug_week_raw"] = "" if pd.isna(week_raw) else str(week_raw)
            result["debug_date_raw"] = "" if pd.isna(date_raw) else str(date_raw)

            result["league"] = normalize_league_display_to_canonical(league_raw) or normalize_optional_text(league_raw)
            result["location"] = normalize_optional_text(location_raw)
            week_value = parse_week_from_text(week_raw)
            if week_value is not None:
                result["available_weeks"] = str(week_value)
            date_info = parse_old_format_date(date_raw)
            result["season"] = derive_season_from_old_date(date_info)
            if not result["season"] or _season_from_content_is_uncertain(result["season"]):
                path_si = infer_season_from_path(excel_file)
                if path_si:
                    result["season"] = path_si["season_short"]
            result["games_per_week"] = None
            result["degradation_trace"] = (
                f"old_format league_raw='{result['debug_league_raw'] or 'missing'}', "
                f"week_raw='{result['debug_week_raw'] or 'missing'}', "
                f"date_raw='{result['debug_date_raw'] or 'missing'}', "
                f"location_raw='{result['debug_location_raw'] or 'missing'}'"
            )

            if not result["league"]:
                old_issues.append("Missing league in Ligabericht P8:T8")
            if week_value is None:
                old_issues.append("Missing week in Ligabericht E6:F6")
            if date_info is None:
                old_issues.append("Missing/invalid date in Ligabericht Q6:T6")
            if not result["season"]:
                old_issues.append("Could not derive season from Ligabericht date or folder path")
            if not result["location"]:
                old_issues.append("Missing location in Ligabericht E8:J8")

        if tabelle_df is not None:
            teams_raw = get_cell_value(tabelle_df, 2, 13)  # N3:Q3
            result["debug_teams_raw"] = "" if pd.isna(teams_raw) else str(teams_raw)
            result["number_of_teams"] = parse_metadata_int(teams_raw)
            if result["number_of_teams"] is None:
                old_issues.append("Missing number of teams in Tabelle N3:Q3")

        if not old_format_results_are_valid(excel_file):
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
        spielorte_df = read_excel_safely(excel_file, sheet_name="Spielorte", header=None)
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
        league = extract_league_from_schluessel(excel_file)
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
        path_si = infer_season_from_path(excel_file)
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
            if week_sheet_has_valid_data(excel_file, week):
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
        row = _analyze_with_cache(
            file_path,
            analysis_log,
            old_format_sheet_threshold=old_format_sheet_threshold,
            force_reanalyze=force_reanalyze,
            overrides_df=overrides_df,
        )
        if row.get("from_cache"):
            cache_hits += 1
        else:
            reason = str(row.get("analysis_reexecute_reason") or "cache miss: unknown")
            print(f"  re-analyze: {file_path} -> {reason}")
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


def run_convert_legacy_xls_mode(excel_files):
    """Convert legacy .xls files to .xlsx in place via LibreOffice headless."""
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
    print(f"Converting {len(xls_files)} legacy .xls file(s)...")
    for source_file in xls_files:
        target_file = source_file.with_suffix(".xlsx")
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


def run_process_mode_with_analysis(excel_files, args):
    """Analyze first, then process only eligible post-2022 files."""
    reset_team_normalization_stats()
    analysis_log = load_analysis_log()
    overrides_df = load_extract_overrides()
    overrides_manifest_fingerprint = compute_overrides_manifest_fingerprint(overrides_df)
    analysis_rows = []
    cache_hits = 0
    total_analysis_files = len(excel_files)
    for index, file_path in enumerate(excel_files, start=1):
        row = _analyze_with_cache(
            file_path,
            analysis_log,
            old_format_sheet_threshold=args.old_format_sheet_threshold,
            force_reanalyze=args.force_reanalyze,
            overrides_df=overrides_df,
        )
        if row.get("from_cache"):
            cache_hits += 1
        else:
            reason = str(row.get("analysis_reexecute_reason") or "cache miss: unknown")
            print(f"  re-analyze (process mode): {file_path} -> {reason}")
        analysis_rows.append(row)
        print_progress_bar(index, total_analysis_files, "Analyzing files")
    save_analysis_log(analysis_log)
    analysis_df = pd.DataFrame(analysis_rows)
    if analysis_df.empty:
        print("No files available for processing.")
        return

    if args.analysis_output:
        output_path = Path(args.analysis_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_df.to_csv(output_path, sep=";", index=False)
        print(f"Process-mode analysis CSV written to: {output_path}")

    eligible_df = analysis_df[
        (analysis_df["eligible_for_processing"] == True)
        & (analysis_df["data_format"] == "data_format_post_2022")
    ].copy()

    print(
        f"Eligible post_2022 files for processing: {len(eligible_df)}/{len(analysis_df)} "
        f"(cache hits: {cache_hits})"
    )
    if eligible_df.empty:
        print("No eligible post_2022 files to process.")
        return

    continuous_output_file = Path("database/data/historical_league_results.csv")
    process_cache = analysis_log.setdefault("processing_cache", {})
    combo_cache = process_cache.setdefault("league_season_outputs", {})

    output_dir = Path("C:/tmp/csvs")
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files = []
    skipped_combo_count = 0

    combo_keys = (
        eligible_df[["Season", "League"]]
        if "Season" in eligible_df.columns and "League" in eligible_df.columns
        else eligible_df[["season", "league"]].rename(columns={"season": "Season", "league": "League"})
    )
    combo_count = len(combo_keys.drop_duplicates())
    processed_combos = 0

    for (season_value, league_value), combo_df in eligible_df.groupby(["season", "league"], dropna=False):
        processed_combos += 1
        season_part = sanitize_filename_component(season_value if pd.notna(season_value) else "unknown_season")
        league_part = sanitize_filename_component(league_value if pd.notna(league_value) else "unknown_league")
        combo_output_file = output_dir / f"{season_part} {league_part}.csv"
        combo_cache_key = f"{season_part}::{league_part}"
        combo_signature = _build_combo_processing_signature(
            combo_df,
            season_value=season_value,
            league_value=league_value,
        )

        cached_combo = combo_cache.get(combo_cache_key, {})
        combo_cache_hit = (
            not args.force_reanalyze
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

        combo_criteria = {
            "force_reanalyze_disabled": not args.force_reanalyze,
            "has_cached_combo": isinstance(cached_combo, dict),
            "combo_signature_match": cached_combo.get("combo_signature") == combo_signature,
            "analyzer_version_match": cached_combo.get("analyzer_version") == ANALYZER_VERSION,
            "processor_version_match": cached_combo.get("processor_version") == PROCESSOR_VERSION,
            "output_file_exists": combo_output_file.is_file(),
        }
        if args.force_reanalyze:
            combo_reexecute_reason = "forced via --force_reanalyze"
        else:
            failed_combo_criteria = [name for name, ok in combo_criteria.items() if not ok]
            combo_reexecute_reason = (
                "cache miss: " + ", ".join(failed_combo_criteria) if failed_combo_criteria else "output_hash_mismatch"
            )
        print(f"  reprocess combo [{season_part} | {league_part}] -> {combo_reexecute_reason}")

        combo_output_df = pd.DataFrame()
        total_files_in_combo = len(combo_df)
        for file_index, row in enumerate(combo_df.itertuples(index=False), start=1):
            input_file = Path(row.file)
            available_weeks = parse_available_weeks(row.available_weeks)
            if not available_weeks:
                continue

            for week in available_weeks:
                global dict_of_match_numbers
                dict_of_match_numbers = {}
                with redirect_stdout(io.StringIO()):
                    result = extract_excel_data(
                        str(input_file),
                        args.team_sheet_prefix + str(week),
                        args.season_sheet,
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
            # Stage 3: normalize extracted data before writing/merging.
            combo_output_df = normalize_extracted_dataframe(combo_output_df)
            combo_output_df = combo_output_df.sort_values(
                by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"]
            )
            combo_output_df.to_csv(combo_output_file, sep=";", index=False)
            combo_hash = compute_file_sha256(combo_output_file)
            created_files.append((combo_output_file, len(combo_output_df)))
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
                "last_reexecute_reason": combo_reexecute_reason,
            }

        print_progress_bar(processed_combos, combo_count, "Processing combos")

    # Build merge targets from the current eligible process scope (not all CSVs in output dir).
    target_output_files = []
    for row in eligible_df.itertuples(index=False):
        season_value = getattr(row, "season", None)
        league_value = getattr(row, "league", None)
        if pd.isna(season_value) or pd.isna(league_value):
            continue
        season_part = sanitize_filename_component(season_value)
        league_part = sanitize_filename_component(league_value)
        target_output_files.append(output_dir / f"{season_part} {league_part}.csv")
    target_output_files = sorted(set(target_output_files))

    merged_frames = []
    missing_target_outputs = []
    for csv_file in target_output_files:
        if csv_file.is_file():
            try:
                merged_frames.append(pd.read_csv(csv_file, sep=";", dtype=str))
            except Exception as exc:
                print(f"Warning: failed to read target CSV during merge: {csv_file} ({exc})")
        else:
            missing_target_outputs.append(csv_file)

    if not merged_frames:
        print("No data extracted and no existing target CSVs found for eligible process scope.")
        if missing_target_outputs:
            print("Missing target CSVs:")
            for missing_file in missing_target_outputs:
                print(f"  - {missing_file}")
        return

    merged_df = pd.concat(merged_frames, ignore_index=True)
    # Apply normalization at merge stage even when all combo outputs were cache hits.
    merged_df = normalize_extracted_dataframe(merged_df)
    merged_df = normalize_team_numbering_dataframe(merged_df, overrides_df=load_team_number_overrides())
    merged_df = merged_df.sort_values(
        by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"],
        key=lambda col: col.astype(str),
    )

    # Continuous cross-season/cross-league output for backend source registration.
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
        "eligible_count": int(len(eligible_df)),
        "combo_cache_entries": int(len(combo_cache)),
        "skipped_combo_count": int(skipped_combo_count),
    }
    save_analysis_log(analysis_log)

    print("\nCreated CSV files:")
    for output_file, row_count in created_files:
        print(f"  - {output_file} ({row_count} rows)")
    if missing_target_outputs:
        print("\nProcess scope CSVs missing (skipped from merge):")
        for missing_file in missing_target_outputs:
            print(f"  - {missing_file}")
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


def run_normalize_data_mode(args):
    """Rebuild normalized continuous output from existing combo CSVs only."""
    reset_team_normalization_stats()
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

    merged_df = pd.concat(merged_frames, ignore_index=True)
    merged_df = normalize_extracted_dataframe(merged_df)
    merged_df = normalize_team_numbering_dataframe(merged_df, overrides_df=load_team_number_overrides())
    merged_df = merged_df.sort_values(
        by=["Season", "League", "Week", "Round Number", "Match Number", "Team", "Position"],
        key=lambda col: col.astype(str),
    )

    continuous_output_file = Path("database/data/historical_league_results.csv")
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
    excel_files = filter_xls_for_mode(excel_files, args.mode, args.skip_xls)
    if not excel_files and not (args.mode == "analyze" and skipped_discovery_files):
        print("No Excel files found for given input.")
        raise SystemExit(1)

    print(f"Excel files discovered: {len(excel_files)}")
    for file_path in excel_files:
        print(f"  - {file_path}")

    if args.mode == "convert_legacy_xls":
        run_convert_legacy_xls_mode(excel_files)
        raise SystemExit(0)

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
    