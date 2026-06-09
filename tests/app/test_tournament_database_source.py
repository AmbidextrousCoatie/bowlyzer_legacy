"""Tournament DB source must read published merge on VPS (not GF export in the image)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.config.database_config import database_config
from app.routes import tournament_routes


def test_player_merged_hybrid_uses_runtime_league_plus_tournament_merge() -> None:
    cfg = database_config.get_source_config("db_player_merged_hybrid")
    assert cfg is not None
    assert cfg.is_enabled
    assert cfg.filename == "league_results_merged.csv"
    assert len(cfg.merge_file_paths) == 1
    assert Path(cfg.merge_file_paths[0]).name == "tournaments_postprocessed.csv"
    assert Path(cfg.file_path or "").name == "league_results_merged.csv"


def test_tournament_regions_uses_published_merge_file() -> None:
    cfg = database_config.get_source_config("db_tournament_regions_2026_gf")
    assert cfg is not None
    assert cfg.is_enabled
    assert cfg.filename == "tournaments_postprocessed.csv"
    assert cfg.merge_file_paths == ()
    path = Path(cfg.file_path or "")
    assert path.name == "tournaments_postprocessed.csv"
    assert path.parent.name == "data"


def test_resolve_default_tournament_source_parquet_only(monkeypatch) -> None:
    """Parquet-only VPS deploy must not fall back to db_real_merged (OOM risk)."""
    logical = Path("/app/database/data/tournaments_postprocessed.csv")

    def fake_get_source_config(source_id: str):
        if source_id == tournament_routes._REGIONAL_TOURNAMENT_SOURCE:
            return SimpleNamespace(file_path=str(logical))
        return None

    def fake_data_file_exists(path: Path) -> bool:
        assert path == logical
        return True

    def must_not_instantiate(*_args, **_kwargs):
        raise AssertionError("resolve must not load TournamentService")

    monkeypatch.setattr(database_config, "get_source_config", fake_get_source_config)
    monkeypatch.setattr(tournament_routes, "data_file_exists", fake_data_file_exists)
    monkeypatch.setattr(tournament_routes, "TournamentService", must_not_instantiate)

    assert (
        tournament_routes._resolve_default_tournament_source()
        == tournament_routes._REGIONAL_TOURNAMENT_SOURCE
    )
