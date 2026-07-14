"""Tests for legacy tournament PDF discovery."""

from database.tournament_scrape.categories import load_scrape_config
from database.tournament_scrape.discover import (
    canonical_basename,
    discover_tournament_pdfs,
    select_downloads,
)
from database.tournament_scrape.urls import tournament_index_candidates

SAMPLE_2019_FRAGMENT = """
<html><body>
<a href="bm2019_akt_sb_he_aus.pdf">Ausschreibung</a>
<a href="bm2019_akt_sb_he_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_nb_he_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_einz_he_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_einz_da_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_dopp_he_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_dopp_da_erg.pdf">Ergebnisse</a>
<a href="bm2019_akt_mixed_erg.pdf">Ergebnisse</a>
<a href="bm2019_sen_einz_erg_sen_a.pdf">Sen A</a>
<a href="bm2019_sen_einz_erg_v_he1.pdf">V Männer 1</a>
<a href="bm2019_sen_trio_erg_sen_a.pdf">Sen A</a>
<a href="bm2019_jug_einz_erg_am_vr.pdf">A-männlich</a>
<a href="bm2019_akt_sb_he_start.pdf">Starteinteilung</a>
</body></html>
"""

SAMPLE_2013_FRAGMENT = """
<html><body>
<a href="bm2013_sb_herren_erg.pdf">Ergebnisse</a>
<a href="bm2013_nb_herren_erg.pdf">Ergebnisse</a>
<a href="bm2013_einz_he_erg.pdf">Ergebnisse</a>
<a href="bm2013_einz_da_erg.pdf">Ergebnisse</a>
<a href="bm2013_dopp_he_erg.pdf">Ergebnisse</a>
<a href="bm2013_dopp_da_erg.pdf">Ergebnisse</a>
<a href="ergebnisse/aktive_mixed/ergebnisse_bm_mixed_2013.pdf">Ergebnisse</a>
<a href="bm2013_sen_einz_erg_s_a.pdf">Se A</a>
<a href="bm2013_sen_einz_erg_v_1.pdf">V1 Herren</a>
<a href="bm2013_sen_trio_erg_sen_a.pdf">Senioren A</a>
</body></html>
"""

SAMPLE_2004_FRAGMENT = """
<html><body>
<a href="bm/bm_sb_he_erg.pdf">Ergebnisse</a>
<a href="bm/bm_nb_he_erg.pdf">Ergebnisse</a>
<a href="bm/bm_einz_h_erg_fi.pdf">Ergebnisse Herren</a>
<a href="bm/bm_einz_d_erg_fi.pdf">Ergebnisse Damen</a>
<a href="bm/bm_dop_he_erg.pdf">Ergebnisse Doppel Herren</a>
<a href="bm/bm_dop_da_erg.pdf">Ergebnisse Doppel Damen</a>
<a href="bm_senioren/bm_sen_einz_erg_sa.pdf">Sen A</a>
<a href="bm_senioren/bm_sen_einz_erg_vh1.pdf">Vers He 1</a>
<a href="bm_senioren/bm_sen_trio_erg_a.pdf">Senioren A</a>
</body></html>
"""

SAMPLE_2010_FRAGMENT = """
<html><body>
<a href="bm2011_nbm_h_erg.pdf">Ergebnisse alt</a>
<a href="bm2011_nbm_h_erg_neu.pdf">Ergebnisse</a>
<a href="bm2010_einz_erg_h.pdf">Herren</a>
<a href="bm2010_einz_erg_d.pdf">Damen</a>
</body></html>
"""

SAMPLE_2018_DOPPEL_FRAGMENT = """
<html><body>
<a href="bm2018_akt_dopp_m_erg.pdf">Herren Doppel</a>
<a href="bm2018_akt_dopp_f_erg.pdf">Damen Doppel</a>
</body></html>
"""

SAMPLE_2008_FRAGMENT = """
<html><body>
<a href="bm2009_sb_he_erg.pdf">Ergebnisse</a>
<a href="bm2009_nb_he_erg.pdf">Ergebnisse</a>
<a href="bm2009_einzel_erg_he.pdf">Herren</a>
<a href="bm2009_einzel_erg_da.pdf">Damen</a>
<a href="bm2009_mix_erg.pdf">Ergebnisse</a>
<a href="bm2009_sen_einz_erg_vh_1.pdf">V Männer 1</a>
<a href="bm2009_sen_trio_erg_si.pdf">Si A</a>
</body></html>
"""

SAMPLE_2007_XLS_FRAGMENT = """
<html><body>
<a href="bm2007_einz_erg.xls">Ergebnisse Einzel</a>
</body></html>
"""


def _discover(html: str, *, category_ids: list[str] | None = None):
    config = load_scrape_config()
    page_url = "http://example/saison2018-19/meisterschaften/indexm18-19.htm"
    return discover_tournament_pdfs(
        html,
        page_url=page_url,
        folder_slug="2018-19",
        config=config,
        category_ids=category_ids,
    )


