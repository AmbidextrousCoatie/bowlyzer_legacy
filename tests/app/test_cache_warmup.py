"""Cache warmup helpers."""

from app.cache.cache_warmup import seasons_for_warmup
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
