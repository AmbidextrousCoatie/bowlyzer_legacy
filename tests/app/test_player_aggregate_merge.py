"""All-players aggregate lifetime stats merge."""

from __future__ import annotations

from app.services.player_service import PlayerService


def test_merge_aggregate_lifetime_payloads_combines_totals():
    part_a = {
        "scope": "all",
        "seasons": [{"season": "24/25", "row_type": "season_total", "games": 10}],
        "player_competitions": [{"player_name": "A", "average": 200.0, "games": 5}],
        "player_season_totals": [
            {
                "season": "24/25",
                "player_name": "A",
                "player_id": "1",
                "games": 10,
                "total_pins": 1800,
                "average": 180.0,
            }
        ],
        "periods": [{"player_name": "A", "average": 190.0}],
        "lifetime": {
            "total_games": 10,
            "total_pins": 1800,
            "average_score": 180.0,
            "best_game": {"score": 250, "date": "tbd", "event": "A · 24/25 Week 1"},
            "worst_game": {"score": 120, "date": "tbd", "event": "A · 24/25 Week 2"},
            "best_season": {"season": "24/25", "average": 180.0, "player_name": "A"},
            "most_improved": {"season": None, "improvement": None, "player_name": None},
        },
    }
    part_b = {
        "scope": "all",
        "seasons": [{"season": "25/26", "row_type": "season_total", "games": 8}],
        "player_competitions": [{"player_name": "B", "average": 210.0, "games": 4}],
        "player_season_totals": [
            {
                "season": "25/26",
                "player_name": "B",
                "player_id": "2",
                "games": 8,
                "total_pins": 1600,
                "average": 200.0,
            },
            {
                "season": "24/25",
                "player_name": "A",
                "player_id": "1",
                "games": 6,
                "total_pins": 1200,
                "average": 200.0,
            },
        ],
        "periods": [{"player_name": "B", "average": 205.0}],
        "lifetime": {
            "total_games": 8,
            "total_pins": 1600,
            "average_score": 200.0,
            "best_game": {"score": 280, "date": "tbd", "event": "B · 25/26 Week 1"},
            "worst_game": {"score": 100, "date": "tbd", "event": "B · 25/26 Week 2"},
            "best_season": {"season": "25/26", "average": 200.0, "player_name": "B"},
            "most_improved": {"season": "25/26", "improvement": 20.0, "player_name": "A"},
        },
    }

    merged = PlayerService.merge_aggregate_lifetime_payloads([part_a, part_b])
    assert merged is not None
    assert len(merged["seasons"]) == 2
    assert len(merged["player_competitions"]) == 2
    assert len(merged["player_season_totals"]) == 3
    assert merged["lifetime"]["total_games"] == 24
    assert merged["lifetime"]["total_pins"] == 4600
    assert merged["lifetime"]["best_game"]["score"] == 280
    assert merged["lifetime"]["worst_game"]["score"] == 100
    assert merged["lifetime"]["best_season"]["player_name"] == "B"
    assert merged["lifetime"]["most_improved"]["player_name"] == "A"
    assert merged["lifetime"]["most_improved"]["improvement"] == 20.0
