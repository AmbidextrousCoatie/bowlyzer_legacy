"""Seeded elim + stepladder + BO3 finals bracket for Clubmeisterschaft."""

from __future__ import annotations

import pandas as pd

from app.services.tournament_service import (
    KO_BRACKET_FORMAT_ELIM_STEPLADDER,
    TournamentService,
)
from data_access.schema import Columns

SEASON = "25/26"
TOURNAMENT = "Clubmeisterschaft Donaubowler 2026"


def _row(
    *,
    round_name: str,
    round_number: int,
    game: int,
    player: str,
    score: int,
    handicap: int = 0,
    player_id: str = "",
) -> dict:
    return {
        Columns.season: SEASON,
        Columns.event_name: TOURNAMENT,
        Columns.round_number: round_number,
        Columns.round_name: round_name,
        Columns.game_number: game,
        Columns.player_name: player,
        Columns.player_id: player_id or player[:3].upper(),
        Columns.club: "Donaubowler",
        Columns.score: score,
        Columns.handicap: handicap,
    }


def _finale_df() -> pd.DataFrame:
    """
    Seeds: 1 Anna, 2 Ben, 3 Cara, 4 Dan, 5 Eva, 6 Finn

    Decision basis = handicap (Score + Handicap).

    Elim sequential (lowest each game):
      G0 inkl: Dan 210, Eva 211, Finn 205 → Finn out (6th)
      G1 inkl: Dan 268, Eva 199 → Eva out (5th); Dan advances
      (Finn has no G1 row — mirrors real Clubmeisterschaft sheet)

    SL1: Cara 217 vs Dan 235 → Dan
    SL2: Ben 219 vs Dan 232 → Dan
    Final BO3: Anna vs Dan → Anna wins 2-0
    """
    rows = [
        # Elim game 0 (3 players)
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Dan", score=200, handicap=10),
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Eva", score=200, handicap=11),
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Finn", score=181, handicap=24),
        # Elim game 1 (2 remaining)
        _row(round_name="KO Eliminierung", round_number=7, game=1, player="Dan", score=258, handicap=10),
        _row(round_name="KO Eliminierung", round_number=7, game=1, player="Eva", score=188, handicap=11),
        # SL1
        _row(round_name="KO Stepladder", round_number=8, game=2, player="Cara", score=213, handicap=4),
        _row(round_name="KO Stepladder", round_number=8, game=2, player="Dan", score=225, handicap=10),
        # SL2
        _row(round_name="KO Stepladder", round_number=8, game=3, player="Ben", score=215, handicap=4),
        _row(round_name="KO Stepladder", round_number=8, game=3, player="Dan", score=222, handicap=10),
        # Final BO3 (2-0)
        _row(round_name="KO-Finale", round_number=9, game=4, player="Anna", score=201, handicap=5),
        _row(round_name="KO-Finale", round_number=9, game=4, player="Dan", score=190, handicap=10),
        _row(round_name="KO-Finale", round_number=9, game=5, player="Anna", score=235, handicap=5),
        _row(round_name="KO-Finale", round_number=9, game=5, player="Dan", score=160, handicap=10),
    ]
    return pd.DataFrame(rows)


def test_ko_bracket_format_config() -> None:
    svc = TournamentService()
    assert svc._ko_bracket_format(SEASON, TOURNAMENT) == KO_BRACKET_FORMAT_ELIM_STEPLADDER
    assert svc._ko_decision_basis(SEASON, TOURNAMENT) == "handicap"


