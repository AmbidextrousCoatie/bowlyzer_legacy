import pandas as pd

from data_access.league_standings_validation import (
    STATUS_GREEN,
    STATUS_RED,
    STATUS_YELLOW,
    StandingRow,
    classify_status,
    compare_standings,
    compute_standings_from_dataframe,
    parse_post_2022_tabges_standings,
    parse_pre_2022_tabelle_standings,
    pick_standings_sheet,
)


def _pre_2022_tabelle_df() -> pd.DataFrame:
    rows = [
        [None, None, None, None, None, None, None, None, None, None, None],
        [None, "Neue Tabelle", None, None, None, None, None, None, None, None, None],
        [None, None, "Mannschaft", None, None, None, None, "Pins", "Punkte", "Bonus", "Total"],
        [None, 1, "Team Alpha", None, None, None, None, 1000, 10, 2, 12],
        [None, 2, "Team Beta", None, None, None, None, 900, 8, 1, 9],
    ]
    return pd.DataFrame(rows)


def test_parse_pre_2022_tabelle_standings():
    rows = parse_pre_2022_tabelle_standings(_pre_2022_tabelle_df())
    assert len(rows) == 2
    assert rows[0] == StandingRow(position=1, team="Team Alpha", total_points=12.0, total_pins=1000)
    assert rows[1].team == "Team Beta"


def test_parse_post_2022_tabges_standings():
    rows_data = [
        ["Liga", None, None, None, None, None, None, None, None, None, None, None, None],
        ["Saison", None, None, None, None, None, None, None, None, None, None, None, None],
        ["Gesamttabelle", None, None, None, None, None, None, None, None, None, None, None, None],
        [None, None, None, None, None, None, None, None, None, None, None, None, None],
        ["Pl.", "Mannschaften", "Spieltag 1", None, "Spieltag 2", None, None, None, None, None, None, None, None],
        [None, None, "Pins", "Pkt.", "Pins", "Pkt.", None, None, None, None, None, None, None],
        [1, "Team Alpha", 500, 10, 500, 8, None, None, None, None, None, None, None],
        [2, "Team Beta", 400, 6, 450, 7, None, None, None, None, None, None, None],
    ]
    df = pd.DataFrame(rows_data)
    rows = parse_post_2022_tabges_standings(df)
    assert rows[0].team == "Team Alpha"
    assert rows[0].total_points == 18.0
    assert rows[0].total_pins == 1000
    assert rows[1].position == 2


def test_pick_standings_sheet_post_2022_prefers_tabges():
    sheets = ["Spielorte", "Tabelle6", "TabGes6", "Schnitt6"]
    assert pick_standings_sheet(sheets, data_format="data_format_post_2022") == "TabGes6"


def test_classify_status():
    assert classify_status(teams_match=True, positions_match=True, points_match=True, pins_match=True) == STATUS_GREEN
    assert classify_status(teams_match=True, positions_match=True, points_match=False, pins_match=True) == STATUS_YELLOW
    assert classify_status(teams_match=False, positions_match=False, points_match=False, pins_match=False) == STATUS_RED


def test_compare_standings_green_yellow_red():
    ref = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    computed_ok = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_ok)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_GREEN

    computed_pts_off = [
        StandingRow(1, "Team Alpha", 11.0, 1000),
        StandingRow(2, "Team Beta", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_pts_off)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_YELLOW

    computed_wrong_team = [
        StandingRow(1, "Team Alpha", 12.0, 1000),
        StandingRow(2, "Team Gamma", 9.0, 900),
    ]
    teams_match, pos_match, pts_match, pins_match, *_rest = compare_standings(ref, computed_wrong_team)
    assert classify_status(
        teams_match=teams_match,
        positions_match=pos_match,
        points_match=pts_match,
        pins_match=pins_match,
    ) == STATUS_RED


def test_compute_standings_from_dataframe():
    df = pd.DataFrame(
        [
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Alpha",
                "Score": "200",
                "Points": "1",
                "Input Data": "True",
                "Computed Data": "False",
            },
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Alpha",
                "Score": "180",
                "Points": "0.5",
                "Input Data": "True",
                "Computed Data": "False",
            },
            {
                "Season": "19/20",
                "Event": "A S2",
                "Event Type": "league",
                "Team": "Team Beta",
                "Score": "150",
                "Points": "0",
                "Input Data": "True",
                "Computed Data": "False",
            },
        ]
    )
    rows = compute_standings_from_dataframe(df, league="A S2", season="19/20")
    assert len(rows) == 2
    assert rows[0].team == "Team Alpha"
    assert rows[0].total_points == 1.5
    assert rows[0].total_pins == 380
