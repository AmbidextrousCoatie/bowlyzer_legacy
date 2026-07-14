"""Tournament landing overview: podiums and player history."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.tournament_service import TournamentService

CSV = Path(__file__).resolve().parents[2] / "database" / "data" / "tournament_manual_postprocessed.csv"


@pytest.fixture
def svc() -> TournamentService:
    if not CSV.is_file():
        pytest.skip("tournament_manual_postprocessed.csv not present")
    return TournamentService(database="db_tournament_regions_2026_gf")


def test_list_tournament_events_returns_season_tournament_pairs(svc: TournamentService) -> None:
    events = svc.list_tournament_events()
    assert events
    assert {"season", "tournament"} <= set(events[0].keys())


def test_get_tournament_podiums_top_three(svc: TournamentService) -> None:
    events = svc.list_tournament_events()
    if not events:
        pytest.skip("no tournament events")
    sample = events[0]
    payload = svc.get_tournament_podiums(
        season=sample["season"],
        tournament=sample["tournament"],
        top_n=3,
    )
    assert payload["top_n"] == 3
    assert len(payload["podiums"]) == 1
    podium = payload["podiums"][0]
    assert podium["tournament_group"]
    assert "tournament_average" in podium
    finishers = podium["finishers"]
    assert 1 <= len(finishers) <= 3
    assert finishers[0]["player"]
    if finishers[0].get("average") is not None:
        assert podium["tournament_average"] is not None


def test_get_tournament_podiums_groups_by_normalized_name(svc: TournamentService) -> None:
    payload = svc.get_tournament_podiums(tournament="Bayerische Meisterschaft Einzel", top_n=1)
    seasons = {p["season"] for p in payload["podiums"]}
    assert len(seasons) >= 2
    assert all(
        p["tournament_group"] == "Bayerische Meisterschaft Einzel" for p in payload["podiums"]
    )


def test_get_player_tournament_results(svc: TournamentService) -> None:
    events = svc.list_tournament_events()
    if not events:
        pytest.skip("no tournament events")
    sample = events[0]
    finishers, tournament_average = svc._leaderboard_top_finishers(sample["season"], sample["tournament"], top_n=1)
    if not finishers:
        pytest.skip("no finishers")
    player = finishers[0]["player"]
    rows = svc.get_player_tournament_results(player)
    assert rows
    match = next(
        (
            row
            for row in rows
            if row["season"] == sample["season"] and row["tournament"] == sample["tournament"]
        ),
        None,
    )
    assert match is not None
    assert match["position"] is not None
    assert match["average"] is not None


def test_get_tournament_player_catalog_without_event_scope(svc: TournamentService) -> None:
    players = svc.get_tournament_player_catalog()
    assert players
    assert all(str(name).strip() for name in players)
