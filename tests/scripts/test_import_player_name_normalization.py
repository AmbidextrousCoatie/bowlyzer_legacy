"""Import player name normalization rules from annotated MULTI_NAME audit CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from data_access.player_name_normalization_config import (
    apply_player_name_normalization,
    is_same_person_name_group,
    load_player_name_remapping_rules,
)
from scripts.import_player_name_normalization_from_audit import build_config_from_audit_csv


def _write_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "issue_type",
        "player_name",
        "player_id",
        "autoresolve_rule",
        "proposed_name",
        "manual_rule",
        "assigned name",
        "assigned_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_build_config_from_audit_csv(tmp_path: Path) -> None:
    rows = [
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Hug Jürgen",
            "player_id": "3175",
            "manual_rule": "dbu_id",
            "assigned name": "Hug, Jürgen",
        },
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Hug, Jürgen",
            "player_id": "3175",
            "manual_rule": "dbu_id",
        },
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Bodirsky, Claudia",
            "player_id": "7062",
            "manual_rule": "same person",
        },
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Lehner, Claudia",
            "player_id": "7062",
            "manual_rule": "same person",
        },
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Köse Sahin",
            "player_id": "16002",
            "autoresolve_rule": "name_reassembly",
            "proposed_name": "Köse, Sahin",
        },
    ]
    csv_path = tmp_path / "names.csv"
    _write_csv(csv_path, rows)
    config = build_config_from_audit_csv(csv_path)
    assert len(config["manual_resolutions"]["dbu_id"]) == 1
    assert config["manual_resolutions"]["dbu_id"][0]["replace"]["player_name"] == "Hug, Jürgen"
    assert len(config["manual_resolutions"]["same_person"]) == 1
    assert config["autoresolve_remappings"][0]["source"] == "name_reassembly"


def test_apply_name_normalization_from_config(tmp_path: Path) -> None:
    config = {
        "version": 1,
        "manual_resolutions": {
            "dbu_id": [
                {
                    "match": {"player_name": "Hug Jürgen", "player_id": "3175"},
                    "replace": {"player_name": "Hug, Jürgen"},
                    "source": "dbu_id",
                }
            ],
            "missing_id": [],
            "same_person": [
                {
                    "player_id": "7062",
                    "player_names": ["Bodirsky, Claudia", "Lehner, Claudia"],
                }
            ],
        },
        "autoresolve_remappings": [],
    }
    cfg_path = tmp_path / "player_name_normalization.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    import pandas as pd

    from data_access.schema import Columns

    df = pd.DataFrame(
        [
            {Columns.player_name: "Hug Jürgen", Columns.player_id: "3175"},
            {Columns.player_name: "Bodirsky, Claudia", Columns.player_id: "7062"},
            {Columns.player_name: "Lehner, Claudia", Columns.player_id: "7062"},
        ]
    )
    out, stats = apply_player_name_normalization(df, config_path=cfg_path)
    assert out.loc[0, Columns.player_name] == "Hug, Jürgen"
    assert int(stats[load_player_name_remapping_rules(cfg_path)[0].label()]) == 1
    assert is_same_person_name_group(
        "7062",
        {"Bodirsky, Claudia", "Lehner, Claudia"},
        config_path=cfg_path,
    )
