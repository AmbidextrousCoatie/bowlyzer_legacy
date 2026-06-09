"""Player registry discovery on legacy scrape season hubs."""

from scripts.scrape_legacy_liga import (
    discover_player_registry_paths,
    select_player_registry_downloads,
)


SAMPLE_HTML = """
<html><body>
<tr bgcolor="#bbc2a9">
  <td><b>Aktive Mitglieder der Saison 2013/14</b>
  <span class="kleiner">Endstand vom 30. Juni 2014
  <a href="allgemein/aktive_Endstand_140630.xls">Download...</a></span>
  <a href="allgemein/aktive_130313.xls">Zwischenstand</a>
  </td>
</tr>
</body></html>
"""


def test_discover_player_registry_paths_finds_endstand_and_interim() -> None:
    found = discover_player_registry_paths(
        SAMPLE_HTML,
        folder_slug="2013-14",
        page_url="http://example/saison2013-14/indexs13-14.htm",
    )
    rels = {item["rel_path"] for item in found}
    assert "saison2013-14/allgemein/aktive_Endstand_140630.xls" in rels
    assert "saison2013-14/allgemein/aktive_130313.xls" in rels


def test_discover_ignores_cross_season_links() -> None:
    html = """
    <a href="http://sektion-bowling.bowling-bayern.de/dateien/saison2008-09/allgemein/aktive_090528.xls">old</a>
    <a href="allgemein/aktive_100705.xls">current</a>
    """
    found = discover_player_registry_paths(
        html,
        folder_slug="2009-10",
        page_url="http://example/saison2009-10/indexs09-10.htm",
    )
    rels = {item["rel_path"] for item in found}
    assert "saison2009-10/allgemein/aktive_100705.xls" in rels
    assert not any("2008-09" in rel for rel in rels)


def test_select_player_registry_prefers_endstand() -> None:
    found = discover_player_registry_paths(
        SAMPLE_HTML,
        folder_slug="2013-14",
        page_url="http://example/saison2013-14/indexs13-14.htm",
    )
    selected = select_player_registry_downloads(found)
    assert len(selected) == 1
    assert selected[0]["preferred"] is True
    assert "Endstand" in selected[0]["rel_path"]
