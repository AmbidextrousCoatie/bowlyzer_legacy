"""Curated player ID / name remappings from JSON config."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_access.player_id_name_normalization import (
    PlayerIdNameRemapRule,
    apply_player_id_name_normalization,
    load_player_id_name_remapping_rules,
)
from data_access.schema import Columns


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                Columns.season: "14/15",
                Columns.player_name: "Seltmann, Dominic",
                Columns.player_id: "26504",
            },
            {
                Columns.season: "24/25",
                Columns.player_name: "Seltmann, Dominik",
                Columns.player_id: "25604",
            },
            {
                Columns.season: "08/09",
                Columns.player_name: "Rotter, Mark-Roland",
                Columns.player_id: "16005",
            },
        ]
    )


def test_apply_remaps_only_exact_combo(tmp_path: Path) -> None:
    cfg = tmp_path / "rules.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "remappings": [
                    {
                        "match": {"player_id": "26504", "player_name": "Seltmann, Dominic"},
                        "replace": {"player_id": "25604", "player_name": "Seltmann, Dominik"},
                    },
                    {
                        "match": {"player_id": "16005", "player_name": "Rotter, Mark-Roland"},
                        "replace": {"player_id": "16010"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    rules = load_player_id_name_remapping_rules(cfg)
    out, stats = apply_player_id_name_normalization(_frame(), rules)
    assert stats[rules[0].label()] == 1
    assert stats[rules[1].label()] == 1
    row0 = out.iloc[0]
    assert row0[Columns.player_id] == "25604"
    assert row0[Columns.player_name] == "Seltmann, Dominik"
    row2 = out.iloc[2]
    assert row2[Columns.player_id] == "16010"
    assert row2[Columns.player_name] == "Rotter, Mark-Roland"
    # Unrelated row untouched
    assert out.iloc[1][Columns.player_id] == "25604"


def test_load_rejects_rule_without_replace_fields(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.json"
    cfg.write_text(
        json.dumps(
            {
                "remappings": [
                    {
                        "match": {"player_id": "1", "player_name": "A"},
                        "replace": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    try:
        load_player_id_name_remapping_rules(cfg)
    except ValueError as exc:
        assert "replace needs" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_apply_with_empty_rules_is_noop() -> None:
    out, stats = apply_player_id_name_normalization(_frame(), [])
    assert stats == {}
    assert out.equals(_frame())


def test_rule_label() -> None:
    rule = PlayerIdNameRemapRule(
        match_player_id="1",
        match_player_name="Alpha, A",
        replace_player_id="2",
        replace_player_name="Beta, B",
    )
    assert "Alpha, A" in rule.label()
    assert "id=2" in rule.label()