def test_elim_stepladder_bracket_payload() -> None:
    svc = TournamentService()
    df = _finale_df()
    svc._tournament_df_cache[svc._tournament_cache_key(SEASON, TOURNAMENT)] = df
    svc._ko_bracket_cache.clear()

    bracket = svc._build_ko_bracket_payload(SEASON, TOURNAMENT, df=df)
    assert bracket["ko_bracket_format"] == KO_BRACKET_FORMAT_ELIM_STEPLADDER
    assert bracket["ko_decision_basis"] == "handicap"

    by_key = {m["key"]: m for m in bracket["matches"]}
    assert "ELIM" in by_key
    assert "SL1" in by_key
    assert "SL2" in by_key
    assert "F" in by_key

    elim = by_key["ELIM"]
    assert elim["kind"] == "field"
    assert elim["phase"] == "elim"
    assert elim["decision_basis"] == "handicap"
    rounds = {r["key"]: r for r in elim["rounds"]}
    assert "ELIM1" in rounds
    assert "ELIM2" in rounds

    elim1 = rounds["ELIM1"]
    field1 = {p["name"]: p for p in elim1["field"]}
    assert field1["Finn"]["eliminated"] is True
    assert field1["Finn"]["place"] == 6
    assert field1["Finn"]["games"] == [205]
    assert field1["Dan"]["advances"] is True
    assert field1["Eva"]["advances"] is True

    elim2 = rounds["ELIM2"]
    field2 = {p["name"]: p for p in elim2["field"]}
    assert field2["Eva"]["eliminated"] is True
    assert field2["Eva"]["place"] == 5
    assert field2["Dan"]["advances"] is True
    assert field2["Dan"]["games"] == [268]
    assert elim2["advancer"] == "Dan"

    assert by_key["SL1"]["phase"] == "stepladder"
    assert by_key["SL1"]["series_mode"] == "single_game"
    assert by_key["SL1"]["loser_place"] == 4
    # pin_games are decision pins (inkl hdc): Cara 217 vs Dan 235
    assert by_key["SL1"]["pin_games"] == [[217, 235]] or by_key["SL1"]["pin_games"] == [[235, 217]]
    sl1_winner = by_key["SL1"]["side_a"]["name"] if by_key["SL1"]["winner"] == "a" else by_key["SL1"]["side_b"]["name"]
    assert sl1_winner == "Dan"
    sl1_loser_side = by_key["SL1"]["side_b"] if by_key["SL1"]["winner"] == "a" else by_key["SL1"]["side_a"]
    assert sl1_loser_side["place"] == 4
    assert sl1_loser_side["name"] == "Cara"

    sl2_winner = by_key["SL2"]["side_a"]["name"] if by_key["SL2"]["winner"] == "a" else by_key["SL2"]["side_b"]["name"]
    assert sl2_winner == "Dan"
    assert by_key["SL2"]["loser_place"] == 3
    sl2_loser_side = by_key["SL2"]["side_b"] if by_key["SL2"]["winner"] == "a" else by_key["SL2"]["side_a"]
    assert sl2_loser_side["place"] == 3

    assert by_key["F"]["phase"] == "final"
    assert by_key["F"]["series_mode"] == "bo3_pins"
    assert by_key["F"]["loser_place"] == 2
    assert by_key["F"]["side_a"]["games_won"] + by_key["F"]["side_b"]["games_won"] == 2
    fin_winner = by_key["F"]["side_a"]["name"] if by_key["F"]["winner"] == "a" else by_key["F"]["side_b"]["name"]
    assert fin_winner == "Anna"
    fin_loser = by_key["F"]["side_b"] if by_key["F"]["winner"] == "a" else by_key["F"]["side_a"]
    assert fin_loser["place"] == 2
    assert fin_loser["name"] == "Dan"

    places = {p["place"]: p["player"] for p in bracket["placements"]}
    assert places[1] == "Anna"
    assert places[2] == "Dan"
    assert places[3] == "Ben"
    assert places[4] == "Cara"
    assert places[5] == "Eva"
    assert places[6] == "Finn"


def test_handicap_can_flip_elim_vs_scratch() -> None:
    """Scratch-lowest is Finn; inkl-hdc-lowest is Eva — decisions use handicap."""
    svc = TournamentService()
    rows = [
        # Scratch: Finn 198 lowest. HDC: Eva 199 lowest (Finn 222, Dan 210).
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Dan", score=200, handicap=10),
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Eva", score=199, handicap=0),
        _row(round_name="KO Eliminierung", round_number=7, game=0, player="Finn", score=198, handicap=24),
        _row(round_name="KO Eliminierung", round_number=7, game=1, player="Dan", score=200, handicap=10),
        _row(round_name="KO Eliminierung", round_number=7, game=1, player="Finn", score=220, handicap=24),
        _row(round_name="KO Stepladder", round_number=8, game=2, player="Cara", score=200, handicap=4),
        _row(round_name="KO Stepladder", round_number=8, game=2, player="Finn", score=210, handicap=24),
        _row(round_name="KO Stepladder", round_number=8, game=3, player="Ben", score=200, handicap=4),
        _row(round_name="KO Stepladder", round_number=8, game=3, player="Finn", score=210, handicap=24),
        _row(round_name="KO-Finale", round_number=9, game=4, player="Anna", score=220, handicap=5),
        _row(round_name="KO-Finale", round_number=9, game=4, player="Finn", score=180, handicap=24),
        _row(round_name="KO-Finale", round_number=9, game=5, player="Anna", score=220, handicap=5),
        _row(round_name="KO-Finale", round_number=9, game=5, player="Finn", score=180, handicap=24),
    ]
    df = pd.DataFrame(rows)
    svc._tournament_df_cache[svc._tournament_cache_key(SEASON, TOURNAMENT)] = df
    svc._ko_bracket_cache.clear()
    bracket = svc._build_ko_bracket_payload(SEASON, TOURNAMENT, df=df)
    elim = next(m for m in bracket["matches"] if m["key"] == "ELIM")
    elim1 = next(r for r in elim["rounds"] if r["key"] == "ELIM1")
    field_by_name = {p["name"]: p for p in elim1["field"]}
    assert field_by_name["Eva"]["place"] == 6
    elim2 = next(r for r in elim["rounds"] if r["key"] == "ELIM2")
    assert elim2["advancer"] == "Finn"


