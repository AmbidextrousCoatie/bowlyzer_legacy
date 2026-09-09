from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, List

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database.paths import get_data_dir, merge_duplicates_non_exact_report_csv, merge_duplicates_report_csv
from data_access.player_id_name_normalization import (
    apply_player_id_name_normalization,
    compute_player_id_name_normalization_fingerprint,
    format_normalization_summary as format_player_id_normalization_summary,
    load_player_id_only_remapping_rules,
)
from data_access.players_registry import (
    apply_legacy_player_id_remapping,
    apply_players_registry,
    compute_players_registry_fingerprint,
    format_registry_apply_summary,
    load_players_registry_df,
)
from data_access.competition_schema import apply_league_competition_schema_v2
from scripts.data.extract_excel_data import (
    load_team_number_overrides,
    normalize_extracted_dataframe,
    normalize_team_numbering_dataframe,
    print_team_normalization_summary,
    reset_team_normalization_stats,
)


DEFAULT_OUT = get_data_dir() / "league_results_merged.csv"
CSV_SEP = ";"
# Stable dedupe: ``match number`` is assignment-order dependent across extracts; ``player``
# display names vary after registry normalization. Prefer ``player id`` + ``opponent``.
DEFAULT_KEYS = (
    "league",
    "season",
    "week",
    "round number",
    "team",
    "position",
    "player id",
    "opponent",
)


def _resolve_key_columns(df: pd.DataFrame, keys: List[str]) -> Dict[str, str]:
    """Map logical dedupe keys to concrete CSV column names."""
    normalized = {str(col).strip().lower(): str(col) for col in df.columns}

    def pick(candidates: Iterable[str], logical: str) -> str:
        for candidate in candidates:
            hit = normalized.get(candidate)
            if hit:
                return hit
        raise ValueError(
            f"Could not resolve dedupe key '{logical}'. Tried {list(candidates)}. "
            f"Available columns: {list(df.columns)}"
        )

    alias_candidates: Dict[str, Iterable[str]] = {
        "league": ("event", "league"),
        "season": ("season",),
        "week": ("week",),
        "game": ("game", "match number", "game number"),
        "round number": ("round number", "round", "round_no", "round_nr"),
        "match number": ("match number", "match", "game", "game number"),
        "team": ("team", "team name"),
        "position": ("position",),
        "player": ("player", "player name"),
        "player id": ("player id", "player_id", "edv", "edv-nr"),
        "opponent": ("opponent", "opponent team", "gegner"),
    }
    out: Dict[str, str] = {}
    for key in keys:
        out[key] = pick(alias_candidates.get(key, (key,)), key)
    return out


def _normalized_key(series: pd.Series) -> pd.Series:
    # Keep key normalization simple and deterministic.
    return series.fillna("").astype(str).str.strip().str.lower()


def _apply_dedupe_key_columns(combined: pd.DataFrame, key_cols: Dict[str, str]) -> List[str]:
    """
    Materialize ``__k_*`` columns for dedupe.

    ``player id`` falls back to ``player`` when the id cell is empty (legacy rows).
    """
    normalized = {str(col).strip().lower(): str(col) for col in combined.columns}
    player_col = key_cols.get("player")
    if not player_col:
        for candidate in ("player", "player name"):
            player_col = normalized.get(candidate)
            if player_col:
                break

    dedupe_cols: List[str] = []
    for logical, concrete in key_cols.items():
        if logical == "player":
            continue
        if logical == "player id":
            pid_series = _normalized_key(combined[concrete])
            if player_col:
                pid_series = pid_series.mask(
                    pid_series.eq(""),
                    _normalized_key(combined[player_col]),
                )
            combined["__k_player id"] = pid_series
            dedupe_cols.append("__k_player id")
            continue
        col_name = f"__k_{logical}"
        combined[col_name] = _normalized_key(combined[concrete])
        dedupe_cols.append(col_name)
    return dedupe_cols


