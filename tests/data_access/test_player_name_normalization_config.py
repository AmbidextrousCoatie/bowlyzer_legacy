"""Player name normalization config load/apply."""

from __future__ import annotations

import json
from pathlib import Path

from data_access.player_name_normalization_config import (
    apply_player_name_normalization,
    is_same_person_name_group,
    load_player_name_normalization_config,
)


def test_missing_id_remap(tmp_path: Path) -> None:
    config = {
        "version": 1,
        "manual_resolutions": {
            "dbu_id": [],
            "missing_id": [
                {
                    "match": {"player_name": "Müller, Anna", "player_id": "11111"},
                    "replace": {"player_id": "22222"},
                    "source": "missing_id",
                }
            ],
            "same_person": [],
        },
        "autoresolve_remappings": [],
    }
    cfg_path = tmp_path / "player_name_normalization.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")

    import pandas as pd

    from data_access.schema import Columns

    df = pd.DataFrame([{Columns.player_name: "Müller, Anna", Columns.player_id: "11111"}])
    out, stats = apply_player_name_normalization(df, config_path=cfg_path)
    assert out.loc[0, Columns.player_id] == "22222"
    assert sum(stats.values()) == 1


def test_same_person_marriage_and_nickname_groups() -> None:
    cfg = load_player_name_normalization_config()
    assert is_same_person_name_group(
        "38397",
        {"Schwartz, Janin", "Theisen, Janin"},
    )
    assert is_same_person_name_group(
        "16270",
        {"Feuerlein, Andreas", "Feuerlein, Andy"},
    )
    assert is_same_person_name_group(
        "38114",
        {"Hoppe, Oscar", "Hoppe, Oswald"},
    )
    assert is_same_person_name_group(
        "38555",
        {"Daffner, Regina", "Gahr, Regina", "Gahr Regina"},
    )
    assert not is_same_person_name_group(
        "38397",
        {"Schwartz, Janin", "Someone, Else"},
    )
