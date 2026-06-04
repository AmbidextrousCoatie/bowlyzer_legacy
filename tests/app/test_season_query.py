from app.utils.season_query import normalize_season_query_value, season_for_api_query


def test_normalize_season_hyphen_and_slash():
    assert normalize_season_query_value("14-15") == "14/15"
    assert normalize_season_query_value("14/15") == "14/15"
    assert normalize_season_query_value("14%2F15") == "14/15"


def test_season_for_api_query():
    assert season_for_api_query("25/26") == "25/26"
    assert season_for_api_query("25-26") == "25/26"
