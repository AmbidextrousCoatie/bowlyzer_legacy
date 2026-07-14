"""Orchestrates configured tournament imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from database.tournament_import.config import (
    ImportEntry,
    TournamentImportConfig,
    get_format_spec,
    load_config,
    resolve_output_path,
    resolve_source_path,
)
from database.tournament_import.io import (
    GF_REGIONAL_TOURNAMENT_CSV,
    MANUAL_TOURNAMENT_CSV,
    merge_rows_by_season_events,
    strip_rows_for_season_tournament,
    write_csv_rows,
)
from database.tournament_import.postprocess import postprocess_rows
from database.tournament_import.registry import get_adapter
from database.tournament_import.adapters.base import ImportResult
from database.tournament_import.adapters.legacy_pdf_validation import (
    begin_parse_warnings,
    drain_parse_warnings,
)


@dataclass
class ServiceRunSummary:
    results: List[ImportResult] = field(default_factory=list)
    missing_legacy_pdfs: List[str] = field(default_factory=list)
    rebuilt_player_hybrid: bool = False
    published_parquet: Dict[str, object] | None = None
    player_cache_invalidation: Dict[str, int] | None = None
    tournament_cache_invalidation: Dict[str, int] | None = None


class TournamentImportService:
    def __init__(self, config: TournamentImportConfig | None = None, config_path: str | Path | None = None):
        self.config = config or load_config(config_path)

    def run(
        self,
        *,
        entry_ids: Optional[List[str]] = None,
        tournaments: Optional[List[str]] = None,
        first_year: Optional[int] = None,
        last_year: Optional[int] = None,
        input_dir: Optional[Path] = None,
        rebuild_player_hybrid: bool = True,
        publish_parquet: bool = True,
        dry_run: bool = False,
    ) -> ServiceRunSummary:
        summary = ServiceRunSummary()

        if tournaments is not None or first_year is not None or last_year is not None:
            if tournaments is None or first_year is None or last_year is None:
                raise ValueError("Specify --tournament, --first-year, and --last-year together")
            summary = self._run_legacy_pdf_range(
                tournaments=tournaments,
                first_year=first_year,
                last_year=last_year,
                input_dir=input_dir,
                dry_run=dry_run,
            )
            if dry_run or not summary.results:
                return summary
        else:
            selected = self._select_entries(entry_ids)
            for entry in selected:
                result = self._run_entry(entry, dry_run=dry_run)
                summary.results.append(result)
            if dry_run or not summary.results:
                return summary

        if publish_parquet:
            from database.tournament_import.publish import publish_tournaments_parquet

            summary.published_parquet = publish_tournaments_parquet()
            summary.tournament_cache_invalidation = self._invalidate_tournament_caches()
            summary.player_cache_invalidation = self._invalidate_player_caches()

        if rebuild_player_hybrid:
            self._rebuild_player_hybrid()
            summary.rebuilt_player_hybrid = True
        return summary

    def _run_legacy_pdf_range(
        self,
        *,
        tournaments: List[str],
        first_year: int,
        last_year: int,
        input_dir: Optional[Path],
        dry_run: bool,
    ) -> ServiceRunSummary:
        from database.tournament_import.legacy_pdf_targets import (
            import_entry_for_target,
            resolve_legacy_pdf_targets,
        )

        summary = ServiceRunSummary()
        resolved = resolve_legacy_pdf_targets(
            tournaments=tournaments,
            first_year=first_year,
            last_year=last_year,
            input_dir=input_dir,
        )
        summary.missing_legacy_pdfs = list(resolved.missing)

        for target in resolved.targets:
            entry = import_entry_for_target(target)
            try:
                summary.results.append(self._run_entry(entry, dry_run=dry_run))
            except (ValueError, FileNotFoundError) as exc:
                summary.missing_legacy_pdfs.append(
                    f"{target.tournament_code}:{target.calendar_year} ({exc})"
                )
        return summary

    def _select_entries(self, entry_ids: Optional[List[str]]) -> List[ImportEntry]:
        entries = [e for e in self.config.imports if e.enabled]
        if entry_ids:
            wanted = {eid.strip() for eid in entry_ids}
            entries = [e for e in entries if e.id in wanted]
            missing = wanted - {e.id for e in entries}
            if missing:
                raise KeyError(f"Unknown or disabled import id(s): {sorted(missing)}")
        return entries

    def _run_entry(self, entry: ImportEntry, *, dry_run: bool) -> ImportResult:
        source = resolve_source_path(entry.source)
        entry = self._enrich_entry_from_registry(entry, source)
        fmt = get_format_spec(self.config, entry)
        adapter = get_adapter(fmt.adapter)

        begin_parse_warnings()
        raw_rows = adapter.parse(source, entry)
        parse_warnings = drain_parse_warnings()
        postprocessed = postprocess_rows(raw_rows)
        if postprocessed:
            import pandas as pd

            from data_access.tournament_data_normalization import normalize_tournament_dataframe

            frame = pd.DataFrame(postprocessed)
            frame, _norm_stats = normalize_tournament_dataframe(frame)
            postprocessed = frame.to_dict(orient="records")
        event_names = sorted({row["Event Name"] for row in postprocessed})
        season = str(postprocessed[0].get("Season", "") or "").strip() if postprocessed else ""

        result = ImportResult(
            entry_id=entry.id,
            source=source,
            event_names=event_names,
            raw_row_count=len(raw_rows),
            postprocessed_row_count=len(postprocessed),
            warnings=list(parse_warnings),
        )

        if dry_run:
            return result

        output_path = resolve_output_path(entry, event_names)
        write_csv_rows(output_path, postprocessed)

        registry = self._registry_for_source(source)
        if entry.merge_target == "manual":
            if season and registry is not None:
                strip_rows_for_season_tournament(
                    MANUAL_TOURNAMENT_CSV,
                    season=season,
                    tournament_id=registry.tournament_id,
                    legacy_event_names=registry.legacy_event_names,
                )
            before, after = merge_rows_by_season_events(MANUAL_TOURNAMENT_CSV, postprocessed)
            result.warnings.append(
                f"Merged into {MANUAL_TOURNAMENT_CSV.name}: {before} -> {after} rows"
            )
        elif entry.merge_target == "gf_regional":
            if season and registry is not None:
                strip_rows_for_season_tournament(
                    GF_REGIONAL_TOURNAMENT_CSV,
                    season=season,
                    tournament_id=registry.tournament_id,
                    legacy_event_names=registry.legacy_event_names,
                )
            before, after = merge_rows_by_season_events(GF_REGIONAL_TOURNAMENT_CSV, postprocessed)
            result.warnings.append(
                f"Merged into {GF_REGIONAL_TOURNAMENT_CSV.name}: {before} -> {after} rows"
            )

        return result

    def _registry_for_source(self, source: Path):
        from database.tournament_import.source_registry import lookup_source_row

        return lookup_source_row(source)

    def _enrich_entry_from_registry(self, entry: ImportEntry, source: Path) -> ImportEntry:
        """Apply tournament_source_registry.csv metadata to static import jobs."""
        registry = self._registry_for_source(source)
        if registry is None:
            return entry
        options = dict(entry.options)
        if registry.event_name and not str(options.get("event_name") or "").strip():
            options["event_name"] = registry.event_name
        return ImportEntry(
            id=entry.id,
            format=entry.format,
            source=entry.source,
            enabled=entry.enabled,
            merge_target=entry.merge_target,
            output=entry.output,
            options=options,
        )

    def _rebuild_player_hybrid(self) -> None:
        from app.config.database_config import _build_player_merged_hybrid_csv

        _build_player_merged_hybrid_csv()

    def _invalidate_tournament_caches(self) -> Dict[str, int]:
        from app.cache.player_data_cache import invalidate_tournament_published_caches

        return invalidate_tournament_published_caches()

    def _invalidate_player_caches(self) -> Dict[str, int]:
        from app.cache.player_data_cache import invalidate_player_merged_caches

        return invalidate_player_merged_caches()