def _write_duplicates_report(
    combined: pd.DataFrame,
    dedupe_cols: List[str],
    out_path: Path,
    non_exact_out_path: Path,
    sep: str,
    *,
    full_report_row_limit: int = 100_000,
) -> Dict[str, int]:
    """
    Write duplicate-key audit CSVs.

    Previously this used per-group ``iterrows`` CSV writing, which could take hours when
    inputs already contained near-complete key duplication (e.g. a published file that
    was merged with itself). Stats are vectorized; the full dump is skipped when it would
    exceed ``full_report_row_limit`` (non-exact conflicts are always written).
    """
    dup_mask = combined.duplicated(subset=dedupe_cols, keep=False)
    dup_df = combined.loc[dup_mask].copy()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    non_exact_out_path.parent.mkdir(parents=True, exist_ok=True)

    if dup_df.empty:
        header = list(combined.columns)
        pd.DataFrame(columns=header).to_csv(out_path, sep=sep, index=False)
        pd.DataFrame(columns=header).to_csv(non_exact_out_path, sep=sep, index=False)
        return {
            "duplicate_groups": 0,
            "duplicate_rows": 0,
            "exact_groups_strict": 0,
            "exact_groups_business": 0,
            "non_exact_groups_business": 0,
            "rows_in_exact_groups_business": 0,
            "rows_in_non_exact_groups_business": 0,
            "full_report_written": True,
            "full_report_skipped_rows": 0,
        }

    sort_cols = list(dedupe_cols)
    if "__source_idx" in dup_df.columns:
        sort_cols = sort_cols + ["__source_idx"]
    dup_df = dup_df.sort_values(by=sort_cols, ascending=True, kind="mergesort")

    dup_groups = int(dup_df.groupby(dedupe_cols, dropna=False, sort=False).ngroups)
    dup_rows = int(len(dup_df))

    # Group-level exactness stats:
    # - strict: all columns must match (including metadata columns).
    # - business: ignore merge metadata (__source_idx + __k_* columns).
    metadata_cols = {"__source_idx"} | {c for c in dup_df.columns if c.startswith("__k_")}
    strict_cols = list(dup_df.columns)
    business_cols = [c for c in strict_cols if c not in metadata_cols]

    strict_hash = pd.util.hash_pandas_object(dup_df[strict_cols], index=False)
    business_hash = pd.util.hash_pandas_object(dup_df[business_cols], index=False)
    hashed = dup_df[dedupe_cols].copy()
    hashed["__strict_hash"] = strict_hash
    hashed["__biz_hash"] = business_hash
    grouped = hashed.groupby(dedupe_cols, dropna=False, sort=False)
    strict_nunique = grouped["__strict_hash"].nunique()
    business_nunique = grouped["__biz_hash"].nunique()
    group_sizes = grouped.size()

    exact_groups_strict = int((strict_nunique == 1).sum())
    exact_business_mask = business_nunique == 1
    exact_groups_business = int(exact_business_mask.sum())
    rows_in_exact_groups_business = int(group_sizes[exact_business_mask].sum())
    rows_in_nonexact_groups_business = int(group_sizes[~exact_business_mask].sum())
    non_exact_groups_business = int((~exact_business_mask).sum())

    non_exact_key_frame = business_nunique[~exact_business_mask].reset_index()[dedupe_cols]
    if not non_exact_key_frame.empty:
        non_exact_df = dup_df.merge(non_exact_key_frame, on=dedupe_cols, how="inner")
        non_exact_df.to_csv(non_exact_out_path, sep=sep, index=False)
    else:
        pd.DataFrame(columns=list(dup_df.columns)).to_csv(non_exact_out_path, sep=sep, index=False)

    full_report_written = dup_rows <= full_report_row_limit
    if full_report_written:
        dup_df.to_csv(out_path, sep=sep, index=False)
        skipped_rows = 0
    else:
        # Header-only placeholder so callers still find a file; details are in stats / non-exact.
        pd.DataFrame(columns=list(dup_df.columns)).to_csv(out_path, sep=sep, index=False)
        skipped_rows = dup_rows
        print(
            f"  duplicate full report skipped ({dup_rows:,} rows > limit "
            f"{full_report_row_limit:,}); wrote non-exact only "
            f"({rows_in_nonexact_groups_business:,} rows).",
            flush=True,
        )

    return {
        "duplicate_groups": dup_groups,
        "duplicate_rows": dup_rows,
        "exact_groups_strict": exact_groups_strict,
        "exact_groups_business": exact_groups_business,
        "non_exact_groups_business": non_exact_groups_business,
        "rows_in_exact_groups_business": rows_in_exact_groups_business,
        "rows_in_non_exact_groups_business": rows_in_nonexact_groups_business,
        "full_report_written": full_report_written,
        "full_report_skipped_rows": skipped_rows,
    }