def test_tournament_index_candidates_standard_and_plain() -> None:
    assert tournament_index_candidates("2008-09", "08-09") == [
        "http://sektion-bowling.bowling-bayern.de/dateien/saison2008-09/meisterschaften/indexm08-09.htm",
        "http://sektion-bowling.bowling-bayern.de/dateien/saison2008-09/meisterschaften/indexm.htm",
    ]
    assert tournament_index_candidates("2005-06", "05-06")[1].endswith("/indexm.htm")
    assert tournament_index_candidates("2004-05", "04-05")[1].endswith("/indexm.htm")


def test_discover_legacy_2010_filename_variants() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2010_FRAGMENT,
        page_url="http://example/saison2010-11/meisterschaften/indexm10-11.htm",
        folder_slug="2010-11",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item.basename for item in selected}
    assert by_category["nordbayerische-herren"] == "bm2011_nbm_h_erg_neu.pdf"
    assert by_category["bayerische-einzel-herren"] == "bm2010_einz_erg_h.pdf"
    assert by_category["bayerische-einzel-frauen"] == "bm2010_einz_erg_d.pdf"


def test_discover_legacy_2018_doppel_filename_variants() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2018_DOPPEL_FRAGMENT,
        page_url="http://example/saison2017-18/meisterschaften/indexm17-18.htm",
        folder_slug="2017-18",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item.basename for item in selected}
    assert by_category["bayerisches-doppel-herren"] == "bm2018_akt_dopp_m_erg.pdf"
    assert by_category["bayerisches-doppel-frauen"] == "bm2018_akt_dopp_f_erg.pdf"


def test_discover_legacy_2008_filename_variants() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2008_FRAGMENT,
        page_url="http://example/saison2008-09/meisterschaften/indexm08-09.htm",
        folder_slug="2008-09",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item.basename for item in selected}
    assert by_category["suedbayerische-herren"] == "bm2009_sb_he_erg.pdf"
    assert by_category["bayerische-einzel-herren"] == "bm2009_einzel_erg_he.pdf"
    assert by_category["bayerische-einzel-frauen"] == "bm2009_einzel_erg_da.pdf"


def test_discover_legacy_2004_subdirectory_paths() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2004_FRAGMENT,
        page_url="http://example/saison2004-05/meisterschaften/indexm.htm",
        folder_slug="2004-05",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item.basename for item in selected}
    assert by_category["suedbayerische-herren"] == "bm_sb_he_erg.pdf"
    assert by_category["bayerische-einzel-herren"] == "bm_einz_h_erg_fi.pdf"
    assert by_category["bayerisches-doppel-herren"] == "bm_dop_he_erg.pdf"
    assert by_category["bayerisches-doppel-frauen"] == "bm_dop_da_erg.pdf"
    sb_item = next(item for item in selected if item.category_id == "suedbayerische-herren")
    assert canonical_basename(sb_item, "2004-05") == "bm2005_sb_he_erg.pdf"
    dopp_item = next(item for item in selected if item.category_id == "bayerisches-doppel-herren")
    assert canonical_basename(dopp_item, "2004-05") == "bm2005_dop_he_erg.pdf"


def test_discover_primary_categories_from_2019_fragment() -> None:
    discovered = _discover(SAMPLE_2019_FRAGMENT)
    selected = select_downloads(discovered, load_scrape_config())
    by_category = {item.category_id: item.basename for item in selected}

    assert by_category["suedbayerische-herren"] == "bm2019_akt_sb_he_erg.pdf"
    assert by_category["nordbayerische-herren"] == "bm2019_akt_nb_he_erg.pdf"
    assert by_category["bayerische-einzel-herren"] == "bm2019_akt_einz_he_erg.pdf"
    assert by_category["bayerische-einzel-frauen"] == "bm2019_akt_einz_da_erg.pdf"
    assert by_category["bayerisches-doppel-herren"] == "bm2019_akt_dopp_he_erg.pdf"
    assert by_category["bayerisches-doppel-frauen"] == "bm2019_akt_dopp_da_erg.pdf"
    assert by_category["bayerische-mixed"] == "bm2019_akt_mixed_erg.pdf"


def test_discover_ignores_jugend_and_non_result_pdfs() -> None:
    discovered = _discover(SAMPLE_2019_FRAGMENT)
    basenames = {item.basename for item in discovered}
    assert "bm2019_jug_einz_erg_am_vr.pdf" not in basenames
    assert "bm2019_akt_sb_he_start.pdf" not in basenames


def test_discover_multi_file_senioren_and_versehrte() -> None:
    discovered = _discover(SAMPLE_2019_FRAGMENT)
    selected = select_downloads(discovered, load_scrape_config())
    senioren = [item.basename for item in selected if item.category_id == "bayerische-senioren"]
    versehrte = [item.basename for item in selected if item.category_id == "bayerische-versehrte"]
    trio = [item.basename for item in selected if item.category_id == "bayerische-senioren-trio"]

    assert "bm2019_sen_einz_erg_sen_a.pdf" in senioren
    assert "bm2019_sen_einz_erg_v_he1.pdf" in versehrte
    assert "bm2019_sen_trio_erg_sen_a.pdf" in trio


