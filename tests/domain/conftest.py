"""
Fixtures for domain-layer tests (v2 DDD). Skipped when the `domain` package is absent.
"""

from uuid import uuid4

import pytest

pytest.importorskip(
    "domain",
    reason="domain package is not part of this repository (legacy Flask app only)",
)

from domain.entities import Game, League, Player, Team
from domain.value_objects import (
    GameResult,
    Handicap,
    HandicapCalculationMethod,
    HandicapSettings,
    Points,
    Score,
    Season,
)


@pytest.fixture
def sample_score():
    return Score(200.0)


@pytest.fixture
def sample_points():
    return Points(2.5)


@pytest.fixture
def sample_season():
    return Season("2024-25")


@pytest.fixture
def sample_handicap():
    return Handicap(20.0)


@pytest.fixture
def sample_handicap_settings():
    return HandicapSettings(
        enabled=True,
        calculation_method=HandicapCalculationMethod.CUMULATIVE_AVERAGE,
        base_average=200.0,
        percentage=0.9,
        max_handicap=50.0,
        cap_handicap_score=True,
    )


@pytest.fixture
def sample_handicap_settings_moving_window():
    return HandicapSettings(
        enabled=True,
        calculation_method=HandicapCalculationMethod.MOVING_WINDOW,
        base_average=200.0,
        percentage=0.9,
        max_handicap=50.0,
        moving_window_size=5,
        cap_handicap_score=True,
    )


@pytest.fixture
def sample_game_result(sample_score, sample_points, sample_handicap):
    return GameResult(
        player_id=uuid4(),
        position=1,
        scratch_score=sample_score,
        points=sample_points,
        handicap=sample_handicap,
    )


@pytest.fixture
def sample_team():
    return Team(name="Team Alpha", league_id=uuid4())


@pytest.fixture
def sample_player():
    return Player(name="John Doe")


@pytest.fixture
def sample_league(sample_season):
    return League(name="Test League", abbreviation="TEST", level=3)


@pytest.fixture
def sample_game(sample_league, sample_season):
    team1_id = uuid4()
    team2_id = uuid4()
    return Game(
        league_id=sample_league.id,
        season=sample_season,
        week=1,
        team_id=team1_id,
        opponent_team_id=team2_id,
    )


def create_game_results(player_id, scores, positions=None, handicaps=None):
    from domain.value_objects.game_result import GameResult
    from domain.value_objects.handicap import Handicap
    from domain.value_objects.points import Points
    from domain.value_objects.score import Score

    if positions is None:
        positions = [1] * len(scores)
    if handicaps is None:
        handicaps = [None] * len(scores)

    results = []
    for score, position, handicap in zip(scores, positions, handicaps):
        results.append(
            GameResult(
                player_id=player_id,
                position=position,
                scratch_score=Score(score),
                points=Points(2.0),
                handicap=Handicap(handicap) if handicap is not None else None,
            )
        )
    return results
