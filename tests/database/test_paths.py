"""database.paths — work vs published data directories."""

from database.paths import (
    REPO_DATA_DIR,
    REPO_WORK_DIR,
    _csv_looks_populated,
    _prefer_populated_csv,
    default_work_data_dir,
    get_data_dir,
    get_published_csv_dir,
    get_work_data_dir,
    gf_tournaments_combined_postprocessed_csv,
    legacy_scrape_dir,
    manual_tournament_postprocessed_csv,
)


def test_default_work_dir_is_repo_local(monkeypatch):
    monkeypatch.delenv("BOWLYZER_WORK_DATA_DIR", raising=False)
    assert default_work_data_dir() == REPO_WORK_DIR


def test_work_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(tmp_path / "work"))
    assert get_work_data_dir() == (tmp_path / "work").resolve()


def test_data_dir_defaults_to_repo(monkeypatch):
    monkeypatch.delenv("BOWLYZER_DATA_DIR", raising=False)
    assert get_data_dir() == REPO_DATA_DIR


def test_published_csv_dir_defaults_to_repo(monkeypatch):
    monkeypatch.delenv("BOWLYZER_PUBLISHED_CSV_DIR", raising=False)
    assert get_published_csv_dir().name == "published_csv"


def test_legacy_scrape_prefers_work_dir(monkeypatch, tmp_path):
    work = tmp_path / "work"
    legacy = work / "legacy_scrape"
    legacy.mkdir(parents=True)
    (legacy / "marker.txt").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work))
    assert legacy_scrape_dir() == legacy


def test_prefer_populated_csv_skips_header_only_stub(tmp_path):
    stub = tmp_path / "stub.csv"
    real = tmp_path / "real.csv"
    stub.write_text("Season;Player\n", encoding="utf-8")
    real.write_text("Season;Player\n" + ("25/26;Alice\n" * 40), encoding="utf-8")
    assert not _csv_looks_populated(stub)
    assert _csv_looks_populated(real)
    assert _prefer_populated_csv(stub, real) == real.resolve()


def test_tournament_paths_skip_empty_work_stubs(monkeypatch, tmp_path):
    """Overridden work dir with empty stubs must not hide database/work copies."""
    work = tmp_path / "work"
    (work / "tournaments").mkdir(parents=True)
    (work / "gf").mkdir(parents=True)
    header = (
        "Season;Date;Location;Event Type;Event Name;Round Number;Round Name;"
        "Player;Player ID;Club;Game Number;Score;Handicap;Cumulative Score;"
        "Stage Rank;Cut Line;Cut Basis;Overall Cumulative Score\n"
    )
    (work / "tournaments" / "tournament_manual_postprocessed.csv").write_text(header, encoding="utf-8")
    (work / "gf" / "gf_tournaments_2026__combined_postprocessed.csv").write_text(header, encoding="utf-8")
    monkeypatch.setenv("BOWLYZER_WORK_DATA_DIR", str(work))

    # Only assert fallback behavior when repo work copies are populated.
    manual = manual_tournament_postprocessed_csv()
    gf = gf_tournaments_combined_postprocessed_csv()
    if _csv_looks_populated(REPO_WORK_DIR / "tournaments" / "tournament_manual_postprocessed.csv"):
        assert manual.resolve() != (work / "tournaments" / "tournament_manual_postprocessed.csv").resolve()
        assert _csv_looks_populated(manual)
    if _csv_looks_populated(REPO_WORK_DIR / "gf" / "gf_tournaments_2026__combined_postprocessed.csv"):
        assert gf.resolve() != (work / "gf" / "gf_tournaments_2026__combined_postprocessed.csv").resolve()
        assert _csv_looks_populated(gf)