def test_discover_legacy_2013_filename_variants() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2013_FRAGMENT,
        page_url="http://example/saison2012-13/meisterschaften/indexm12-13.htm",
        folder_slug="2012-13",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item.basename for item in selected}

    assert by_category["suedbayerische-herren"] == "bm2013_sb_herren_erg.pdf"
    assert by_category["nordbayerische-herren"] == "bm2013_nb_herren_erg.pdf"
    assert by_category["bayerische-einzel-herren"] == "bm2013_einz_he_erg.pdf"
    assert by_category["bayerische-mixed"] == "ergebnisse_bm_mixed_2013.pdf"


def test_discover_bm_2007_dual_xls_workbook() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        SAMPLE_2007_XLS_FRAGMENT,
        page_url="http://example/saison2006-07/meisterschaften/indexm.htm",
        folder_slug="2006-07",
        config=config,
    )
    selected = select_downloads(discovered, config)
    by_category = {item.category_id: item for item in selected}
    assert "bayerische-einzel-herren" in by_category
    assert "bayerische-einzel-frauen" in by_category
    assert by_category["bayerische-einzel-herren"].basename == "bm2007_einz_erg.xls"
    assert by_category["bayerische-einzel-frauen"].basename == "bm2007_einz_erg.xls"


def test_category_filter_limits_discovery() -> None:
    discovered = _discover(SAMPLE_2019_FRAGMENT, category_ids=["suedbayerische-herren"])
    assert {item.category_id for item in discovered} == {"suedbayerische-herren"}


def test_canonical_basename_prefixes_year_for_legacy_paths() -> None:
    config = load_scrape_config()
    discovered = discover_tournament_pdfs(
        '<a href="ergebnisse/aktive_doppel/doppel_m_erg.pdf">Ergebnisse</a>',
        page_url="http://example/saison2016-17/meisterschaften/indexm16-17.htm",
        folder_slug="2016-17",
        config=config,
        category_ids=["bayerisches-doppel-herren"],
    )
    item = discovered[0]
    assert canonical_basename(item, "2016-17") == "bm2017_doppel_m_erg.pdf"


def test_resolve_category_ids_from_tournament_codes() -> None:
    from database.tournament_scrape.categories import resolve_category_ids

    assert resolve_category_ids(tournaments=["sbm", "nbm"]) == [
        "suedbayerische-herren",
        "nordbayerische-herren",
    ]
    assert resolve_category_ids(tournaments=["sbm,nbm,bm,bm_f,bm_md,bm_dd"]) == [
        "suedbayerische-herren",
        "nordbayerische-herren",
        "bayerische-einzel-herren",
        "bayerische-einzel-frauen",
        "bayerisches-doppel-herren",
        "bayerisches-doppel-frauen",
    ]
    assert resolve_category_ids() is None


def test_filter_importable_tournament_codes_excludes_doubles() -> None:
    from database.tournament_scrape.categories import (
        filter_importable_category_ids,
        filter_importable_tournament_codes,
        resolve_category_ids,
    )

    assert filter_importable_tournament_codes(["sbm", "bm_md", "bm_dd"]) == ["sbm"]
    category_ids = filter_importable_category_ids(
        resolve_category_ids(tournaments=["sbm,nbm,bm,bm_f,bm_md,bm_dd"]) or []
    )
    assert "bayerisches-doppel-herren" not in category_ids
    assert "bayerisches-doppel-frauen" not in category_ids


def test_download_tournaments_range_invokes_each_season(monkeypatch) -> None:
    from scripts import scrape_legacy_tournaments as mod

    calls: list[str] = []

    def fake_download(season: str, **kwargs: object) -> dict:
        calls.append(season)
        return {
            "season": season,
            "discovered": 1,
            "selected": 1,
            "skipped_existing": 0,
            "downloaded": 0 if kwargs.get("dry_run") else 1,
            "failed": 0,
            "files": [],
        }

    monkeypatch.setattr(mod, "download_season_tournaments", fake_download)
    monkeypatch.setattr(mod, "_append_tournament_log", lambda _record: None)
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)

    report = mod.download_tournaments_range(first_year=2004, last_year=2006, dry_run=True)

    assert calls == ["2004-05", "2005-06", "2006-07"]
    assert report["seasons_attempted"] == 3
    assert report["seasons_with_results"] == 3
    assert report["selected"] == 3
    assert report["dry_run"] is True


def test_download_tournaments_range_rejects_inverted_years() -> None:
    from scripts import scrape_legacy_tournaments as mod

    try:
        mod.download_tournaments_range(first_year=2018, last_year=2004)
    except ValueError as exc:
        assert "must be <=" in str(exc)
    else:
        raise AssertionError("expected ValueError")
