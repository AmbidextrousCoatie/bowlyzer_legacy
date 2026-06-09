"""
Parse player display labels into canonical ``Family, Given names`` form.

Rules:
  - Collapse runs of whitespace and trim ends.
  - Comma present: family before comma, given name(s) after.
  - No comma, one token: that token is the family name.
  - No comma, two tokens: either ``Given Family`` or ``Family Given`` (reversal-equivalent).
  - No comma, three or more tokens: family = last word; given = everything before it.
"""

from __future__ import annotations

import re

_COMMA_BEFORE = re.compile(r"\s+,")
_COMMA_AFTER = re.compile(r",\s*")


def collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_player_label(value: object) -> str:
    """
    Normalize a raw player label for identity comparison.

    Collapses whitespace, trims ends, and standardizes comma spacing
    (``Mihatsch , Rudolf`` → ``Mihatsch, Rudolf``).
    """
    raw = str(value).strip() if value is not None else ""
    if not raw or raw.lower() in {"nan", "none"}:
        return ""
    s = collapse_whitespace(raw)
    s = _COMMA_BEFORE.sub(",", s)
    s = _COMMA_AFTER.sub(", ", s)
    return s


def normalize_player_name_whitespace(value: object) -> str:
    return normalize_player_label(value)


def _format_family_given(family: str, given: str) -> str:
    if not family:
        return ""
    if given:
        return f"{family}, {given}"
    return family


def parse_player_name_parts(name: str) -> tuple[str, str]:
    """
    Return ``(family, given)`` from a raw player label.

    For two-token labels without a comma, uses the ``Given Family`` reading
    (last word = family). Use ``candidate_canonical_names`` when reversal may apply.
    """
    s = normalize_player_name_whitespace(name)
    if not s:
        return "", ""
    if "," in s:
        family, _, given = s.partition(",")
        return family.strip(), given.strip()
    parts = s.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def candidate_canonical_names(name: str) -> frozenset[str]:
    """
    Possible canonical ``Family, Given`` strings for a raw label.

    Two-token labels without a comma admit both token orderings, so
    ``Köse, Sahin``, ``Sahin Köse``, and ``Köse Sahin`` share candidates.
    """
    s = normalize_player_name_whitespace(name)
    if not s:
        return frozenset()
    if "," in s:
        return frozenset({_format_family_given(*parse_player_name_parts(s))})
    parts = s.split(" ")
    if len(parts) == 1:
        return frozenset([parts[0]])
    if len(parts) == 2:
        first, second = parts
        return frozenset(
            [
                _format_family_given(second, first),
                _format_family_given(first, second),
            ]
        )
    return frozenset([_format_family_given(parts[-1], " ".join(parts[:-1]))])


def group_canonical_target(names: Iterable[str]) -> str | None:
    """
    When every name in a group shares at least one candidate canonical form, return it.

    Prefers an explicit comma label from the group when it matches the shared set.
    """
    names_list = [n for n in names if normalize_player_name_whitespace(n)]
    if not names_list:
        return None
    candidate_sets = [candidate_canonical_names(n) for n in names_list]
    common = candidate_sets[0].intersection(*candidate_sets[1:])
    if not common:
        return None
    if len(common) == 1:
        return next(iter(common))
    for name in names_list:
        if "," in name:
            label = canonicalize_player_name(name)
            if label in common:
                return label
    return sorted(common)[0]


def canonicalize_player_name(name: str) -> str:
    """
    Primary display canonical ``Family, Given names``.

    Ambiguous two-token labels without a comma default to ``Given Family``
    (last word = family), matching typical German ``Vorname Nachname`` entry.
    """
    family, given = parse_player_name_parts(name)
    return _format_family_given(family, given)
