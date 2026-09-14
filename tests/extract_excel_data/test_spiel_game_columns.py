"""Spiel 1..n headers are the only valid game columns; Gesamt is never a game."""

from __future__ import annotations

import pandas as pd

from scripts.data.extract_excel_data import (
    _effective_max_games_per_week,
    _max_games_from_team_count,
    detect_spiel_game_columns,
    dict_of_match_numbers,
    extract_team_players,
)


def _team_block(
    *,
    player_name: str,
    player_id: int,
    game_scores: list[int],
    opponents: list[str],
    spiel_7_pins: int | None = None,
    spiel_7_opponent: str | None = None,
    template_games: int = 9,
) -> pd.DataFrame:
    """10-team / 9-game Erfassung template after slicing from Team-Nr."""
    df = pd.DataFrame([[None] * 24] * 30)
    df.iloc[0, 0] = "Team-Nr."
    df.iloc[2, 0] = "Absolut Sports 2"
    df.iloc[4, 0] = "Spieler"
    df.iloc[5, 0] = "Name"
    df.iloc[5, 1] = "RL-Nr."
    df.iloc[6, 0] = player_name
    df.iloc[6, 1] = player_id

    for game in range(1, template_games + 1):
        pins_col = 2 * game
        pkt_col = pins_col + 1
        df.iloc[4, pins_col] = f"Spiel {game}"
        df.iloc[5, pins_col] = "Pins"
        df.iloc[5, pkt_col] = "Pkt."

    gesamt_col = 2 * (template_games + 1)
    df.iloc[4, gesamt_col] = "Gesamt"
    df.iloc[5, gesamt_col] = "Pins"
    df.iloc[5, gesamt_col + 1] = "Pkt."

    team_game_totals = [0] * template_games
    for idx, (score, opponent) in enumerate(zip(game_scores, opponents)):
        pins_col = 2 * (idx + 1)
        df.iloc[6, pins_col] = score
        df.iloc[6, pins_col + 1] = 1
        df.iloc[22, pins_col] = opponent
        team_game_totals[idx] = score + 400
        df.iloc[18, pins_col] = team_game_totals[idx]
        df.iloc[18, pins_col + 1] = 1

    df.iloc[6, gesamt_col] = sum(game_scores)
    df.iloc[18, 0] = "Gesamt"
    df.iloc[18, gesamt_col] = sum(team_game_totals)

    if spiel_7_pins is not None:
        df.iloc[6, 14] = spiel_7_pins
        df.iloc[6, 15] = 5
        df.iloc[18, 14] = 3920
        df.iloc[18, 15] = 9
        df.iloc[22, 16] = "Spielzettel wurde: richtig komplett leserlich ausgefüllt:"
    if spiel_7_opponent is not None:
        df.iloc[22, 14] = spiel_7_opponent
    return df


TEAM_INFO = {
    "team_name": "Absolut Sports 2",
    "location": "Regensburg Superbowl",
    "week": "1",
    "opponent": "Pfaffenhofen 2",
}

GAME_SCORES = [177, 161, 180, 173, 214, 132]
OPPONENTS = [
    "Pfaffenhofen 2",
    "BC EMAX 6",
    "LA Bowling Landshut 2",
    "Pfaffenhofen 2",
    "BC EMAX 6",
    "LA Bowling Landshut 2",
]


def test_detect_spiel_game_columns_stops_at_gesamt_and_drops_unused_template_slots() -> None:
    df = _team_block(
        player_name="Faltermeier Robert",
        player_id=38472,
        game_scores=GAME_SCORES,
        opponents=OPPONENTS,
        spiel_7_pins=sum(GAME_SCORES),
    )
    games = detect_spiel_game_columns(df)
    assert [game_no for game_no, _, _ in games] == [1, 2, 3, 4, 5, 6]
    assert all(pins_col <= 13 for _, pins_col, _ in games)


def test_detect_spiel_game_columns_keeps_full_nine_game_week() -> None:
    scores = [150, 160, 170, 180, 190, 200, 155, 165, 175]
    opponents = [f"Team {n}" for n in range(1, 10)]
    df = _team_block(
        player_name="Stockmann Uwe",
        player_id=38149,
        game_scores=scores,
        opponents=opponents,
    )
    games = detect_spiel_game_columns(df)
    assert [game_no for game_no, _, _ in games] == list(range(1, 10))


