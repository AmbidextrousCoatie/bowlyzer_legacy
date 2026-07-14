#!/usr/bin/env python3
"""Build or refresh database/config/tournament_source_registry.csv from known PDFs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.paths import tournaments_input_dir
from database.tournament_import.legacy_pdf_format import detect_legacy_pdf_format
from database.tournament_import.legacy_pdf_targets import (
    calendar_years_for_season_range,
    resolve_legacy_pdf_targets,
)
from database.tournament_import.source_registry import (
    CATEGORY_IMPORT_META,
    DEFAULT_REGISTRY_PATH,
    TournamentSourceRow,
    compute_file_fingerprint,
    event_name_for_category,
    load_source_registry,
    merge_registry_rows,
    season_label,
    write_source_registry,
)
from database.tournament_scrape.categories import load_scrape_config, resolve_category_ids

# Known basename overrides from scrape tests / manual imports when flat-dir resolution differs.
KNOWN_BASENAMES: dict[tuple[str, int], str] = {
    ("suedbayerische-herren", 2009): "bm2009_sb_he_erg.pdf",
    ("suedbayerische-herren", 2012): "bm2012_sbm_h_erg.pdf",
    ("suedbayerische-herren", 2013): "bm2013_sb_herren_erg.pdf",
    ("nordbayerische-herren", 2012): "bm2012_nb_he_erg.pdf",
    ("nordbayerische-herren", 2013): "bm2013_nb_herren_erg.pdf",
    ("bayerische-einzel-herren", 2009): "bm2009_einzel_erg_he.pdf",
    ("bayerische-einzel-frauen", 2009): "bm2009_einzel_erg_da.pdf",
    ("bayerische-einzel-herren", 2005): "bm2005_einz_h_erg_fi.pdf",
    ("bayerische-einzel-frauen", 2005): "bm2005_einz_d_erg_fi.pdf",
    ("bayerisches-doppel-herren", 2005): "bm2005_dop_he_erg.pdf",
    ("bayerisches-doppel-frauen", 2005): "bm2005_dop_da_erg.pdf",
    ("bayerische-einzel-herren", 2010): "bm2010_einz_erg_h.pdf",
    ("bayerische-einzel-frauen", 2010): "bm2010_einz_erg_d.pdf",
    ("bayerische-einzel-herren", 2018): "bm2018_akt_einz_m_erg.pdf",
    ("bayerische-einzel-frauen", 2018): "bm2018_akt_einz_f_erg.pdf",
    ("bayerisches-doppel-herren", 2018): "bm2018_akt_dopp_m_erg.pdf",
    ("bayerisches-doppel-frauen", 2018): "bm2018_akt_dopp_f_erg.pdf",
    ("bayerische-einzel-frauen", 2019): "bm2019_akt_einz_da_erg.pdf",
    ("suedbayerische-herren", 2019): "bm2019_akt_sb_he_erg.pdf",
    ("nordbayerische-herren", 2019): "bm2019_akt_nb_he_erg.pdf",
}


KNOWN_LEGACY_EVENT_NAMES: dict[str, tuple[str, ...]] = {
    "bm2009_sb_he_erg.pdf": ("Südbayerische Meisterschaft 2009 Herren",),
    "bm2010_sb_he_erg.pdf": ("Südbayerische Meisterschaft 2010,  City-Bowling Augsburg",),
    "bm2011_sbm_h_erg.pdf": ("Südbayerische Meisterschaft Einzel Herren 2011",),
    "bm2012_sbm_h_erg.pdf": ("Süd-Bayerische Meisterschaft 2012",),
    "bm2013_sb_herren_erg.pdf": ("Südbayerische Meisterschaft 2013",),
    "bm2012_nbm_h_erg.pdf": ("Nordbayerische Meisterschaft Einzel Herren 2012",),
    "bm2013_nb_herren_erg.pdf": ("Nordbayerische Meisterschaft Einzel 2013",),
    "bm2017_nb_he_erg.pdf": ("Nordbayrische Meisterschaft Einzel 2017",),
    "bm2018_nb_he_erg.pdf": ("Nordbayrische Meisterschaft 2018",),
    "bm2016_sb_he_erg.pdf": ("Südbayerische Meisterschaft Einzel 2016",),
    "bm2017_sb_he_erg.pdf": ("Südbayerische Meisterschaft Einzel 2017",),
    "bm2018_sb_he_erg.pdf": ("Südbayerische Meisterschaft Einzel 2018",),
    "bm2019_akt_sb_he_erg.pdf": ("Südbayerische Meisterschaft Einzel 2019",),
}


def _row_from_target(
    *,
    basename: str,
    category_id: str,
    calendar_year: int,
    pdf_path: Path | None,
    input_dir: Path,
    notes: str = "",
) -> TournamentSourceRow:
    meta = CATEGORY_IMPORT_META[category_id]
    season_start = calendar_year - 1
    fingerprint = ""
    file_path = ""
    pdf_format = ""
    if pdf_path is not None and pdf_path.is_file():
        fingerprint = compute_file_fingerprint(pdf_path)
        try:
            file_path = pdf_path.resolve().relative_to(input_dir.resolve()).as_posix()
        except ValueError:
            file_path = pdf_path.name
        pdf_format = detect_legacy_pdf_format(pdf_path)
    return TournamentSourceRow(
        file_basename=basename,
        file_fingerprint=fingerprint,
        file_path=file_path,
        season=season_label(season_start),
        calendar_year=calendar_year,
        category_id=category_id,
        tournament_id=meta["tournament_id"],
        event_name=event_name_for_category(category_id, calendar_year),
        gender=meta["gender"],
        format=pdf_format,
        enabled=True,
        notes=notes,
        legacy_event_names=KNOWN_LEGACY_EVENT_NAMES.get(basename, ()),
    )


def _rows_from_resolved_targets(input_dir: Path, *, first_year: int, last_year: int) -> list[TournamentSourceRow]:
    category_ids = resolve_category_ids(tournaments=["sbm", "nbm", "bm", "bm_f"]) or []
    summary = resolve_legacy_pdf_targets(
        tournaments=["sbm", "nbm", "bm", "bm_f"],
        first_year=first_year,
        last_year=last_year,
        input_dir=input_dir,
    )
    rows = [
        _row_from_target(
            basename=target.pdf_path.name,
            category_id=target.category_id,
            calendar_year=target.calendar_year,
            pdf_path=target.pdf_path,
            input_dir=input_dir,
            notes="resolved from input dir",
        )
        for target in summary.targets
    ]

    # Seed expected rows for years/files missing on disk (editable in CSV).
    scrape_config = load_scrape_config()
    known_ids = {row.category_id: row for row in rows}
    for season_start, calendar_year in zip(
        range(first_year, last_year + 1),
        calendar_years_for_season_range(first_year, last_year),
    ):
        for category_id in category_ids:
            if any(row.calendar_year == calendar_year and row.category_id == category_id for row in rows):
                continue
            basename = KNOWN_BASENAMES.get((category_id, calendar_year))
            if not basename:
                continue
            pdf_path = input_dir / basename
            rows.append(
                _row_from_target(
                    basename=basename,
                    category_id=category_id,
                    calendar_year=calendar_year,
                    pdf_path=pdf_path if pdf_path.is_file() else None,
                    input_dir=input_dir,
                    notes="seed basename (file missing)" if not pdf_path.is_file() else "seed basename",
                )
            )
    return rows


def _rows_from_exceptions(input_dir: Path) -> list[TournamentSourceRow]:
    from database.tournament_import.source_exceptions import exceptions_as_registry_dicts

    rows: list[TournamentSourceRow] = []
    for raw in exceptions_as_registry_dicts():
        basename = str(raw["file_basename"])
        path = input_dir / basename
        fingerprint = ""
        file_path = ""
        if path.is_file():
            fingerprint = compute_file_fingerprint(path)
            try:
                file_path = path.resolve().relative_to(input_dir.resolve()).as_posix()
            except ValueError:
                file_path = path.name
        rows.append(
            TournamentSourceRow(
                file_basename=basename,
                file_fingerprint=fingerprint,
                file_path=file_path,
                season=str(raw["season"]),
                calendar_year=int(raw["calendar_year"]),
                category_id=str(raw["category_id"]),
                tournament_id=str(raw["tournament_id"]),
                event_name=str(raw["event_name"]),
                gender=str(raw["gender"]),
                format=str(raw["format"]),
                enabled=bool(raw.get("enabled", True)),
                notes=str(raw.get("notes") or ""),
                legacy_event_names=tuple(raw.get("legacy_event_names") or ()),
                source_sheet=str(raw.get("source_sheet") or ""),
            )
        )
    return rows


def _rows_from_scan(input_dir: Path) -> list[TournamentSourceRow]:
    scrape_config = load_scrape_config()
    rows: list[TournamentSourceRow] = []
    for pdf_path in sorted(input_dir.glob("*.pdf")):
        from database.tournament_import.legacy_pdf_targets import _calendar_year_from_name, _matches_category

        calendar_year = _calendar_year_from_name(pdf_path.name)
        if calendar_year is None:
            continue
        category_id = ""
        for category in scrape_config.categories:
            if _matches_category(pdf_path.name, category.id):
                category_id = category.id
                break
        if not category_id or category_id not in CATEGORY_IMPORT_META:
            continue
        rows.append(
            _row_from_target(
                basename=pdf_path.name,
                category_id=category_id,
                calendar_year=calendar_year,
                pdf_path=pdf_path,
                input_dir=input_dir,
                notes="scanned from input dir",
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Legacy PDF intake directory (default: work_dir/tournaments/input)",
    )
    parser.add_argument("--first-year", type=int, default=2005, help="First season start year")
    parser.add_argument("--last-year", type=int, default=2025, help="Last season start year")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Registry CSV path",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace rows for matching basenames instead of merging fingerprints only",
    )
    parser.add_argument(
        "--overwrite-format",
        action="store_true",
        help="Replace format column from detection when refreshing registry rows",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_dir = (args.input_dir or tournaments_input_dir()).resolve()

    incoming: list[TournamentSourceRow] = []
    if input_dir.is_dir():
        incoming.extend(_rows_from_scan(input_dir))
        incoming.extend(_rows_from_exceptions(input_dir))
        incoming.extend(
            _rows_from_resolved_targets(input_dir, first_year=args.first_year, last_year=args.last_year)
        )
    else:
        print(f"Input dir missing: {input_dir}", file=sys.stderr)

    existing = load_source_registry(args.output) if args.output.is_file() else []
    merged = merge_registry_rows(
        existing, incoming, overwrite=args.overwrite, overwrite_format=args.overwrite_format
    )
    if not merged:
        print("No registry rows produced.", file=sys.stderr)
        raise SystemExit(1)

    out = write_source_registry(merged, args.output)
    print(f"Wrote {len(merged)} row(s) to {out}")


if __name__ == "__main__":
    main()
