"""Resolve Meisterschaften index URLs across legacy season layout variants."""

from __future__ import annotations

from typing import Callable, Sequence

BASE_HOST = "http://sektion-bowling.bowling-bayern.de/dateien"


def tournament_index_candidates(folder_slug: str, liga_slug: str) -> list[str]:
    """
    Candidate index pages for a bowling season.

    Layout history on sektion-bowling.bowling-bayern.de:

    - 2008-09 .. present (most seasons):
      ``saison{YYYY-YY}/meisterschaften/indexm{yy-yy}.htm``
    - 2004-05 .. 2007-08 (partial):
      ``saison{YYYY-YY}/meisterschaften/indexm.htm`` (no year suffix)
    - 2005-06 season hub also links the plain ``indexm.htm`` page; the
      ``indexm{yy-yy}.htm`` variant does not exist for that season.

    The season hub ``indexs{yy-yy}.htm`` is intentionally omitted here — it
    only mirrors a link to the Meisterschaften index and carries fewer PDFs.
    """
    folder = folder_slug.strip()
    liga = liga_slug.strip()
    return [
        f"{BASE_HOST}/saison{folder}/meisterschaften/indexm{liga}.htm",
        f"{BASE_HOST}/saison{folder}/meisterschaften/indexm.htm",
    ]


def resolve_tournament_index_url(
    folder_slug: str,
    liga_slug: str,
    *,
    fetch_status: Callable[[str], tuple[int, bytes]] | None = None,
) -> tuple[str, list[str]]:
    """
    Return the first reachable tournament index URL and every candidate tried.

    When ``fetch_status`` is omitted, all candidates are returned with the
    first one preferred (callers probe HTTP themselves).
    """
    candidates = tournament_index_candidates(folder_slug, liga_slug)
    if fetch_status is None:
        return candidates[0], candidates

    for url in candidates:
        try:
            status, body = fetch_status(url)
        except OSError:
            continue
        if status == 200 and body:
            return url, candidates
    return candidates[-1], candidates


def fetch_tournament_index_html(
    folder_slug: str,
    liga_slug: str,
    fetch_status: Callable[[str], tuple[int, bytes]],
) -> tuple[str, str, list[str]]:
    """Fetch the first working Meisterschaften index page; return url, html, candidates tried."""
    candidates = tournament_index_candidates(folder_slug, liga_slug)
    errors: list[str] = []
    for url in candidates:
        try:
            status, body = fetch_status(url)
        except OSError as exc:
            errors.append(f"{url}: {exc}")
            continue
        if status == 200 and body:
            html = body.decode("iso-8859-1", errors="replace")
            return url, html, candidates
        errors.append(f"{url}: HTTP {status}")
    detail = "; ".join(errors) or "no candidates"
    raise FileNotFoundError(f"No tournament index for season {folder_slug} ({detail})")
