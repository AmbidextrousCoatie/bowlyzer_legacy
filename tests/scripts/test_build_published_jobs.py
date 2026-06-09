"""--job flag parsing for build_published_dataset."""

import pytest

from scripts.build_published_dataset import order_publish_jobs, parse_job_names


def test_parse_job_names_default_pair():
    assert parse_job_names("league,tournament") == ["league", "tournament"]


def test_parse_job_names_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        parse_job_names("league,foo")


def test_order_publish_jobs_prepends_registry_before_league():
    assert order_publish_jobs(["league", "tournament"], auto_players_registry=True) == [
        "players_registry",
        "league",
        "tournament",
    ]


def test_order_publish_jobs_respects_skip_flag():
    assert order_publish_jobs(["league"], auto_players_registry=False) == ["league"]


def test_order_publish_jobs_keeps_explicit_registry_first():
    assert order_publish_jobs(["players_registry", "league"], auto_players_registry=True) == [
        "players_registry",
        "league",
    ]
