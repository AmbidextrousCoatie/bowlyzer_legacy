from app.utils.league_utils import numeric_sort_key


def test_numeric_sort_key_parses_formatted_average():
    assert numeric_sort_key("201.4") == 201.4
    assert numeric_sort_key(188.0) == 188.0
    assert numeric_sort_key("LL S") == float("-inf")


def test_top_team_rows_rank_by_average_not_league_or_season_order():
    """Regression: rows were sorted by league (index 3), a string, so the key
    was always 0 and the table kept the earliest seasons."""
    rows = [
        ["Team A", "210.0", "08/09", "LL S"],
        ["Team B", "205.0", "09/10", "LL S"],
        ["Team C", "220.0", "24/25", "LL S"],
    ]
    by_league = sorted(
        rows,
        key=lambda x: x[3] if isinstance(x[3], (int, float)) else 0,
        reverse=True,
    )
    assert by_league[0][2] == "08/09"

    by_average = sorted(rows, key=lambda x: numeric_sort_key(x[1]), reverse=True)
    assert [row[2] for row in by_average] == ["24/25", "08/09", "09/10"]
    assert by_average[0][1] == "220.0"
