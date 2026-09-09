"""Cache warmup helpers."""

from app.cache.cache_warmup import (
    iter_liga_season_overview_jobs,
    season_timetable_payload,
    seasons_for_warmup,
    warm_myclub_spieler_for_club,
)
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


def test_season_timetable_payload_uses_to_dict():
    class _Table:
        def to_dict(self):
            return {"columns": [], "data": [[1, "2011-09-18", "Brunnthal"]]}

    class _Ls:
        def get_season_timetable(self, *, league, season):
            assert league == "A N1"
            assert season == "11/12"
            return _Table()

    assert season_timetable_payload(_Ls(), "A N1", "11/12") == {
        "columns": [],
        "data": [[1, "2011-09-18", "Brunnthal"]],
    }


def test_iter_liga_season_overview_jobs_is_per_season_then_league():
    class _Ls:
        def get_leagues(self, *, season):
            return {"11/12": ["BayL", "A N1"], "12/13": ["BayL"]}[season]

        def get_season_league_standings(self, *, season, division):
            return {"season": season, "division": division}

        def get_season_timetable(self, *, league, season):
            class _Table:
                def to_dict(self):
                    return {"league": league, "season": season}

            return _Table()

    jobs = iter_liga_season_overview_jobs(_Ls(), "db_real_merged", ["11/12", "12/13"])
    endpoints = [(endpoint, query.get("season"), query.get("league")) for endpoint, query, _build in jobs]
    assert endpoints == [
        ("get_season_league_standings", "11/12", None),
        ("get_season_timetable", "11/12", "BayL"),
        ("get_season_timetable", "11/12", "A N1"),
        ("get_season_league_standings", "12/13", None),
        ("get_season_timetable", "12/13", "BayL"),
    ]
    assert jobs[2][2]() == {"league": "A N1", "season": "11/12"}