def merge_sources(
    input_paths: List[Path],
    out_path: Path,
    key_names: List[str],
    sep: str = CSV_SEP,
    duplicates_out_path: Path | None = None,
    non_exact_duplicates_out_path: Path | None = None,
    normalize_team_names: bool = True,
    normalize_player_ids: bool = True,
    write_csv: bool = False,
    show_progress: bool = True,
) -> Dict:
    if len(input_paths) < 2:
        raise ValueError("Provide at least two input CSV files.")

    if normalize_team_names:
        reset_team_normalization_stats()

    frames: List[pd.DataFrame] = []
    input_dims: List[Dict] = []
    overrides_df = load_team_number_overrides() if normalize_team_names else pd.DataFrame()
    player_id_rules = load_player_id_only_remapping_rules() if normalize_player_ids else []
    registry_df = load_players_registry_df() if normalize_player_ids else None
    player_id_stats: Dict[str, int] = {}
    registry_stats: Dict[str, int] = {}
    legacy_id_remapped = 0
    for idx, path in enumerate(input_paths):
        source_label = path.name
        print(f"  load [{idx + 1}/{len(input_paths)}] {source_label} …", flush=True)
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)
        if normalize_team_names and not df.empty:
            df = normalize_extracted_dataframe(
                df,
                show_progress=show_progress,
                progress_desc=f"normalize [{idx + 1}/{len(input_paths)}] {source_label}",
            )
            df = normalize_team_numbering_dataframe(
                df,
                overrides_df,
                show_progress=show_progress,
                progress_desc=f"team numbers [{idx + 1}/{len(input_paths)}] {source_label}",
            )
        if normalize_player_ids and not df.empty:
            print(
                f"  player ids [{idx + 1}/{len(input_paths)}] {source_label} "
                f"({len(df):,} rows) …",
                flush=True,
            )
            df, legacy_stats = apply_legacy_player_id_remapping(df)
            legacy_id_remapped += int(legacy_stats.get("legacy_id_remapped") or 0)
            if player_id_rules:
                df, batch_stats = apply_player_id_name_normalization(df, player_id_rules, id_only=True)
                for label, count in batch_stats.items():
                    player_id_stats[label] = player_id_stats.get(label, 0) + int(count)
            if registry_df is not None and not registry_df.empty:
                df, batch_stats = apply_players_registry(df, registry_df)
                for label, count in batch_stats.items():
                    registry_stats[label] = registry_stats.get(label, 0) + int(count)
        df["__source_idx"] = str(idx)
        frames.append(df)
        input_dims.append(
            {
                "path": str(path),
                "priority": idx,
                "rows": int(len(df)),
            }
        )

    print(f"  concat {len(frames)} sources ({sum(len(f) for f in frames):,} rows) …", flush=True)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    key_cols = _resolve_key_columns(combined, key_names)

    dedupe_cols = _apply_dedupe_key_columns(combined, key_cols)
    grouped_any = combined.groupby(dedupe_cols, dropna=False).size()
    duplicate_keys_any = int((grouped_any > 1).sum())
    grouped_cross_source = combined.groupby(dedupe_cols, dropna=False)["__source_idx"].nunique()
    conflict_keys = int((grouped_cross_source > 1).sum())
    duplicates_out_path = duplicates_out_path or merge_duplicates_report_csv(out_path)
    non_exact_duplicates_out_path = non_exact_duplicates_out_path or merge_duplicates_non_exact_report_csv(
        out_path
    )
    print(
        f"  duplicate report ({duplicate_keys_any:,} multi-row keys, "
        f"{conflict_keys:,} cross-source) …",
        flush=True,
    )
    duplicates_stats = _write_duplicates_report(
        combined=combined,
        dedupe_cols=dedupe_cols,
        out_path=duplicates_out_path,
        non_exact_out_path=non_exact_duplicates_out_path,
        sep=sep,
    )
    print(
        f"  duplicate report done: {duplicates_stats['duplicate_rows']:,} rows in "
        f"{duplicates_stats['duplicate_groups']:,} groups "
        f"({duplicates_stats['non_exact_groups_business']:,} non-exact business)",
        flush=True,
    )

    print("  dedupe + competition schema …", flush=True)
    merged = combined.drop_duplicates(subset=dedupe_cols, keep="last")
    merged = merged.drop(columns=dedupe_cols + ["__source_idx"])
    merged = apply_league_competition_schema_v2(merged)

    from data_access.parquet_sidecar import publish_dataframe

    print(
        f"  publish {len(merged):,} rows "
        f"({'parquet+csv' if write_csv else 'parquet'}) …",
        flush=True,
    )
    published = publish_dataframe(merged, out_path, write_csv=write_csv, sep=sep)
    parquet_path = published["parquet"]
    print("  publish done.", flush=True)

    per_source_unique: List[Dict] = []
    for idx in range(len(input_paths)):
        unique_rows = int(
            combined.loc[combined["__source_idx"] == str(idx)]
            .drop_duplicates(subset=dedupe_cols, keep="last")
            .shape[0]
        )
        per_source_unique.append(
            {
                "path": str(input_paths[idx]),
                "priority": idx,
                "unique_rows": unique_rows,
            }
        )

    if normalize_team_names:
        print_team_normalization_summary()
    if normalize_player_ids and legacy_id_remapped:
        print(f"Legacy EDV remapping: {legacy_id_remapped} row(s)")
    if normalize_player_ids and player_id_rules:
        print(format_player_id_normalization_summary(player_id_stats))
    if normalize_player_ids and registry_stats:
        print(format_registry_apply_summary(registry_stats))

    return {
        "dedupe_keys": key_names,
        "input_dims": input_dims,
        "input_unique_dims": per_source_unique,
        "merge_conflicts": {
            "keys_with_cross_source_conflict": conflict_keys,
            "keys_with_duplicates_any": duplicate_keys_any,
            "rows_deduped": int(len(combined) - len(merged)),
            "duplicate_groups_reported": duplicates_stats["duplicate_groups"],
            "duplicate_rows_reported": duplicates_stats["duplicate_rows"],
            "exact_duplicate_groups_strict": duplicates_stats["exact_groups_strict"],
            "exact_duplicate_groups_business": duplicates_stats["exact_groups_business"],
            "non_exact_duplicate_groups_business": duplicates_stats["non_exact_groups_business"],
            "rows_in_exact_duplicate_groups_business": duplicates_stats["rows_in_exact_groups_business"],
            "rows_in_non_exact_duplicate_groups_business": duplicates_stats["rows_in_non_exact_groups_business"],
        },
        "output_dims": {
            "rows": int(len(merged)),
        },
        "paths": {
            "output": str(out_path),
            "parquet_output": str(parquet_path),
            "csv_output": str(published["csv"]) if published.get("csv") else "",
            "duplicates_report": str(duplicates_out_path),
            "duplicates_non_exact_report": str(non_exact_duplicates_out_path),
        },
        "normalization": {
            "team_name_normalization_applied": bool(normalize_team_names),
            "players_registry_applied": bool(registry_df is not None and not registry_df.empty),
            "players_registry_row_count": int(len(registry_df)) if registry_df is not None else 0,
            "players_registry_fingerprint": compute_players_registry_fingerprint(registry_df),
            "players_registry_rows_changed": int(
                registry_stats.get("registry_exact", 0)
                + registry_stats.get("registry_reassembly", 0)
                + registry_stats.get("registry_close", 0)
            ),
            "player_id_remap_applied": bool(normalize_player_ids and player_id_rules),
            "legacy_edv_rows_remapped": int(legacy_id_remapped),
            "player_id_name_normalization_fingerprint": compute_player_id_name_normalization_fingerprint(),
            "player_id_rows_changed": int(sum(player_id_stats.values())),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Merge multiple CSV files with ordered priority. "
            "Later inputs win conflicts for duplicate dedupe keys."
        )
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        required=True,
        help="Ordered list of input CSV files. Last file has highest priority on conflicts.",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Path for merged CSV output.")
    parser.add_argument(
        "--duplicates-out",
        default="",
        help=(
            "Optional output path for duplicate rows report CSV. "
            "If omitted, uses <out> with '_duplicates' suffix."
        ),
    )
    parser.add_argument(
        "--duplicates-non-exact-out",
        default="",
        help=(
            "Optional output path for non-exact duplicate rows report CSV "
            "(only groups where business columns differ). "
            "If omitted, uses <out> with '_duplicates_non_exact' suffix."
        ),
    )
    parser.add_argument(
        "--keys",
        default=",".join(DEFAULT_KEYS),
        help="Comma-separated dedupe keys. Defaults: league,season,week,game,position",
    )
    parser.add_argument("--sep", default=CSV_SEP, help="CSV delimiter (default ';').")
    parser.add_argument(
        "--no-normalize-team-names",
        action="store_true",
        help=(
            "Disable team-name normalization. By default, the same normalization rules "
            "used by extract_excel_data are applied to every input before merge."
        ),
    )
    parser.add_argument(
        "--no-normalize-player-ids",
        action="store_true",
        help="Disable curated player_id_name_normalization.json remappings.",
    )
    parser.add_argument(
        "--write-csv",
        action="store_true",
        help="Also write the merged CSV (default: Parquet only).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars during per-source team normalization",
    )
    args = parser.parse_args()

    input_paths = [Path(p).resolve() for p in args.inputs]
    out_path = Path(args.out).resolve()
    duplicates_out_path = Path(args.duplicates_out).resolve() if str(args.duplicates_out).strip() else None
    non_exact_duplicates_out_path = (
        Path(args.duplicates_non_exact_out).resolve()
        if str(args.duplicates_non_exact_out).strip()
        else None
    )
    key_names = [k.strip().lower() for k in str(args.keys).split(",") if k.strip()]

    for p in input_paths:
        if not p.is_file():
            print(f"Missing CSV: {p}")
            return 2

    stats = merge_sources(
        input_paths=input_paths,
        out_path=out_path,
        key_names=key_names,
        sep=args.sep,
        duplicates_out_path=duplicates_out_path,
        non_exact_duplicates_out_path=non_exact_duplicates_out_path,
        normalize_team_names=not args.no_normalize_team_names,
        normalize_player_ids=not args.no_normalize_player_ids,
        write_csv=args.write_csv,
        show_progress=not args.no_progress,
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
