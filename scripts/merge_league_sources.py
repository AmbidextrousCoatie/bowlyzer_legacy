from __future__ import annotations

import argparse
import json
import csv
from pathlib import Path
import sys
from typing import Dict, Iterable, List

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from extract_excel_data import (
    load_team_number_overrides,
    normalize_extracted_dataframe,
    normalize_team_numbering_dataframe,
    print_team_normalization_summary,
    reset_team_normalization_stats,
)


DEFAULT_OUT = Path("database/data/league_results_merged.csv")
CSV_SEP = ";"
# TODO(cfell): Current legacy rows include "Team Total" lines reusing Position==0.
# Keep "player" in the dedupe key for now to avoid false collisions. Later we should
# model team totals explicitly (separate row type / stable synthetic key) and remove
# this workaround.
DEFAULT_KEYS = ("league", "season", "week", "round number", "match number", "team", "position", "player")


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
        "league": ("league",),
        "season": ("season",),
        "week": ("week",),
        "game": ("game", "match number", "game number"),
        "round number": ("round number", "round", "round_no", "round_nr"),
        "match number": ("match number", "match", "game", "game number"),
        "team": ("team", "team name"),
        "position": ("position",),
        "player": ("player", "player name"),
    }
    out: Dict[str, str] = {}
    for key in keys:
        out[key] = pick(alias_candidates.get(key, (key,)), key)
    return out


def _normalized_key(series: pd.Series) -> pd.Series:
    # Keep key normalization simple and deterministic.
    return series.fillna("").astype(str).str.strip().str.lower()


def _write_duplicates_report(
    combined: pd.DataFrame,
    dedupe_cols: List[str],
    out_path: Path,
    non_exact_out_path: Path,
    sep: str,
) -> Dict[str, int]:
    dup_mask = combined.duplicated(subset=dedupe_cols, keep=False)
    dup_df = combined.loc[dup_mask].copy()
    if dup_df.empty:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=sep)
            writer.writerow([*combined.columns])
        return {"duplicate_groups": 0, "duplicate_rows": 0}

    dup_df["__dup_key"] = dup_df[dedupe_cols].astype(str).agg("|".join, axis=1)
    dup_df = dup_df.sort_values(by=["__dup_key", "__source_idx"], ascending=[True, True])
    dup_groups = int(dup_df["__dup_key"].nunique())
    dup_rows = int(len(dup_df))

    # Group-level exactness stats:
    # - strict: all columns must match (including metadata columns).
    # - business: ignore merge metadata (__source_idx + __k_* columns).
    metadata_cols = {"__source_idx"} | {c for c in dup_df.columns if c.startswith("__k_")}
    strict_cols = [c for c in dup_df.columns if c != "__dup_key"]
    business_cols = [c for c in strict_cols if c not in metadata_cols]

    exact_groups_strict = 0
    exact_groups_business = 0
    rows_in_exact_groups_business = 0
    rows_in_nonexact_groups_business = 0
    for _, group in dup_df.groupby("__dup_key", sort=False):
        strict_unique = group[strict_cols].drop_duplicates().shape[0]
        business_unique = group[business_cols].drop_duplicates().shape[0]
        if strict_unique == 1:
            exact_groups_strict += 1
        if business_unique == 1:
            exact_groups_business += 1
            rows_in_exact_groups_business += int(len(group))
        else:
            rows_in_nonexact_groups_business += int(len(group))

    output_columns = [c for c in dup_df.columns if c != "__dup_key"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=sep)
        writer.writerow(output_columns)
        first_group = True
        for _, group in dup_df.groupby("__dup_key", sort=False):
            if not first_group:
                writer.writerow([])
            first_group = False
            for _, row in group.iterrows():
                writer.writerow([row.get(col, "") for col in output_columns])

    # Write only non-exact duplicate groups (business columns differ).
    non_exact_out_path.parent.mkdir(parents=True, exist_ok=True)
    with non_exact_out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=sep)
        writer.writerow(output_columns)
        first_group = True
        for _, group in dup_df.groupby("__dup_key", sort=False):
            business_unique = group[business_cols].drop_duplicates().shape[0]
            if business_unique <= 1:
                continue
            if not first_group:
                writer.writerow([])
            first_group = False
            for _, row in group.iterrows():
                writer.writerow([row.get(col, "") for col in output_columns])

    return {
        "duplicate_groups": dup_groups,
        "duplicate_rows": dup_rows,
        "exact_groups_strict": int(exact_groups_strict),
        "exact_groups_business": int(exact_groups_business),
        "non_exact_groups_business": int(dup_groups - exact_groups_business),
        "rows_in_exact_groups_business": int(rows_in_exact_groups_business),
        "rows_in_non_exact_groups_business": int(rows_in_nonexact_groups_business),
    }


def merge_sources(
    input_paths: List[Path],
    out_path: Path,
    key_names: List[str],
    sep: str = CSV_SEP,
    duplicates_out_path: Path | None = None,
    non_exact_duplicates_out_path: Path | None = None,
    normalize_team_names: bool = True,
) -> Dict:
    if len(input_paths) < 2:
        raise ValueError("Provide at least two input CSV files.")

    if normalize_team_names:
        reset_team_normalization_stats()

    frames: List[pd.DataFrame] = []
    input_dims: List[Dict] = []
    overrides_df = load_team_number_overrides() if normalize_team_names else pd.DataFrame()
    for idx, path in enumerate(input_paths):
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)
        if normalize_team_names and not df.empty:
            df = normalize_extracted_dataframe(df)
            df = normalize_team_numbering_dataframe(df, overrides_df)
        df["__source_idx"] = str(idx)
        frames.append(df)
        input_dims.append(
            {
                "path": str(path),
                "priority": idx,
                "rows": int(len(df)),
            }
        )

    combined = pd.concat(frames, ignore_index=True, sort=False)
    key_cols = _resolve_key_columns(combined, key_names)

    for logical_name, concrete_column in key_cols.items():
        combined[f"__k_{logical_name}"] = _normalized_key(combined[concrete_column])

    dedupe_cols = [f"__k_{k}" for k in key_names]
    grouped_any = combined.groupby(dedupe_cols, dropna=False).size()
    duplicate_keys_any = int((grouped_any > 1).sum())
    grouped_cross_source = combined.groupby(dedupe_cols, dropna=False)["__source_idx"].nunique()
    conflict_keys = int((grouped_cross_source > 1).sum())
    duplicates_out_path = duplicates_out_path or out_path.with_name(f"{out_path.stem}_duplicates{out_path.suffix}")
    non_exact_duplicates_out_path = non_exact_duplicates_out_path or out_path.with_name(
        f"{out_path.stem}_duplicates_non_exact{out_path.suffix}"
    )
    duplicates_stats = _write_duplicates_report(
        combined=combined,
        dedupe_cols=dedupe_cols,
        out_path=duplicates_out_path,
        non_exact_out_path=non_exact_duplicates_out_path,
        sep=sep,
    )

    merged = combined.drop_duplicates(subset=dedupe_cols, keep="last")
    merged = merged.drop(columns=dedupe_cols + ["__source_idx"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, sep=sep, index=False)

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
            "duplicates_report": str(duplicates_out_path),
            "duplicates_non_exact_report": str(non_exact_duplicates_out_path),
        },
        "normalization": {
            "team_name_normalization_applied": bool(normalize_team_names),
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
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
