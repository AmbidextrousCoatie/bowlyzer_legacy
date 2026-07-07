"""Tournament scrape category definitions (database/config/legacy_tournament_scrape.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

from database.paths import REPO_ROOT

DEFAULT_CONFIG_PATH = REPO_ROOT / "database" / "config" / "legacy_tournament_scrape.json"

# CLI shorthand codes → category ids in legacy_tournament_scrape.json
TOURNAMENT_CODES: dict[str, str] = {
    "sbm": "suedbayerische-herren",
    "nbm": "nordbayerische-herren",
    "bm": "bayerische-einzel-herren",
    "bm_f": "bayerische-einzel-frauen",
}


@dataclass(frozen=True)
class TournamentCategory:
    id: str
    label: str
    multi_file: bool
    filename_patterns: Sequence[re.Pattern[str]]
    exclude_href_patterns: Sequence[re.Pattern[str]] = field(default_factory=tuple)


@dataclass(frozen=True)
class TournamentScrapeConfig:
    schema_version: int
    global_exclude_href_patterns: Sequence[re.Pattern[str]]
    categories: List[TournamentCategory]


def _compile_patterns(raw: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(item, re.IGNORECASE) for item in raw)


def load_scrape_config(path: str | Path | None = None) -> TournamentScrapeConfig:
    config_path = Path(path or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise FileNotFoundError(f"Tournament scrape config not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    categories: List[TournamentCategory] = []
    for item in raw.get("categories") or []:
        categories.append(
            TournamentCategory(
                id=str(item["id"]),
                label=str(item.get("label") or item["id"]),
                multi_file=bool(item.get("multi_file", False)),
                filename_patterns=_compile_patterns(item.get("filename_patterns") or []),
                exclude_href_patterns=_compile_patterns(item.get("exclude_href_patterns") or []),
            )
        )
    return TournamentScrapeConfig(
        schema_version=int(raw.get("schema_version", 1)),
        global_exclude_href_patterns=_compile_patterns(raw.get("global_exclude_href_patterns") or []),
        categories=categories,
    )


def category_by_id(config: TournamentScrapeConfig, category_id: str) -> TournamentCategory:
    for category in config.categories:
        if category.id == category_id:
            return category
    known = ", ".join(category.id for category in config.categories)
    raise KeyError(f"Unknown tournament category {category_id!r}; known: {known}")


def resolve_category_ids(
    *,
    tournaments: Sequence[str] | None = None,
    category_ids: Sequence[str] | None = None,
) -> list[str] | None:
    """
    Merge ``--tournament`` shorthand codes (sbm, nbm, bm, bm_f) with explicit ``--category`` ids.

    Returns ``None`` when neither is set (all configured categories).
    """
    resolved: list[str] = []
    seen: set[str] = set()

    def add(category_id: str) -> None:
        if category_id not in seen:
            seen.add(category_id)
            resolved.append(category_id)

    for category_id in category_ids or []:
        add(category_id.strip())

    for raw in tournaments or []:
        for token in raw.split(","):
            code = token.strip().lower()
            if not code:
                continue
            mapped = TOURNAMENT_CODES.get(code)
            if mapped is None:
                known = ", ".join(sorted(TOURNAMENT_CODES))
                raise ValueError(f"Unknown tournament code {code!r}; known: {known}")
            add(mapped)

    return resolved or None
