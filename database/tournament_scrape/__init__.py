"""Legacy BSKV tournament PDF discovery and download."""

from database.tournament_scrape.categories import TournamentCategory, load_scrape_config
from database.tournament_scrape.discover import (
    canonical_basename,
    discover_tournament_pdfs,
    meisterschaften_index_url,
    select_downloads,
)
from database.tournament_scrape.urls import (
    fetch_tournament_index_html,
    resolve_tournament_index_url,
    tournament_index_candidates,
)

__all__ = [
    "TournamentCategory",
    "canonical_basename",
    "discover_tournament_pdfs",
    "fetch_tournament_index_html",
    "load_scrape_config",
    "meisterschaften_index_url",
    "resolve_tournament_index_url",
    "select_downloads",
    "tournament_index_candidates",
]
