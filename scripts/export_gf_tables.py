from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _add_repo_root_to_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


DEFAULT_TABLES: tuple[tuple[int, str], ...] = (
    (124, "sbm_suedbayerische_meisterschaft_2026"),
    (125, "nbm_nordbayerische_meisterschaft_2026"),
)
DEFAULT_STAGE_DEFINITIONS_JSON = "database/input/gf_tournament_stage_definitions.json"
DEFAULT_TABLE_TOURNAMENT_MAP_JSON = "database/input/gf_table_tournament_map.json"


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return cleaned.strip("_") or "gf_table"


def _parse_tables(raw: str) -> List[tuple[int, str]]:
    """
    Parse --tables as:
      124:sbm,125:nbm
    If label is omitted, a generic one is generated from the id.
    """
    out: List[tuple[int, str]] = []
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        if ":" in item:
            table_id_raw, label_raw = item.split(":", 1)
            table_id = int(table_id_raw.strip())
            label = _slugify(label_raw)
        else:
            table_id = int(item)
            label = f"table_{table_id}"
        out.append((table_id, label))
    return out


def _dedupe_entries_by_id(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for entry in entries:
        entry_id = str(entry.get("id") or "").strip()
        if entry_id:
            if entry_id in seen:
                continue
            seen.add(entry_id)
        deduped.append(entry)
    return deduped


def _fetch_all_entries(client: Any, table_id: int, page_size: int) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    page = 1
    while True:
        page_result = client.fetch_entries_page(form_id=table_id, page=page, page_size=page_size)
        if not page_result.entries:
            break
        entries.extend(page_result.entries)
        if len(page_result.entries) < page_size:
            break
        page += 1
    return _dedupe_entries_by_id(entries)


def _to_str_id(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    # Keep GF ids stable ("1", "5.3"), avoid "1.0" from numeric coercion.
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def _column_is_gf_field_id(column_name: str) -> bool:
    return bool(re.fullmatch(r"\d+(\.\d+)?", (column_name or "").strip()))


def _safe_header_label(raw: str) -> str:
    label = re.sub(r"\s+", " ", (raw or "").strip())
    label = re.sub(r'[\\/:*?"<>|]+', "_", label)
    return label or "unnamed"


def _build_field_label_map(form_payload: Dict[str, Any]) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    field_map: Dict[str, str] = {}
    mapping_rows: List[Dict[str, str]] = []
    fields = form_payload.get("fields")
    if not isinstance(fields, list):
        return field_map, mapping_rows

    for field in fields:
        if not isinstance(field, dict):
            continue
        field_id = _to_str_id(field.get("id"))
        label = str(field.get("label") or "").strip()
        admin_label = str(field.get("adminLabel") or "").strip()
        base_label = admin_label or label or f"field_{field_id}"
        base_label = _safe_header_label(base_label)
        if field_id:
            field_map[field_id] = base_label
            mapping_rows.append(
                {
                    "field_id": field_id,
                    "input_id": "",
                    "label": label,
                    "admin_label": admin_label,
                    "resolved_label": base_label,
                    "is_compound_input": "false",
                }
            )

        inputs = field.get("inputs")
        if isinstance(inputs, list):
            for input_def in inputs:
                if not isinstance(input_def, dict):
                    continue
                input_id = _to_str_id(input_def.get("id"))
                input_label = str(input_def.get("label") or "").strip()
                input_admin_label = str(input_def.get("adminLabel") or "").strip()
                resolved_input = input_admin_label or input_label or base_label or f"field_{input_id}"
                resolved_input = _safe_header_label(resolved_input)
                if input_id:
                    field_map[input_id] = resolved_input
                    mapping_rows.append(
                        {
                            "field_id": field_id,
                            "input_id": input_id,
                            "label": input_label or label,
                            "admin_label": input_admin_label or admin_label,
                            "resolved_label": resolved_input,
                            "is_compound_input": "true",
                        }
                    )
    return field_map, mapping_rows


def _write_rows_csv(path: Path, rows: List[Dict[str, str]], headers: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _rename_numeric_columns(
    rows: List[Dict[str, str]], field_labels: Dict[str, str]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    if not rows:
        return rows, []

    original_headers = list(rows[0].keys())
    rename_map: Dict[str, str] = {}
    rename_rows: List[Dict[str, str]] = []
    used_names: set[str] = set()
    for header in original_headers:
        new_header = header
        if _column_is_gf_field_id(header):
            resolved = field_labels.get(header, f"field_{header}")
            candidate = f"{header}__{_safe_header_label(resolved)}"
            suffix = 2
            new_header = candidate
            while new_header in used_names:
                new_header = f"{candidate}_{suffix}"
                suffix += 1
            rename_rows.append({"original_column": header, "renamed_column": new_header, "resolved_label": resolved})
        rename_map[header] = new_header
        used_names.add(new_header)

    renamed_rows: List[Dict[str, str]] = []
    for row in rows:
        renamed_rows.append({rename_map[h]: str(row.get(h, "")) for h in original_headers})
    return renamed_rows, rename_rows


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_tables_from_mapping(mapping: Dict[str, Any]) -> List[tuple[int, str]]:
    out: List[tuple[int, str]] = []
    for table_id_raw, conf in mapping.items():
        if not str(table_id_raw).isdigit():
            continue
        label = ""
        if isinstance(conf, dict):
            label = _slugify(str(conf.get("label") or ""))
        if not label:
            label = f"table_{table_id_raw}"
        out.append((int(table_id_raw), label))
    return sorted(out, key=lambda t: t[0])


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _build_postprocessed_rows(
    canonical_rows: List[Dict[str, str]], stage_meta_rows: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    if not canonical_rows:
        return []

    cut_by_stage: Dict[tuple[str, str, str], str] = {}
    for row in stage_meta_rows:
        key = (
            str(row.get("Event Name") or "").strip(),
            str(row.get("Season") or "").strip(),
            str(row.get("Tournament Stage Id") or "").strip(),
        )
        cut_by_stage[key] = str(row.get("Tournament Stage Cut") or "").strip()

    grouped: Dict[tuple[str, str, str], List[Dict[str, str]]] = {}
    for row in canonical_rows:
        key = (
            str(row.get("Event Name") or "").strip(),
            str(row.get("Season") or "").strip(),
            str(row.get("Round Number") or "").strip(),
        )
        grouped.setdefault(key, []).append(row)

    output: List[Dict[str, str]] = []
    for (event_name, season, stage_id), rows in grouped.items():
        by_game: Dict[int, List[Dict[str, str]]] = {}
        for row in rows:
            by_game.setdefault(_to_int(row.get("Game Number"), 0), []).append(row)

        stage_running: Dict[str, int] = {}
        overall_running: Dict[str, int] = {}
        cut_n = _to_int(cut_by_stage.get((event_name, season, stage_id), ""), default=-1)

        for game in sorted(by_game.keys()):
            game_rows = by_game[game]
            for row in game_rows:
                pid = str(row.get("Player ID") or "").strip() or str(row.get("Player") or "").strip()
                score = _to_int(row.get("Score"), 0)
                stage_running[pid] = stage_running.get(pid, 0) + score
                overall_running[pid] = overall_running.get(pid, 0) + score

            ranked = sorted(stage_running.items(), key=lambda t: (-t[1], t[0]))
            rank_map = {pid: idx + 1 for idx, (pid, _) in enumerate(ranked)}
            cut_score = ""
            if cut_n > 0 and len(ranked) >= cut_n:
                cut_score = str(ranked[cut_n - 1][1])

            for row in game_rows:
                pid = str(row.get("Player ID") or "").strip() or str(row.get("Player") or "").strip()
                enriched = dict(row)
                enriched["Cumulative Score"] = str(stage_running.get(pid, 0))
                enriched["Stage Rank"] = str(rank_map.get(pid, ""))
                enriched["Cut Line"] = cut_score
                enriched["Overall Cumulative Score"] = str(overall_running.get(pid, 0))
                output.append(enriched)

    return sorted(
        output,
        key=lambda r: (
            str(r.get("Season") or ""),
            str(r.get("Event Name") or ""),
            _to_int(r.get("Round Number"), 0),
            _to_int(r.get("Game Number"), 0),
            str(r.get("Player") or ""),
        ),
    )


def _maybe_transform_to_canonical(
    output_dir: Path,
    table_id: int,
    label: str,
    source_rows: List[Dict[str, str]],
    field_map_rows: List[Dict[str, str]],
    table_tournament_map: Dict[str, Any],
    stage_definitions: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, str]], List[Dict[str, str]]]:
    from scripts.transform_gf_tournament_to_canonical import (
        CANONICAL_HEADERS,
        STAGE_META_HEADERS,
        StageDef,
        transform,
    )

    table_conf = table_tournament_map.get(str(table_id))
    if not isinstance(table_conf, dict):
        return {}, [], []
    tournament_key = str(table_conf.get("tournament_key") or "").strip()
    year = str(table_conf.get("year") or "").strip()
    season = str(table_conf.get("season") or year).strip()
    if not tournament_key or not year:
        return {}, [], []

    tournament_defs = stage_definitions.get(tournament_key)
    if not isinstance(tournament_defs, dict):
        return {}, [], []
    year_defs = tournament_defs.get(year)
    if not isinstance(year_defs, dict):
        return {}, [], []

    event_name = str(year_defs.get("event_name") or tournament_key).strip()
    event_type = str(year_defs.get("event_type") or "tournament").strip()
    default_location = str(year_defs.get("default_location") or "").strip()
    stage_items = year_defs.get("stages")
    if not isinstance(stage_items, list) or not stage_items:
        return {}, [], []

    stages: List[StageDef] = []
    for item in stage_items:
        if not isinstance(item, dict):
            continue
        stages.append(
            StageDef(
                stage_id=int(item["id"]),
                stage_name=str(item.get("name") or f"Stage {item['id']}"),
                stage_cut=str(item.get("cut") or "n/a"),
                stage_evaluation=str(item.get("evaluation") or "Scratch Total"),
                date=str(item.get("date") or ""),
                location=str(item.get("location") or default_location),
                game_start=int(item["game_start"]),
                game_end=int(item["game_end"]),
            )
        )
    if not stages:
        return {}, [], []

    canonical_rows, stage_meta_rows = transform(
        source_rows=source_rows,
        field_map_rows=field_map_rows,
        season=season,
        event_name=event_name,
        event_type=event_type,
        stages=sorted(stages, key=lambda s: s.stage_id),
        handicap="0",
        player_lookup={},
    )
    for stage_row in stage_meta_rows:
        stage_row["Season"] = season
        stage_row["Event Name"] = event_name

    canonical_path = output_dir / f"gf_table_{table_id}__{label}__canonical_clean.csv"
    stage_meta_path = output_dir / f"gf_table_{table_id}__{label}__stage_meta.csv"
    _write_rows_csv(canonical_path, canonical_rows, CANONICAL_HEADERS)
    _write_rows_csv(stage_meta_path, stage_meta_rows, STAGE_META_HEADERS)
    summary = {
        "tournament_key": tournament_key,
        "year": year,
        "season": season,
        "canonical_clean_csv": str(canonical_path),
        "stage_meta_csv": str(stage_meta_path),
        "canonical_rows": len(canonical_rows),
    }
    return summary, canonical_rows, stage_meta_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export full GF tables/forms to separate CSV files for inspection."
    )
    parser.add_argument(
        "--tables",
        default="",
        help=(
            "Comma-separated table definitions: ID[:label], e.g. "
            "'124:sbm_suedbayerische_meisterschaft_2026,125:nbm_nordbayerische_meisterschaft_2026'. "
            "If omitted, defaults to IDs 124 and 125."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="database/input/gf_tables_export",
        help="Output folder for generated CSVs.",
    )
    parser.add_argument(
        "--stage-definitions-json",
        default=DEFAULT_STAGE_DEFINITIONS_JSON,
        help="Tournament stage definitions JSON path.",
    )
    parser.add_argument(
        "--table-tournament-map-json",
        default=DEFAULT_TABLE_TOURNAMENT_MAP_JSON,
        help="Table ID to tournament mapping JSON path.",
    )
    parser.add_argument("--site", required=False, help="WordPress site base URL.")
    parser.add_argument("--ck", required=False, help="GF consumer key.")
    parser.add_argument("--cs", required=False, help="GF consumer secret.")
    parser.add_argument("--page-size", type=int, default=200, help="GF page size (max 200).")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification.")
    args = parser.parse_args()

    _add_repo_root_to_path()
    from pipeline.config import GfConfig
    from pipeline.gf_client import GfClient
    from pipeline.staging import rows_from_entries, write_csv

    site = (args.site or os.getenv("GF_SITE_BASE_URL", "")).strip()
    ck = (args.ck or os.getenv("GF_CONSUMER_KEY", "")).strip()
    cs = (args.cs or os.getenv("GF_CONSUMER_SECRET", "")).strip()
    if not site or not ck or not cs:
        print(
            "Missing credentials/site. Provide --site --ck --cs or set "
            "GF_SITE_BASE_URL/GF_CONSUMER_KEY/GF_CONSUMER_SECRET."
        )
        return 2

    stage_definitions = _load_json_file(Path(args.stage_definitions_json).resolve())
    table_tournament_map = _load_json_file(Path(args.table_tournament_map_json).resolve())
    if args.tables.strip():
        tables = _parse_tables(args.tables)
    else:
        mapped = _build_tables_from_mapping(table_tournament_map)
        tables = mapped if mapped else list(DEFAULT_TABLES)
    page_size = max(1, min(200, int(args.page_size)))

    cfg = GfConfig(
        site_base_url=site,
        consumer_key=ck,
        consumer_secret=cs,
        verify_ssl=not args.insecure,
        page_size=page_size,
        forms=[table_id for table_id, _ in tables],
        entries_sort="id",
    )
    client = GfClient(cfg)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: Dict[str, Any] = {"output_dir": str(output_dir), "tables": []}
    combined_canonical_rows: List[Dict[str, str]] = []
    combined_stage_meta_rows: List[Dict[str, str]] = []
    combined_postprocessed_rows: List[Dict[str, str]] = []
    for table_id, label in tables:
        form_payload = client._request_json(f"forms/{table_id}")  # noqa: SLF001 - pragmatic reuse for one-off export
        field_labels, field_map_rows = _build_field_label_map(form_payload)
        entries = _fetch_all_entries(client=client, table_id=table_id, page_size=page_size)
        batch_id = f"manual_export_table_{table_id}"
        rows = rows_from_entries(entries=entries, form_id=table_id, batch_id=batch_id)
        output_raw_path = output_dir / f"gf_table_{table_id}__{label}.csv"
        write_csv(output_raw_path, rows)

        renamed_rows, rename_rows = _rename_numeric_columns(rows, field_labels)
        output_labeled_path = output_dir / f"gf_table_{table_id}__{label}__labeled.csv"
        write_csv(output_labeled_path, renamed_rows)

        field_map_path = output_dir / f"gf_table_{table_id}__{label}__field_map.csv"
        _write_rows_csv(
            field_map_path,
            field_map_rows,
            headers=["field_id", "input_id", "label", "admin_label", "resolved_label", "is_compound_input"],
        )

        rename_map_path = output_dir / f"gf_table_{table_id}__{label}__column_rename_map.csv"
        _write_rows_csv(
            rename_map_path,
            rename_rows,
            headers=["original_column", "renamed_column", "resolved_label"],
        )

        transformed, canonical_rows, stage_meta_rows = _maybe_transform_to_canonical(
            output_dir=output_dir,
            table_id=table_id,
            label=label,
            source_rows=rows,
            field_map_rows=field_map_rows,
            table_tournament_map=table_tournament_map,
            stage_definitions=stage_definitions,
        )
        combined_canonical_rows.extend(canonical_rows)
        combined_stage_meta_rows.extend(stage_meta_rows)
        postprocessed_rows = _build_postprocessed_rows(canonical_rows, stage_meta_rows)
        combined_postprocessed_rows.extend(postprocessed_rows)

        table_summary: Dict[str, Any] = {
            "table_id": table_id,
            "label": label,
            "entries": len(entries),
            "raw_csv": str(output_raw_path),
            "labeled_csv": str(output_labeled_path),
            "field_map_csv": str(field_map_path),
            "column_rename_map_csv": str(rename_map_path),
            "mapped_numeric_columns": len(rename_rows),
        }
        if postprocessed_rows:
            from scripts.transform_gf_tournament_to_canonical import CANONICAL_HEADERS

            postprocessed_headers = CANONICAL_HEADERS + [
                "Cumulative Score",
                "Stage Rank",
                "Cut Line",
                "Overall Cumulative Score",
            ]
            postprocessed_path = output_dir / f"gf_table_{table_id}__{label}__postprocessed.csv"
            _write_rows_csv(postprocessed_path, postprocessed_rows, postprocessed_headers)
            table_summary["postprocessed_csv"] = str(postprocessed_path)
            table_summary["postprocessed_rows"] = len(postprocessed_rows)
        table_summary.update(transformed)
        summary["tables"].append(table_summary)

    if combined_canonical_rows:
        from scripts.transform_gf_tournament_to_canonical import CANONICAL_HEADERS, STAGE_META_HEADERS

        combined_canonical_path = output_dir / "gf_tournaments_2026__combined_canonical_clean.csv"
        combined_stage_meta_path = output_dir / "gf_tournaments_2026__combined_stage_meta.csv"
        combined_postprocessed_path = output_dir / "gf_tournaments_2026__combined_postprocessed.csv"
        postprocessed_headers = CANONICAL_HEADERS + [
            "Cumulative Score",
            "Stage Rank",
            "Cut Line",
            "Overall Cumulative Score",
        ]
        _write_rows_csv(combined_canonical_path, combined_canonical_rows, CANONICAL_HEADERS)
        _write_rows_csv(combined_stage_meta_path, combined_stage_meta_rows, STAGE_META_HEADERS)
        _write_rows_csv(combined_postprocessed_path, combined_postprocessed_rows, postprocessed_headers)
        summary["combined"] = {
            "canonical_clean_csv": str(combined_canonical_path),
            "stage_meta_csv": str(combined_stage_meta_path),
            "postprocessed_csv": str(combined_postprocessed_path),
            "canonical_rows": len(combined_canonical_rows),
            "stage_meta_rows": len(combined_stage_meta_rows),
            "postprocessed_rows": len(combined_postprocessed_rows),
        }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
