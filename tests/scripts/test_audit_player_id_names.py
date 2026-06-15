"""Player name / Player ID consistency audit (no auto-merge)."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.audit_player_id_names import (
    ANALYSIS_MULTI_ID,
    ANALYSIS_MULTI_NAME,
    AUTORESOLVE_MAJORITY,
    AUTORESOLVE_NAME_REASSEMBLY,
    AUTORESOLVE_PLACEHOLDER,
    ISSUE_SAME_ID,
    ISSUE_SAME_ID_NAME_VARIANTS,
    ISSUE_SAME_NAME,
    audit_player_id_names,
    is_placeholder_player_id,
    write_conflict_report,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    headers = ["Season", "Player", "Player ID", "Input Data", "Computed Data"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _player_row(*, season: str, name: str, pid: str) -> dict:
    return {
        "Season": season,
        "Player": name,
        "Player ID": pid,
        "Input Data": "True",
        "Computed Data": "False",
    }


def test_same_name_different_ids(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Seltmann, Dominik", pid="25604"),
        _player_row(season="14/15", name="Seltmann, Dominik", pid="26504"),
        _player_row(season="25/26", name="Seltmann, Dominik", pid="25604"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False)
    same_name = [c for c in conflicts if c.issue_type == ISSUE_SAME_NAME]
    assert len(same_name) == 2
    assert {c.player_id for c in same_name} == {"25604", "26504"}
    assert all(c.player_name == "Seltmann, Dominik" for c in same_name)
    assert all(c.group_size_ids == 2 for c in same_name)


def test_same_id_skipped_when_registry_covers_aliases(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    rows = [
        _player_row(season="24/25", name="Mario Burghardt", pid="12248"),
        _player_row(season="14/15", name="Burghardt, Mario", pid="12248"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    registry = pd.DataFrame(
        [
            {
                "player_id": "12248",
                "canonical_name": "Burghardt, Mario",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "Mario Burghardt",
            }
        ]
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_players_registry_df",
        lambda: registry,
    )

    conflicts = audit_player_id_names(path)
    assert conflicts == []


def test_same_id_different_names(tmp_path: Path) -> None:
    rows = [
        _player_row(season="08/09", name="Rotter, Mark-Roland", pid="16005"),
        _player_row(season="09/10", name="Rotter Dr., Aurelian", pid="16005"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(
        path, apply_normalization=False, analyses=[ANALYSIS_MULTI_ID]
    )
    same_id = [c for c in conflicts if c.issue_type == ISSUE_SAME_ID]
    assert len(same_id) == 2
    assert {c.player_name for c in same_id} == {"Rotter, Mark-Roland", "Rotter Dr., Aurelian"}
    assert all(c.player_id == "16005" for c in same_id)


def test_default_audit_does_not_duplicate_same_id_groups(tmp_path: Path) -> None:
    rows = [
        _player_row(season="08/09", name="Rotter, Mark-Roland", pid="16005"),
        _player_row(season="09/10", name="Rotter Dr., Aurelian", pid="16005"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False)
    assert len(conflicts) == 2
    assert all(c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS for c in conflicts)
    assert not any(c.issue_type == ISSUE_SAME_ID for c in conflicts)


def test_different_spellings_are_not_same_name(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Seltmann, Dominik", pid="25604"),
        _player_row(season="14/15", name="Seltmann, Dominic", pid="26504"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False)
    assert conflicts == []


def test_skips_team_total_and_computed_rows(tmp_path: Path) -> None:
    rows = [
        {
            "Season": "24/25",
            "Player": "Team Total",
            "Player ID": "99999",
            "Input Data": "True",
            "Computed Data": "False",
        },
        {
            "Season": "24/25",
            "Player": "Alpha, A",
            "Player ID": "1",
            "Input Data": "False",
            "Computed Data": "False",
        },
        _player_row(season="24/25", name="Beta, B", pid="1"),
        _player_row(season="24/25", name="Beta, C", pid="1"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False)
    variants = [c for c in conflicts if c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS]
    assert len(variants) == 2
    assert {c.player_name for c in variants} == {"Beta, B", "Beta, C"}


def test_majority_autoresolve_same_name(tmp_path: Path) -> None:
    rows = []
    for _ in range(30):
        rows.append(_player_row(season="24/25", name="Seltmann, Dominik", pid="25604"))
    rows.append(_player_row(season="14/15", name="Seltmann, Dominik", pid="26504"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path)
    minority = next(
        c for c in conflicts if c.issue_type == ISSUE_SAME_NAME and c.player_id == "26504"
    )
    majority = next(
        c for c in conflicts if c.issue_type == ISSUE_SAME_NAME and c.player_id == "25604"
    )
    assert minority.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert minority.proposed_id == "25604"
    assert majority.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert majority.proposed_id == ""


def test_majority_not_applied_below_ratio(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Same, Name", pid="10001"),
        _player_row(season="24/25", name="Same, Name", pid="10001"),
        _player_row(season="14/15", name="Same, Name", pid="10002"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False)
    for row in conflicts:
        assert row.autoresolve_rule == ""
        assert row.proposed_id == ""


def test_is_placeholder_player_id() -> None:
    assert is_placeholder_player_id("1")
    assert is_placeholder_player_id("111")
    assert is_placeholder_player_id("99999")
    assert is_placeholder_player_id("11112345")
    assert is_placeholder_player_id("99991234")
    assert not is_placeholder_player_id("25604")
    assert not is_placeholder_player_id("1234")
    assert not is_placeholder_player_id("11123")


def test_placeholder_autoresolve_same_name(tmp_path: Path) -> None:
    rows = []
    for _ in range(20):
        rows.append(_player_row(season="24/25", name="Dummy, Player", pid="25604"))
    rows.append(_player_row(season="24/25", name="Dummy, Player", pid="11111"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path)
    placeholder = next(c for c in conflicts if c.player_id == "11111")
    real = next(c for c in conflicts if c.player_id == "25604")
    assert placeholder.autoresolve_rule == AUTORESOLVE_PLACEHOLDER
    assert placeholder.proposed_id == "25604"
    assert real.autoresolve_rule == AUTORESOLVE_PLACEHOLDER
    assert real.proposed_id == ""


def test_placeholder_all_dummy_ids_picks_majority_games(tmp_path: Path) -> None:
    rows = []
    for _ in range(10):
        rows.append(_player_row(season="24/25", name="Dummy, Player", pid="11111"))
    rows.append(_player_row(season="24/25", name="Dummy, Player", pid="111"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path)
    dominant = next(c for c in conflicts if c.player_id == "11111")
    minority = next(c for c in conflicts if c.player_id == "111")
    assert dominant.autoresolve_rule == AUTORESOLVE_PLACEHOLDER
    assert dominant.proposed_id == ""
    assert minority.autoresolve_rule == AUTORESOLVE_PLACEHOLDER
    assert minority.proposed_id == "11111"


def test_multi_name_reassembly_same_canonical(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Scheigenpflug, Stephan", pid="12345"),
        _player_row(season="14/15", name="Stephan Scheigenpflug", pid="12345"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 2
    assert all(c.issue_type == ISSUE_SAME_ID_NAME_VARIANTS for c in conflicts)
    assert all(c.canonical_name == "Scheigenpflug, Stephan" for c in conflicts)
    reordered = next(c for c in conflicts if c.player_name == "Stephan Scheigenpflug")
    canonical_row = next(c for c in conflicts if c.player_name == "Scheigenpflug, Stephan")
    assert reordered.autoresolve_rule == AUTORESOLVE_NAME_REASSEMBLY
    assert reordered.proposed_name == "Scheigenpflug, Stephan"
    assert canonical_row.autoresolve_rule == AUTORESOLVE_NAME_REASSEMBLY
    assert canonical_row.proposed_name == ""


def test_multi_name_no_reassembly_when_canonicals_differ(tmp_path: Path) -> None:
    rows = [
        _player_row(season="08/09", name="Rotter, Mark-Roland", pid="16005"),
        _player_row(season="09/10", name="Rotter Dr., Aurelian", pid="16005"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 2
    assert all(c.autoresolve_rule == "" for c in conflicts)
    assert all(c.proposed_name == "" for c in conflicts)
    assert {c.canonical_name for c in conflicts} == {
        "Rotter, Mark-Roland",
        "Rotter Dr., Aurelian",
    }


def test_multi_name_merges_comma_whitespace_variants(tmp_path: Path) -> None:
    rows = []
    for _ in range(10):
        rows.append(_player_row(season="24/25", name="Mihatsch, Rudolf", pid="7031"))
    for _ in range(4):
        rows.append(_player_row(season="18/19", name="Mihatsch , Rudolf", pid="7031"))
    rows.append(_player_row(season="08/09", name="Mihatsch, Rudi", pid="7031"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 2
    rudolf = next(c for c in conflicts if c.player_name == "Mihatsch, Rudolf")
    rudi = next(c for c in conflicts if c.player_name == "Mihatsch, Rudi")
    assert rudolf.row_count == 14
    assert rudolf.canonical_name == "Mihatsch, Rudolf"
    assert rudolf.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert rudolf.proposed_name == ""
    assert rudi.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert rudi.proposed_name == "Mihatsch, Rudolf"


def test_multi_name_reassembly_two_token_reversal(tmp_path: Path) -> None:
    rows = []
    for _ in range(20):
        rows.append(_player_row(season="24/25", name="Köse, Sahin", pid="16002"))
    rows.append(_player_row(season="25/26", name="Köse Sahin", pid="16002"))
    rows.append(_player_row(season="25/26", name="Sahin Köse", pid="16002"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 3
    assert all(c.autoresolve_rule == AUTORESOLVE_NAME_REASSEMBLY for c in conflicts)
    assert all(c.canonical_name == "Köse, Sahin" for c in conflicts)
    dominant = next(c for c in conflicts if c.player_name == "Köse, Sahin")
    minority_a = next(c for c in conflicts if c.player_name == "Köse Sahin")
    minority_b = next(c for c in conflicts if c.player_name == "Sahin Köse")
    assert dominant.proposed_name == ""
    assert minority_a.proposed_name == "Köse, Sahin"
    assert minority_b.proposed_name == "Köse, Sahin"


def test_multi_name_majority_when_reversal_does_not_apply(tmp_path: Path) -> None:
    rows = []
    for _ in range(20):
        rows.append(_player_row(season="24/25", name="Rotter, Mark-Roland", pid="16005"))
    rows.append(_player_row(season="09/10", name="Rotter Dr., Aurelian", pid="16005"))

    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 2
    dominant = next(c for c in conflicts if c.player_name == "Rotter, Mark-Roland")
    minority = next(c for c in conflicts if c.player_name == "Rotter Dr., Aurelian")
    assert dominant.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert dominant.proposed_name == ""
    assert minority.autoresolve_rule == AUTORESOLVE_MAJORITY
    assert minority.proposed_name == "Rotter, Mark-Roland"


def test_multi_name_majority_not_applied_below_ratio(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Rotter, Mark-Roland", pid="16005"),
        _player_row(season="24/25", name="Rotter, Mark-Roland", pid="16005"),
        _player_row(season="25/26", name="Rotter Dr., Aurelian", pid="16005"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_NAME])
    assert all(c.autoresolve_rule == "" for c in conflicts)
    assert all(c.proposed_name == "" for c in conflicts)


def test_analysis_multi_id_only_skips_name_variants(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Scheigenpflug, Stephan", pid="12345"),
        _player_row(season="14/15", name="Stephan Scheigenpflug", pid="12345"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, apply_normalization=False, analyses=[ANALYSIS_MULTI_ID])
    assert len(conflicts) == 2
    assert all(c.issue_type == ISSUE_SAME_ID for c in conflicts)
    assert all(c.canonical_name == "" for c in conflicts)


def test_registry_id_match_skips_false_placeholder_outlier(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    registry = pd.DataFrame(
        [
            {
                "player_id": "7762",
                "canonical_name": "Windsheimer, Friedrich",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
            {
                "player_id": "111708",
                "canonical_name": "Windsheimer, Friedrich",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
        ]
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_players_registry_df",
        lambda: registry,
    )

    rows = [
        _player_row(season="12/13", name="Windsheimer, Friedrich", pid="7762"),
        _player_row(season="14/15", name="Giuseppe, Giorgini", pid="7762"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, analyses=[ANALYSIS_MULTI_NAME])
    names = {c.player_name for c in conflicts}
    assert "Windsheimer, Friedrich" not in names


def test_same_person_config_skips_name_variants(tmp_path: Path) -> None:
    rows = [
        _player_row(season="17/18", name="Schwartz, Janin", pid="38397"),
        _player_row(season="19/20", name="Theisen, Janin", pid="38397"),
        _player_row(season="11/12", name="Feuerlein, Andy", pid="16270"),
        _player_row(season="24/25", name="Feuerlein, Andreas", pid="16270"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, analyses=[ANALYSIS_MULTI_NAME])
    assert conflicts == []


def test_different_person_config_skips_vogt_homonym(tmp_path: Path) -> None:
    rows = [
        _player_row(season="25/26", name="Vogt, Thomas", pid="10903"),
        _player_row(season="09/10", name="Vogt, Thomas", pid="25263"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path)
    assert not any(c.issue_type == ISSUE_SAME_NAME for c in conflicts)


def test_placeholder_bucket_uses_registry_per_name(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    registry = pd.DataFrame(
        [
            {
                "player_id": "25977",
                "canonical_name": "Erhard, Hannelore",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
            {
                "player_id": "25978",
                "canonical_name": "Steiner, Alfred",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
        ]
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_players_registry_df",
        lambda: registry,
    )
    monkeypatch.setattr(
        "data_access.player_id_name_normalization.apply_player_id_name_normalization",
        lambda df, **kwargs: (df, {}),
    )

    rows = [
        _player_row(season="13/14", name="Erhard, Hannelore", pid="99999"),
        _player_row(season="13/14", name="Steiner, Alfred", pid="99999"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 2
    erhard = next(c for c in conflicts if c.player_name == "Erhard, Hannelore")
    steiner = next(c for c in conflicts if c.player_name == "Steiner, Alfred")
    assert erhard.autoresolve_rule == AUTORESOLVE_PLACEHOLDER
    assert erhard.proposed_id == "25977"
    assert erhard.group_size_names == 1
    assert erhard.peer_player_names == ""
    assert steiner.proposed_id == "25978"


def test_same_id_outlier_splits_from_coherent_cluster(tmp_path: Path, monkeypatch) -> None:
    import pandas as pd

    registry = pd.DataFrame(
        [
            {
                "player_id": "38429",
                "canonical_name": "Vu, Hoang Long",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "Hoang Long, Vu|Vu, Hong Long",
            },
            {
                "player_id": "38424",
                "canonical_name": "Gulvadi, Sanat",
                "source": "dbu_id",
                "updated_at": "t",
                "aliases": "",
            },
        ]
    )
    monkeypatch.setattr(
        "data_access.players_registry.load_players_registry_df",
        lambda: registry,
    )
    monkeypatch.setattr(
        "data_access.player_id_name_normalization.apply_player_id_name_normalization",
        lambda df, **kwargs: (df, {}),
    )

    rows = [
        _player_row(season="17/18", name="Vu, Hoang Long", pid="38429"),
        _player_row(season="17/18", name="Vu, Hong Long", pid="38429"),
        _player_row(season="17/18", name="Gulvadi, Sanat", pid="38429"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)

    conflicts = audit_player_id_names(path, analyses=[ANALYSIS_MULTI_NAME])
    assert len(conflicts) == 1
    outlier = conflicts[0]
    assert outlier.player_name == "Gulvadi, Sanat"
    assert outlier.player_id == "38429"
    assert outlier.proposed_id == "38424"
    assert outlier.autoresolve_rule == AUTORESOLVE_PLACEHOLDER


def test_write_conflict_report(tmp_path: Path) -> None:
    rows = [
        _player_row(season="24/25", name="Same, Name", pid="1"),
        _player_row(season="24/25", name="Same, Name", pid="2"),
    ]
    path = tmp_path / "league.csv"
    _write_csv(path, rows)
    out = tmp_path / "report.csv"
    conflicts = audit_player_id_names(path)
    write_conflict_report(conflicts, out)
    text = out.read_text(encoding="utf-8")
    assert "same_name_different_ids" in text
    assert "Same, Name" in text
