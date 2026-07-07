"""Shared tournament postprocessed CSV schema."""

from __future__ import annotations

POSTPROCESSED_HEADERS: list[str] = [
    "Season",
    "Date",
    "Location",
    "Event Type",
    "Event Name",
    "Round Number",
    "Round Name",
    "Player",
    "Player ID",
    "Club",
    "Game Number",
    "Score",
    "Handicap",
    "A Priori Average",
    "Handicap Reference",
    "Cumulative Score",
    "Stage Rank",
    "Cut Line",
    "Cut Basis",
    "Overall Cumulative Score",
]

ROUND_LABELS_PDF_2016: dict[int, tuple[str, str]] = {
    1: ("Vorrunde", "Vorlauf"),
    2: ("Zwischenlauf", "Zwischenlauf"),
    3: ("Finalrunde", "Finalrunde"),
}


def season_label_from_calendar_year(year: int) -> str:
    prev_yy = (year - 1) % 100
    curr_yy = year % 100
    return f"{prev_yy:02d}/{curr_yy:02d}"
