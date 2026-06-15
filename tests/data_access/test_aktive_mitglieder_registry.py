"""Aktive Mitglieder registry import."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_access.aktive_mitglieder_registry import (
    DEFAULT_AKTIVE_MIN_SEASON,
    canonical_name_from_combined,
    canonical_name_from_split,
    discover_local_aktive_workbooks,
    locate_member_header,
    resolve_aktive_min_season,
    row_to_aktive_player,
    build_registry_dataframe_from_aktive,
)


def test_locate_split_name_header() -> None:
    frame = pd.DataFrame(
        [
            ["Liste der aktiven Mitglieder", None, None],
            ["Stand", None, None],
            ["EDV-Nr.", "Nachname", "Vorname", "Zusatz"],
            ["38175", "Bühler", "Lars", None],
        ]
    )
    header_idx, layout, columns = locate_member_header(frame)
    assert header_idx == 2
    assert layout == "split"
    assert columns["nachname"] == 1


def test_locate_combined_name_header() -> None:
    frame = pd.DataFrame(
        [
            ["Datei der aktiven Mitglieder", None, None],
            ["EDV-Nr", "Pass-Nr", "Name"],
            ["10101", "875322", "Brown Mike"],
        ]
    )
    header_idx, layout, columns = locate_member_header(frame)
    assert header_idx == 1
    assert layout == "combined"
    assert columns["name"] == 2


def test_row_to_aktive_player_split_and_combined() -> None:
    split_cols = {"edvnr": 0, "nachname": 1, "vorname": 2, "zusatz": 3}
    split_row = row_to_aktive_player(
        ["7299", "König", "Erich", ""],
        layout="split",
        columns=split_cols,
    )
    assert split_row is not None
    assert split_row.player_id == "7299"
    assert split_row.canonical_name == "König, Erich"

    combined_cols = {"edvnr": 0, "name": 2}
    combined_row = row_to_aktive_player(
        ["10101", "875322", "Brown Mike"],
        layout="combined",
        columns=combined_cols,
    )
    assert combined_row is not None
    assert combined_row.player_id == "10101"
    assert combined_row.canonical_name == "Brown, Mike"


def test_canonical_name_from_split_with_zusatz() -> None:
    assert canonical_name_from_split("Müller", "Anna", "Jr.") == "Müller, Anna Jr."


def test_canonical_name_from_combined_family_given() -> None:
    assert canonical_name_from_combined("Völlmerk Oliver") == "Völlmerk, Oliver"
    assert canonical_name_from_combined("Brown Mike") == "Brown, Mike"


def test_resolve_aktive_min_season_defaults_and_overrides() -> None:
    assert resolve_aktive_min_season(None) == DEFAULT_AKTIVE_MIN_SEASON
    assert resolve_aktive_min_season("2007-08") == "2007-08"
    assert resolve_aktive_min_season("") is None


def test_discover_local_respects_min_season(tmp_path: Path) -> None:
    for season in ("2004-05", "2007-08", "2008-09"):
        season_dir = tmp_path / f"saison{season}" / "allgemein"
        season_dir.mkdir(parents=True)
        (season_dir / f"aktive_{season}.xls").write_bytes(season.encode())

    all_seasons = discover_local_aktive_workbooks(tmp_path)
    assert [season for season, _ in all_seasons] == ["2004-05", "2007-08", "2008-09"]

    from_0808 = discover_local_aktive_workbooks(tmp_path, min_season="2007-08")
    assert [season for season, _ in from_0808] == ["2007-08", "2008-09"]

    from_0809 = discover_local_aktive_workbooks(tmp_path, min_season="2008-09")
    assert [season for season, _ in from_0809] == ["2008-09"]


def test_discover_local_prefers_endstand(tmp_path: Path) -> None:
    season_dir = tmp_path / "saison2013-14" / "allgemein"
    season_dir.mkdir(parents=True)
    interim = season_dir / "aktive_130313.xls"
    endstand = season_dir / "aktive_Endstand_140630.xls"
    interim.write_bytes(b"interim")
    endstand.write_bytes(b"endstand")

    found = discover_local_aktive_workbooks(tmp_path)
    assert found == [("2013-14", endstand)]


def test_build_registry_accumulates_aliases_across_seasons(tmp_path: Path, monkeypatch) -> None:
    old_path = tmp_path / "saison2010-11" / "allgemein" / "aktive_110704.xls"
    new_path = tmp_path / "saison2011-12" / "allgemein" / "aktive_Endstand_120703.xls"
    old_path.parent.mkdir(parents=True)
    new_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")

    from data_access import aktive_mitglieder_registry as mod

    def fake_parse(path: Path, *, season: str = ""):
        if season == "2010-11":
            return [mod.AktivePlayerRow("1234", "Voigt, Thomas", season)]
        return [mod.AktivePlayerRow("1234", "Vogt, Thomas", season)]

    monkeypatch.setattr(mod, "parse_aktive_workbook", fake_parse)

    registry_df, stats = build_registry_dataframe_from_aktive(
        tmp_path,
        updated_at="2026-06-03T00:00:00+00:00",
    )
    assert stats.workbooks_parsed == 2
    assert len(registry_df) == 1
    row = registry_df.iloc[0]
    assert row["player_id"] == "1234"
    assert row["canonical_name"] == "Vogt, Thomas"
    assert "Voigt, Thomas" in row["aliases"]


def test_build_registry_from_aktive_min_season(tmp_path: Path, monkeypatch) -> None:
    for season in ("2004-05", "2007-08"):
        season_dir = tmp_path / f"saison{season}" / "allgemein"
        season_dir.mkdir(parents=True)
        (season_dir / f"aktive_{season}.xls").write_bytes(season.encode())

    from data_access import aktive_mitglieder_registry as mod

    def fake_parse(path: Path, *, season: str = ""):
        if season == "2004-05":
            return [mod.AktivePlayerRow("111708", "Windsheimer, Friedrich", season)]
        return [mod.AktivePlayerRow("7762", "Windsheimer, Friedrich", season)]

    monkeypatch.setattr(mod, "parse_aktive_workbook", fake_parse)

    registry_df, stats = build_registry_dataframe_from_aktive(
        tmp_path,
        updated_at="2026-06-03T00:00:00+00:00",
        min_season="2007-08",
    )
    assert stats.workbooks_parsed == 1
    assert len(registry_df) == 1
    assert registry_df.iloc[0]["player_id"] == "7762"
