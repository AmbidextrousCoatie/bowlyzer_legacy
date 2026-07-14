from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.cav_inspector import (
    CavInspector,
    add_file_to_config,
    filter_substring,
    load_config,
    load_dataframe,
    parse_filter_args,
    resolve_column_tokens,
    save_config,
    slice_summary,
)


@pytest.fixture
def sample_league_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Season": ["2023/24", "2023/24", "2024/25"],
            "Event Type": ["league", "league", "tournament"],
            "Player ID": ["1", "2", "1"],
            "Player": ["Alice", "Bob", "Alice"],
            "Score": [200, 180, 210],
        }
    )


def test_resolve_column_tokens_by_id_and_name() -> None:
    columns = ["Season", "Player", "Score"]
    assert resolve_column_tokens(columns, ["1", "score"]) == ["Season", "Score"]


def test_resolve_column_tokens_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown column"):
        resolve_column_tokens(["Season"], ["missing"])


def test_slice_summary_reports_core_stats(sample_league_df: pd.DataFrame) -> None:
    text = slice_summary(sample_league_df, source_label="test")
    assert "3 rows x 5 cols" in text
    assert "2023/24 .. 2024/25" in text
    assert "league=2" in text
    assert "tournament=1" in text
    assert "Games (rows): 3" in text
    assert "Unique players (Player ID): 2" in text


def test_load_dataframe_csv_semicolon(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("Season;Player\n2023/24;Alice\n", encoding="utf-8")
    df = load_dataframe(path)
    assert list(df.columns) == ["Season", "Player"]
    assert len(df) == 1


def test_load_dataframe_csv_comma(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    df = load_dataframe(path)
    assert list(df.columns) == ["a", "b"]


def test_load_dataframe_parquet(tmp_path: Path, sample_league_df: pd.DataFrame) -> None:
    path = tmp_path / "sample.parquet"
    sample_league_df.to_parquet(path, index=False)
    df = load_dataframe(path)
    assert len(df) == 3


def test_parse_filter_args() -> None:
    assert parse_filter_args('2 "Feller"') == ("2", "Feller")
    assert parse_filter_args("Player Feller") == ("Player", "Feller")


def test_filter_substring_case_insensitive(sample_league_df: pd.DataFrame) -> None:
    filtered = filter_substring(sample_league_df, "Player", "ali")
    assert len(filtered) == 2
    assert set(filtered["Player"]) == {"Alice"}


def test_inspector_filter_command(sample_league_df: pd.DataFrame) -> None:
    inspector = CavInspector()
    inspector.df = sample_league_df.copy()
    inspector.source_label = "memory"
    inspector.filter_slice("Player", "Bob")
    assert len(inspector.df) == 1
    assert inspector.df.iloc[0]["Player"] == "Bob"


def test_inspector_select_and_unique(sample_league_df: pd.DataFrame) -> None:
    inspector = CavInspector()
    inspector.df = sample_league_df.copy()
    inspector.source_label = "memory"
    inspector.select_columns(["1", "4"])
    assert list(inspector.df.columns) == ["Season", "Player"]
    inspector.unique_slice(["Season", "Player"])
    assert len(inspector.df) == 3


def test_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "cav_inspector_files.json"
    monkeypatch.setattr("scripts.cav_inspector.CONFIG_PATH", config_path)
    monkeypatch.setattr("scripts.cav_inspector.REPO_ROOT", tmp_path)

    target = tmp_path / "database/data/custom.parquet"
    target.parent.mkdir(parents=True)
    pd.DataFrame({"a": [1]}).to_parquet(target, index=False)

    add_file_to_config("Custom", target)
    config = load_config()
    assert config["files"][-1]["path"] == "database/data/custom.parquet"

    add_file_to_config("Custom renamed", target)
    config = load_config()
    assert config["files"][-1]["label"] == "Custom renamed"
    assert len(config["files"]) == 1

    save_config({"schema_version": 1, "files": []})
    assert json.loads(config_path.read_text(encoding="utf-8"))["files"] == []
