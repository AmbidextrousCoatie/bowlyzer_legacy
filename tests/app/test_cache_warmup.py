"""Cache warmup helpers."""

from app.cache.cache_warmup import seasons_for_warmup, warm_myclub_spieler_for_club
from app.utils.league_player_sources import resolve_player_database_id


def test_seasons_for_warmup_limit():
    seasons = ["08/09", "09/10", "10/11", "11/12"]

    import os

    old = os.environ.get("LEAGUE_CACHE_WARM_MAX_SEASONS")
    try:
        os.environ.pop("LEAGUE_CACHE_WARM_MAX_SEASONS", None)
        assert seasons_for_warmup(seasons) == seasons
        os.environ["LEAGUE_CACHE_WARM_MAX_SEASONS"] = "2"
        assert seasons_for_warmup(seasons) == ["10/11", "11/12"]
    finally:
        if old is None:
            os.environ.pop("LEAGUE_CACHE_WARM_MAX_SEASONS", None)
        else:
            os.environ["LEAGUE_CACHE_WARM_MAX_SEASONS"] = old


def test_resolve_player_database_merged():
    db = resolve_player_database_id("db_real_merged")
    assert db in ("db_player_merged_hybrid", "db_real_merged")


def test_warm_myclub_spieler_for_club_endpoints(monkeypatch):
    warmed: list[tuple[str, dict[str, str]]] = []

    def fake_warm_one(endpoint, database, query, build):
        warmed.append((endpoint, dict(query)))
        build()
        return "built"

    monkeypatch.setattr("app.cache.cache_warmup._warm_one", fake_warm_one)

    class _FakePlayerService:
        database = "db_player_merged_hybrid"

        def search_players(self, _search, *, club):
            return [{"name": "A", "id": "1", "club": club}]

        def get_all_seasons(self, *, club):
            return ["25/26"]

        def get_aggregate_lifetime_stats(self, *, season, club):
            return {"scope": "all", "club": club, "season": season}

        def get_highest_individual_games(self, *, limit, club):
            return [{"player_name": "A", "score": 300, "club": club, "limit": limit}]

    stats = warm_myclub_spieler_for_club(
        _FakePlayerService(),
        "db_player_merged_hybrid",
        "Donaubowler Regensburg",
        log=lambda _msg: None,
    )
    assert stats["built"] == 4
    assert stats["errors"] == 0
    assert [e for e, _ in warmed] == [
        "player_search",
        "player_get_available_seasons",
        "get_lifetime_stats",
        "get_highest_individual_games",
    ]
    assert warmed[0][1]["club"] == "Donaubowler Regensburg"
    assert warmed[2][1]["season"] == "all"
    assert warmed[3][1]["limit"] == "10"