def test_detect_spiel_game_columns_drops_spiel_7_when_subs_copy_a_real_game_score() -> None:
    df = _team_block(
        player_name="Faltermeier Robert",
        player_id=38472,
        game_scores=GAME_SCORES,
        opponents=OPPONENTS,
        spiel_7_pins=156,
    )
    df.iloc[9, 0] = "Rusev Pavel"
    df.iloc[9, 1] = 38312
    df.iloc[9, 14] = 156
    df.iloc[9, 15] = 1
    games = detect_spiel_game_columns(df)
    assert [game_no for game_no, _, _ in games] == [1, 2, 3, 4, 5, 6]


def test_extract_team_players_ignores_gesamt_sums_written_under_spiel_7() -> None:
    dict_of_match_numbers.clear()
    df = _team_block(
        player_name="Faltermeier Robert",
        player_id=38472,
        game_scores=GAME_SCORES,
        opponents=OPPONENTS,
        spiel_7_pins=sum(GAME_SCORES),
        spiel_7_opponent="Spielzettel wurde: richtig komplett leserlich ausgefüllt:",
    )
    rows = extract_team_players(
        df,
        TEAM_INFO,
        "25/26",
        "KL S1",
        4,
        "2025-09-13",
        max_games_per_week=9,
    )
    player_rows = [row for row in rows if row["Player"] == "Faltermeier Robert"]
    team_rows = [row for row in rows if row["Player"] == "Team Total"]
    assert [row["Round Number"] for row in player_rows] == [1, 2, 3, 4, 5, 6]
    assert [row["Score"] for row in player_rows] == GAME_SCORES
    assert all(row["Score"] <= 300 for row in player_rows)
    assert all("Spielzettel" not in str(row["Opponent"]) for row in player_rows)
    assert all(row["Score"] <= 1200 for row in team_rows)
    assert max(row["Round Number"] for row in rows) == 6


def test_extract_team_players_caps_four_team_double_round_robin_even_if_spiel_7_has_a_league_opponent() -> None:
    dict_of_match_numbers.clear()
    df = _team_block(
        player_name="Faltermeier Robert",
        player_id=38472,
        game_scores=GAME_SCORES,
        opponents=OPPONENTS,
        spiel_7_pins=156,
        spiel_7_opponent="Pfaffenhofen 2",
    )
    known = ["Absolut Sports 2", "Pfaffenhofen 2", "BC EMAX 6", "LA Bowling Landshut 2"]
    rows = extract_team_players(
        df,
        TEAM_INFO,
        "25/26",
        "KL S1",
        4,
        "2025-09-13",
        max_games_per_week=9,
        known_team_names=known,
        number_of_teams=4,
    )
    assert max(row["Round Number"] for row in rows) == 6
    assert all(row["Score"] <= 300 for row in rows if row["Player"] != "Team Total")


def test_six_team_league_keeps_five_games_and_drops_template_tail() -> None:
    scores = [150, 160, 170, 180, 190]
    opponents = [
        "Team B",
        "Team C",
        "Team D",
        "Team E",
        "Team F",
    ]
    df = _team_block(
        player_name="Stockmann Uwe",
        player_id=38149,
        game_scores=scores,
        opponents=opponents,
        spiel_7_pins=sum(scores),
    )
    known = ["Team A", "Team B", "Team C", "Team D", "Team E", "Team F"]
    games = detect_spiel_game_columns(df, known_team_names=known)
    assert [game_no for game_no, _, _ in games] == [1, 2, 3, 4, 5]


def test_max_games_from_team_count_is_double_round_robin() -> None:
    assert _max_games_from_team_count(4) == 6
    assert _max_games_from_team_count(6) == 10
    assert _max_games_from_team_count(8) == 14
    assert _max_games_from_team_count(10) == 18
    assert _effective_max_games_per_week(9, 4) == 6
    assert _effective_max_games_per_week(9, 10) == 9
