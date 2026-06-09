"""Schema v2 helpers for published league rows."""

from __future__ import annotations

import pandas as pd

from data_access.competition_schema import (
    LEAGUE_EVENT_TYPE,
    TOURNAMENT_EVENT_TYPE,
    apply_league_competition_schema_v2,
    apply_tournament_competition_schema_v2,
    club_name_from_team,
    ensure_competition_core_columns_for_read,
)
from data_access.schema import Columns


def test_club_name_from_team_strips_trailing_number():
    assert club_name_from_team("Donaubowler Regensburg 2") == "Donaubowler Regensburg"
    assert club_name_from_team("BayL Male 1") == "BayL Male"
    assert club_name_from_team("NoNumber") == "NoNumber"


def test_apply_league_competition_schema_v2_on_publish():
    df = pd.DataFrame(
        {
            "Season": ["24/25"],
            "League": ["BayL"],
            "Team": ["Donaubowler Regensburg 2"],
            "Player": ["Alice"],
        }
    )
    out = apply_league_competition_schema_v2(df)
    assert "League" not in out.columns
    assert out.loc[0, Columns.event] == "BayL"
    assert out.loc[0, Columns.event_type] == LEAGUE_EVENT_TYPE
    assert out.loc[0, Columns.club] == "Donaubowler Regensburg"


def test_ensure_competition_core_columns_for_read_legacy_league():
    df = pd.DataFrame(
        {
            "Season": ["10/11"],
            "League": ["KL N1"],
            "Team": ["Club Alpha 1"],
            "Player": ["Bob"],
        }
    )
    out = ensure_competition_core_columns_for_read(df)
    assert out.loc[0, Columns.event] == "KL N1"
    assert out.loc[0, Columns.event_type] == LEAGUE_EVENT_TYPE
    assert out.loc[0, Columns.club] == "Club Alpha"
    assert "League" in out.columns


def test_read_compat_flags_tournament_rows_when_input_data_is_boolean():
    """League Parquet normalizes Input Data to boolean before runtime concat."""
    from app.services.player_service import PlayerService

    league = pd.DataFrame(
        {
            Columns.season: ["24/25"],
            Columns.event: ["BayL"],
            Columns.event_type: ["league"],
            Columns.player_name: ["League Player"],
            Columns.input_data: pd.array([True], dtype="boolean"),
            Columns.computed_data: pd.array([False], dtype="boolean"),
            Columns.score: [180],
        }
    )
    tournament = pd.DataFrame(
        {
            Columns.season: ["25/26"],
            Columns.event: ["Clubmeisterschaft"],
            Columns.event_type: ["tournament"],
            Columns.player_name: ["Tournament Player"],
            Columns.input_data: pd.array([pd.NA], dtype="boolean"),
            Columns.computed_data: pd.array([pd.NA], dtype="boolean"),
            Columns.score: [200],
        }
    )
    combined = pd.concat([league, tournament], ignore_index=True)
    out = ensure_competition_core_columns_for_read(combined)
    safe = PlayerService._safe_player_rows(out)
    assert len(safe) == 2


def test_read_compat_flags_tournament_rows_after_league_concat():
    """Runtime merge leaves tournament Input Data null until read normalization."""
    from app.services.player_service import PlayerService

    league = pd.DataFrame(
        {
            Columns.season: ["24/25"],
            Columns.event: ["BayL"],
            Columns.event_type: ["league"],
            Columns.player_name: ["League Player"],
            Columns.input_data: ["True"],
            Columns.computed_data: ["False"],
            Columns.score: [180],
        }
    )
    tournament = pd.DataFrame(
        {
            Columns.season: ["25/26"],
            Columns.event: ["Clubmeisterschaft"],
            Columns.event_type: ["tournament"],
            Columns.player_name: ["Tournament Player"],
            Columns.score: [200],
        }
    )
    combined = pd.concat([league, tournament], ignore_index=True)
    out = ensure_competition_core_columns_for_read(combined)
    safe = PlayerService._safe_player_rows(out)
    assert len(safe) == 2


def test_tournament_player_row_flags_for_spieler_filter():
    from app.services.player_service import PlayerService

    df = pd.DataFrame(
        {
            Columns.season: ["25/26"],
            Columns.event: ["Clubmeisterschaft"],
            Columns.event_type: ["tournament"],
            Columns.player_name: ["Alice"],
            Columns.score: [200],
        }
    )
    out = apply_tournament_competition_schema_v2(df)
    assert out.loc[0, Columns.input_data] == "True"
    assert out.loc[0, Columns.computed_data] == "False"
    kept = PlayerService._safe_player_rows(out)
    assert len(kept) == 1


def test_apply_tournament_competition_schema_v2_on_publish():
    df = pd.DataFrame(
        {
            "Season": ["25/26"],
            "Event Type": ["tournament"],
            "Event Name": ["Südbayerische Meisterschaft"],
            "Player": ["Alice"],
            "Club": ["Donaubowler Regensburg"],
        }
    )
    out = apply_tournament_competition_schema_v2(df)
    assert "Event Name" not in out.columns
    assert out.loc[0, Columns.event] == "Südbayerische Meisterschaft"
    assert out.loc[0, Columns.event_type] == TOURNAMENT_EVENT_TYPE


def test_ensure_competition_core_columns_for_read_legacy_tournament():
    df = pd.DataFrame(
        {
            "Season": ["25/26"],
            "Event Name": ["Clubmeisterschaft Donaubowler 2026"],
            "Player": ["Bob"],
        }
    )
    out = ensure_competition_core_columns_for_read(df)
    assert out.loc[0, Columns.event] == "Clubmeisterschaft Donaubowler 2026"
    assert out.loc[0, Columns.event_type] == TOURNAMENT_EVENT_TYPE
    assert "Event Name" in out.columns
