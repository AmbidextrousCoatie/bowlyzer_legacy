"""Import player ID normalization rules from annotated audit CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from data_access.player_id_name_normalization import (
    is_different_person_name_group,
    load_player_id_name_remapping_rules,
)
from scripts.audit_player_id_names import ISSUE_SAME_NAME, audit_player_id_names
from scripts.import_player_id_normalization_from_audit import build_config_from_audit_csv


def _write_csv(path: Path, rows: list[dict]) -> None:
    headers = [
        "issue_type",
        "player_name",
        "player_id",
        "autoresolve_rule",
        "proposed_id",
        "manual_rule",
        "assigned_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def test_build_config_from_audit_csv(tmp_path: Path) -> None:
    rows = [
        {
            "issue_type": "same_name_different_ids",
            "player_name": "Seltmann, Dominic",
            "player_id": "26504",
            "autoresolve_rule": "",
            "proposed_id": "",
            "manual_rule": "dbu_id",
            "assigned_id": "25604",
        },
        {
            "issue_type": "same_name_different_ids",
            "player_name": "Seltmann, Dominic",
            "player_id": "25604",
            "manual_rule": "dbu_id",
        },
        {
            "issue_type": "same_name_different_ids",
            "player_name": "Müller, Angelika",
            "player_id": "12850",
            "manual_rule": "different_person",
        },
        {
            "issue_type": "same_name_different_ids",
            "player_name": "Müller, Angelika",
            "player_id": "25571",
            "manual_rule": "different_person",
        },
        {
            "issue_type": "same_name_different_ids",
            "player_name": "Dummy, Player",
            "player_id": "11111",
            "autoresolve_rule": "placeholder",
            "proposed_id": "25604",
        },
    ]
    csv_path = tmp_path / "audit.csv"
    _write_csv(csv_path, rows)
    config = build_config_from_audit_csv(csv_path)
    assert len(config["manual_resolutions"]["dbu_id"]) == 1
    assert config["manual_resolutions"]["dbu_id"][0]["replace"]["player_id"] == "25604"
    assert len(config["manual_resolutions"]["different_person"]) == 1
    assert config["autoresolve_remappings"][0]["source"] == "placeholder"


def test_build_config_imports_same_id_placeholder_rows(tmp_path: Path) -> None:
    rows = [
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Erhard, Hannelore",
            "player_id": "99999",
            "autoresolve_rule": "placeholder",
            "proposed_id": "25977",
        },
        {
            "issue_type": "same_id_name_variants",
            "player_name": "Gulvadi, Sanat",
            "player_id": "38429",
            "autoresolve_rule": "placeholder",
            "proposed_id": "38424",
        },
    ]
    csv_path = tmp_path / "audit.csv"
    _write_csv(csv_path, rows)
    config = build_config_from_audit_csv(csv_path)
    assert len(config["autoresolve_remappings"]) == 2
    by_name = {row["match"]["player_name"]: row for row in config["autoresolve_remappings"]}
    assert by_name["Erhard, Hannelore"]["replace"]["player_id"] == "25977"
    assert by_name["Gulvadi, Sanat"]["replace"]["player_id"] == "38424"


def test_audit_zero_same_name_after_normalization(tmp_path: Path, monkeypatch) -> None:
    league = tmp_path / "league.csv"
    with league.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Season", "Player", "Player ID", "Input Data", "Computed Data"],
            delimiter=";",
        )
        writer.writeheader()
        for _ in range(5):
            writer.writerow(
                {
                    "Season": "24/25",
                    "Player": "Seltmann, Dominic",
                    "Player ID": "26504",
                    "Input Data": "True",
                    "Computed Data": "False",
                }
            )
        for _ in range(20):
            writer.writerow(
                {
                    "Season": "24/25",
                    "Player": "Seltmann, Dominic",
                    "Player ID": "25604",
                    "Input Data": "True",
                    "Computed Data": "False",
                }
            )
        writer.writerow(
            {
                "Season": "11/12",
                "Player": "Müller, Angelika",
                "Player ID": "12850",
                "Input Data": "True",
                "Computed Data": "False",
            }
        )
        writer.writerow(
            {
                "Season": "12/13",
                "Player": "Müller, Angelika",
                "Player ID": "25571",
                "Input Data": "True",
                "Computed Data": "False",
            }
        )

    cfg = tmp_path / "rules.json"
    cfg.write_text(
        """
{
  "version": 2,
  "manual_resolutions": {
    "dbu_id": [
      {
        "match": {"player_name": "Seltmann, Dominic", "player_id": "26504"},
        "replace": {"player_id": "25604"},
        "source": "dbu_id"
      }
    ],
    "different_person": [
      {"player_name": "Müller, Angelika", "player_ids": ["12850", "25571"]}
    ]
  },
  "autoresolve_remappings": []
}
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "data_access.player_id_name_normalization.DEFAULT_CONFIG_PATH",
        cfg,
    )

    raw = audit_player_id_names(league, apply_normalization=False)
    assert any(c.issue_type == ISSUE_SAME_NAME for c in raw)

    resolved = audit_player_id_names(league, apply_normalization=True)
    assert not any(c.issue_type == ISSUE_SAME_NAME for c in resolved)
    assert is_different_person_name_group("Müller, Angelika", {"12850", "25571"}, config_path=cfg)
    assert len(load_player_id_name_remapping_rules(cfg)) == 1
