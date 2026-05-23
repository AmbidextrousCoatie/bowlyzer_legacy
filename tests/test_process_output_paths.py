from pathlib import Path

from extract_excel_data import (
    combo_processing_cache_key,
    process_scope_cache_key,
    resolve_process_output_paths,
    top_level_subdir_key,
)


class _Args:
    def __init__(self, output_file: str, output_dir: str | None = None):
        self.output_file = output_file
        self.output_dir = output_dir


def test_resolve_process_output_paths_default_combo_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "legacy" / "legacy_scrape_extracted.csv"
    args = _Args(str(out))
    combo_dir, merged = resolve_process_output_paths(args)
    assert merged == out.resolve()
    assert combo_dir == (out.parent / "legacy_scrape_extracted_combos").resolve()


def test_resolve_process_output_paths_explicit_combo_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "merged.csv"
    combo = tmp_path / "combos"
    args = _Args(str(out), str(combo))
    combo_dir, merged = resolve_process_output_paths(args)
    assert merged == out.resolve()
    assert combo_dir == combo.resolve()


def test_process_scope_cache_key_legacy_default():
    repo_root = Path(__file__).resolve().parents[1]
    default = (repo_root / "database/data/historical_league_results.csv").resolve()
    assert process_scope_cache_key(default) == "historical_league_results"


def test_process_scope_cache_key_legacy_scrape_scope(tmp_path):
    legacy_out = (tmp_path / "legacy_scrape_extracted.csv").resolve()
    assert process_scope_cache_key(legacy_out) == "scope::legacy_scrape_extracted"


def test_top_level_subdir_key(tmp_path):
    root = tmp_path / "legacy_scrape"
    root.mkdir()
    (root / "saison2008-09").mkdir()
    (root / "saison2009-10").mkdir()
    file_a = root / "saison2008-09" / "LB.xlsx"
    file_b = root / "saison2009-10" / "nested" / "LB.xlsx"
    file_a.parent.mkdir(parents=True, exist_ok=True)
    file_b.parent.mkdir(parents=True, exist_ok=True)
    file_a.touch()
    file_b.touch()
    assert top_level_subdir_key(file_a, root) == "saison2008-09"
    assert top_level_subdir_key(file_b, root) == "saison2009-10"
    assert top_level_subdir_key(root / "top.xlsx", root) == "_root"


def test_combo_processing_cache_key_scoped():
    assert combo_processing_cache_key("historical_league_results", "08/09", "Bayernliga") == "08/09::Bayernliga"
    assert (
        combo_processing_cache_key("scope::legacy_scrape_extracted", "08/09", "Bayernliga")
        == "scope::legacy_scrape_extracted::08/09::Bayernliga"
    )
