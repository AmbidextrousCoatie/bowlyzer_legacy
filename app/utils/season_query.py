"""Season strings in URL query params."""



from __future__ import annotations



import re

from typing import Optional

from urllib.parse import unquote



_SEASON_LABEL = re.compile(r"^\d{2}[/\-]\d{2}$")





def normalize_season_query_value(raw: Optional[str]) -> Optional[str]:

    """

    Accept ``14/15``, ``14-15``, or ``14%2F15``; return canonical ``14/15`` for data lookups.

    Prefer ``season=14-15`` on the wire when a reverse proxy sits in front of Flask
    (nginx often breaks ``season=14/15`` and ``season=14%2F15``).

    """

    if raw is None:

        return None

    text = unquote(str(raw).strip())

    if not text:

        return None

    if _SEASON_LABEL.match(text):

        return text.replace("-", "/")

    return text





def season_for_api_query(display_season: str) -> str:

    """Canonical season label for query strings (``14/15``). Legacy ``14-15`` is normalized."""

    normalized = normalize_season_query_value(display_season)

    return normalized if normalized is not None else str(display_season).strip()