def test_tournament_format_info_stepladder_label() -> None:
    svc = TournamentService()
    df = _finale_df()
    svc._tournament_df_cache[svc._tournament_cache_key(SEASON, TOURNAMENT)] = df
    info = svc.get_tournament_format_info(SEASON, TOURNAMENT)
    assert info["ko_bracket_format"] == KO_BRACKET_FORMAT_ELIM_STEPLADDER
    assert info["ko_decision_basis"] == "handicap"
    assert "Handicap" in info["ko_finale_series_label_de"]
    assert info["config"].get("ko_decision_basis") == "handicap"


def test_elim_stepladder_gesamt_orders_ko_places_first() -> None:
    """Overall standings: finals 1–6 first, then field by net average (inkl. HDC)."""
    from app.models.table_data import Column, ColumnGroup, TableData

    svc = TournamentService()
    bracket = {
        "ko_bracket_format": KO_BRACKET_FORMAT_ELIM_STEPLADDER,
        "placements": [
            {"place": 1, "player": "Anna"},
            {"place": 2, "player": "Dan"},
            {"place": 3, "player": "Ben"},
            {"place": 4, "player": "Cara"},
            {"place": 5, "player": "Eva"},
            {"place": 6, "player": "Finn"},
        ],
        "matches": [{"key": "F"}],
    }
    # Layout mirrors scratch/net Gesamt: … total_net, avg_net, …, scratch avg last.
    # Gus has highest scratch avg but lower net avg than Hal → Hal must rank above Gus.
    columns = [
        ColumnGroup(
            title="",
            columns=[
                Column(title="#", field="rank"),
                Column(title="Player", field="player"),
                Column(title="HDC", field="handicap"),
            ],
        ),
        ColumnGroup(
            title="Net",
            columns=[
                Column(title="Total Net", field="total_net"),
                Column(title="Avg Net", field="avg_net"),
            ],
        ),
        ColumnGroup(
            title="Scratch",
            columns=[
                Column(title="Total", field="total_score"),
                Column(title="Avg", field="avg_scratch"),
            ],
        ),
    ]
    # rank, player, hdc, total_net, avg_net, total_score, avg_scratch
    table = TableData(
        columns=columns,
        data=[
            [7, "Gus", 0, 5000, 200.0, 5200, 220.0],
            [2, "Dan", 10, 5100, 210.0, 4800, 200.0],
            [6, "Finn", 24, 4900, 205.0, 4500, 190.0],
            [1, "Anna", 5, 4800, 200.0, 4700, 195.0],
            [3, "Ben", 4, 4700, 199.0, 4600, 192.0],
            [8, "Hal", 20, 5050, 212.0, 4400, 180.0],
            [4, "Cara", 4, 4600, 190.0, 4500, 185.0],
            [5, "Eva", 11, 4500, 180.0, 4300, 175.0],
        ],
        title="t",
        metadata={"leaderboard_mode": "scratch_net_handicap"},
        row_metadata=[{"styling": {}, "cut_shade_rank": i} for i in range(1, 9)],
    )
    df = _finale_df()
    out = svc._integrate_ko_into_total_leaderboard(table, bracket, df, SEASON, TOURNAMENT)
    names = [row[1] for row in out.data]
    places = [row[0] for row in out.data]
    assert names[:6] == ["Anna", "Dan", "Ben", "Cara", "Eva", "Finn"]
    assert places[:6] == [1, 2, 3, 4, 5, 6]
    assert names[6:] == ["Hal", "Gus"]  # net avg 212 > 200, despite Gus scratch 220
    assert places[6:] == [7, 8]
    assert out.default_sort == {"field": "rank", "dir": "asc"}
    assert out.metadata.get("standings_order") == "ko_then_average"
    assert "Ersatz" in str(out.metadata.get("standings_note") or "")


def test_progress_chart_stops_after_qualifying_games() -> None:
    """Clubmeisterschaft config caps avg/position charts at 24 qualifying games."""
    svc = TournamentService(database="db_tournament_regions_2026_gf")
    svc._field_progress_cache.clear()
    fp = svc._compute_field_progress(SEASON, TOURNAMENT)
    assert fp.get("progress_chart_capped") is True
    assert len(fp.get("labels") or []) == 24
    assert fp.get("progress_chart_through_games") == 24
    # No KO game slots (rounds 7+) in the chart window.
    assert all(int(rn) <= 6 for rn, _g in (fp.get("game_slots") or []))
