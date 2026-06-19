"""Tests for league season points budget."""

from data_access.league_points_budget import (
    analyze_total_points,
    compute_league_points_budget,
    detect_points_one_off_correction,
    points_per_match,
    weekly_match_points_budget,
)


def test_bayl_24_25_weekly_budget_matches_standings_sum():
    budget = compute_league_points_budget(
        league="BayL",
        season="24/25",
        number_of_teams=10,
        reference_weeks=4,
        games_per_week=9,
        data_format="data_format_post_2022",
    )
    assert budget.points_per_match == 6.0
    assert budget.weekly_match_points == 270.0
    assert budget.season_total_points == 1080.0


def test_kl_n2_23_24_expected_total_matches_excel_reference():
    budget = compute_league_points_budget(
        league="KL N2",
        season="23/24",
        number_of_teams=4,
        reference_weeks=5,
        games_per_week=6,
        data_format="data_format_post_2022",
    )
    assert budget.season_total_points == 360.0


def test_analyze_total_points_flags_excel_aggregate_error():
    budget = compute_league_points_budget(
        league="KL N2",
        season="23/24",
        number_of_teams=4,
        reference_weeks=5,
        games_per_week=6,
    )
    ref_ok, comp_ok, explained, message = analyze_total_points(
        reference_total=360.0,
        computed_total=300.0,
        budget=budget,
        points_mismatches=[
            "RW 69 Lichtenhof Stein 8: ref pts 117.5 vs computed 95.5",
            "Castra Regina Regensburg 3: ref pts 100.5 vs computed 88.5",
            "Donaubowler Regensburg 3: ref pts 99.0 vs computed 81.0",
        ],
    )
    assert ref_ok is True
    assert comp_ok is False
    assert explained is False
    assert "Excel ref" in message

    ref_ok2, comp_ref_ok2, explained2, message2 = analyze_total_points(
        reference_total=420.0,
        computed_total=420.0,
        budget=budget,
        points_mismatches=[],
    )
    assert ref_ok2 is False
    assert comp_ref_ok2 is True
    assert explained2 is False
    assert "schema" in message2


def test_points_per_match_3pt_system():
    assert points_per_match("liga_bayern_3pt", players_per_team=4) == 7.0
    assert weekly_match_points_budget(10, 9, 7.0) == 315.0


def test_pre_2022_five_team_phantom_bye_budget_matches_excel_reference():
    """A S1 10/11: 5 real teams, Spielzettel metadata counts 6 incl. bye."""
    budget = compute_league_points_budget(
        league="A S1",
        season="10/11",
        number_of_teams=5,
        reference_weeks=8,
        games_per_week=5,
        data_format="data_format_pre_2022",
        phantom_bye=True,
    )
    assert budget.weekly_match_points == 30.0
    assert budget.weekly_placement_points == 15.0
    assert budget.weekly_total_points == 45.0
    assert budget.season_total_points == 360.0


def test_pre_2022_an2_expected_total_includes_placement_bonus():
    budget = compute_league_points_budget(
        league="A N2",
        season="09/10",
        number_of_teams=8,
        reference_weeks=8,
        games_per_week=7,
        data_format="data_format_pre_2022",
    )
    assert budget.points_per_match == 2.0
    assert budget.weekly_match_points == 56.0
    assert budget.weekly_placement_points == 36.0
    assert budget.season_total_points == 736.0


def test_no_show_weekly_reduction_escalates():
    from data_access.league_points_budget import (
        apply_no_show_adjustments,
        no_show_weekly_reduction,
    )

    assert no_show_weekly_reduction(0) == 0.0
    assert no_show_weekly_reduction(1) == 1.0
    assert no_show_weekly_reduction(2) == 3.0
    assert no_show_weekly_reduction(3) == 6.0

    budget = compute_league_points_budget(
        league="BL S1 (D)",
        season="10/11",
        number_of_teams=6,
        reference_weeks=8,
        games_per_week=5,
        data_format="data_format_pre_2022",
    )
    assert budget.season_total_points == 408.0
    adjusted = apply_no_show_adjustments(budget, {5: 1})
    assert adjusted.season_total_points == 407.0
    assert adjusted.expected_weekly_points(5) == 50.0
    assert adjusted.expected_weekly_points(1) == 51.0


def test_detect_no_show_ref_schema_healing_accepts_excel_below_schema():
    from data_access.league_points_budget import detect_no_show_ref_schema_healing

    healed, remark = detect_no_show_ref_schema_healing(
        reference_total=735.0,
        computed_total=735.0,
        schema_total=736.0,
        no_show_teams_by_week={5: ["SG Rottendorf 5"]},
        comp_ref_ok=True,
        ref_schema_ok=False,
        teams_match=True,
        positions_match=True,
    )
    assert healed is True
    assert "SG Rottendorf 5" in remark
    assert "W5" in remark


def test_detect_no_show_ref_schema_healing_rejects_when_merge_differs_from_excel():
    from data_access.league_points_budget import detect_no_show_ref_schema_healing

    healed, _remark = detect_no_show_ref_schema_healing(
        reference_total=735.0,
        computed_total=728.0,
        schema_total=736.0,
        no_show_teams_by_week={5: ["SG Rottendorf 5"]},
        comp_ref_ok=False,
        ref_schema_ok=False,
        teams_match=True,
        positions_match=True,
    )
    assert healed is False


def test_detect_points_one_off_correction_accepts_computed_an2_case():
    corrected, remark = detect_points_one_off_correction(
        reference_total=736.0,
        computed_total=735.0,
        expected_total=736.0,
        points_mismatches=[
            "SG Rottendorf 4: ref pts 146.0 vs computed 145.0",
        ],
        teams_match=True,
        positions_match=True,
        pins_match=True,
        reference_total_points_ok=True,
        computed_total_points_ok=False,
    )
    assert corrected is True
    assert "SG Rottendorf 4" in remark
    assert "accepted computed" in remark


def test_detect_points_one_off_correction_when_excel_total_one_high():
    corrected, remark = detect_points_one_off_correction(
        reference_total=737.0,
        computed_total=736.0,
        expected_total=736.0,
        points_mismatches=[
            "OK Bowlers Bindlach 2: ref pts 99.0 vs computed 98.0",
        ],
        teams_match=True,
        positions_match=True,
        pins_match=True,
        reference_total_points_ok=False,
        computed_total_points_ok=True,
    )
    assert corrected is True
    assert "OK Bowlers Bindlach 2" in remark
    assert "schema" in remark


def test_detect_points_one_off_correction_rejects_multi_point_gap():
    corrected, _remark = detect_points_one_off_correction(
        reference_total=736.0,
        computed_total=733.0,
        expected_total=736.0,
        points_mismatches=[
            "SG Rottendorf 4: ref pts 146.0 vs computed 143.0",
        ],
        teams_match=True,
        positions_match=True,
        pins_match=True,
        reference_total_points_ok=True,
        computed_total_points_ok=False,
    )
    assert corrected is False
