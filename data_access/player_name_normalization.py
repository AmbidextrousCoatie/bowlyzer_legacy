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
from typing import Iterable, Tuple

_COMMA_BEFORE = re.compile(r"\s+,")
_COMMA_AFTER = re.compile(r",\s*")

# Noble / particle prefixes merged onto family for identity matching.
FAMILY_PARTICLES = frozenset({"von", "van"})

# Senior / junior markers (same person over time — cf. marriage aliases).
GENERATION_MARKERS = frozenset({"sen", "jun", "sr", "jr"})

# Minimum length for the shorter given-name fragment in substring matching.
GIVEN_SUBSTRING_MIN_LEN = 3

# Allow bare prefix nicknames (``Alex`` / ``Alexander``) from this length upward.
GIVEN_SUBSTRING_NICKNAME_MIN_LEN = 4

# Shorter bare prefix (``Max`` / ``Maximilian``) when shorter is well under half the longer.
GIVEN_SUBSTRING_SHORT_PREFIX_MAX_RATIO = 0.5


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


def given_names_substring_equivalent(
    left: str,
    right: str,
    *,
    min_len: int = GIVEN_SUBSTRING_MIN_LEN,
    nickname_min_len: int = GIVEN_SUBSTRING_NICKNAME_MIN_LEN,
) -> bool:
    """
    Bidirectional given-name substring match for the same family + player id.

    Covers nicknames (``Alex`` ↔ ``Alexander``) and extra middle tokens
    (``Carina`` ↔ ``Carina Mareen``). Requires the shorter side to be a prefix
    of the longer, with a word boundary (space/hyphen) or nickname-length prefix.
    """
    a = collapse_whitespace(left).lower()
    b = collapse_whitespace(right).lower()
    if not a or not b:
        return False
    if a == b:
        return True
    for shorter, longer in ((a, b), (b, a)):
        if len(shorter) < min_len or len(shorter) >= len(longer):
            continue
        if not longer.startswith(shorter):
            continue
        tail = longer[len(shorter) :]
        if not tail:
            return True
        if tail[0] in "- ":
            return True
        if len(shorter) >= nickname_min_len:
            return True
        if len(shorter) / len(longer) < GIVEN_SUBSTRING_SHORT_PREFIX_MAX_RATIO:
            return True
    return False


def split_generation_suffix(text: str) -> Tuple[str, str]:
    """
    Split a trailing senior/junior marker from a family or given fragment.

    ``Glasl jun.`` → ``(Glasl, jun)``; ``Hans-Jürgen sen`` → ``(Hans-Jürgen, sen)``.
    """
    cleaned = collapse_whitespace(text)
    if not cleaned:
        return "", ""
    parts = cleaned.split()
    if len(parts) >= 2 and parts[-1].lower().rstrip(".") in GENERATION_MARKERS:
        return " ".join(parts[:-1]).strip(), parts[-1].lower().rstrip(".")
    return cleaned, ""


def _extract_particle_from_family(family: str) -> Tuple[str, str]:
    """Return ``(family_core, particle)`` with von/van moved off the family tokens."""
    cleaned = collapse_whitespace(family)
    if not cleaned:
        return "", ""
    parts = cleaned.split()
    if parts[0].lower() in FAMILY_PARTICLES:
        return " ".join(parts[1:]).strip(), parts[0].lower()
    if len(parts) >= 2 and parts[-1].lower() in FAMILY_PARTICLES:
        return " ".join(parts[:-1]).strip(), parts[-1].lower()
    return cleaned, ""


def _extract_particle_from_given(given: str) -> Tuple[str, str]:
    """Return ``(given_core, particle)`` when von/van trails the given (``Susanne van``)."""
    cleaned = collapse_whitespace(given)
    if not cleaned:
        return "", ""
    parts = cleaned.split()
    if len(parts) >= 2 and parts[-1].lower() in FAMILY_PARTICLES:
        return " ".join(parts[:-1]).strip(), parts[-1].lower()
    return cleaned, ""


def normalize_particle_name(name: str) -> str:
    """
    Comparison-oriented ``Family, Given`` with von/van on the family and sen/jun stripped.

    Examples:
      ``Alt, Christiane von`` → ``von Alt, Christiane``
      ``Weverberg Van, Susanne`` → ``van Weverberg, Susanne``
      ``Glasl jun., Hans-Jürgen`` → ``Glasl, Hans-Jürgen``
      ``Hans-Jürgen Glasl sen.`` → ``Glasl, Hans-Jürgen``
    """
    label = normalize_player_label(name)
    if not label:
        return ""

    if "," in label:
        family, _, given = label.partition(",")
        family, given = family.strip(), given.strip()
    else:
        body, _whole_gen = split_generation_suffix(label)
        family, given = parse_player_name_parts(body)

    family, _ = split_generation_suffix(family)
    given, _ = split_generation_suffix(given)

    fam_core, fam_lead = _extract_particle_from_family(family)
    given_core, given_trail = _extract_particle_from_given(given)
    particle = fam_lead or given_trail
    family_out = f"{particle} {fam_core}".strip() if particle else fam_core
    return _format_family_given(family_out, given_core)


def name_identity_key(name: str) -> Tuple[str, str]:
    """
    Stable ``(family, given)`` key for same-person matching (particles + sen/jun normalized).
    """
    canonical = normalize_particle_name(name)
    family, given = parse_player_name_parts(canonical)
    return family.casefold(), given.casefold()


def names_share_identity(left: str, right: str) -> bool:
    return name_identity_key(left) == name_identity_key(right)


def group_canonical_target(names: Iterable[str]) -> str | None:
    """
    When every name in a group shares at least one candidate canonical form, return it.

    Prefers an explicit comma label from the group when it matches the shared set.
    """
    names_list = [n for n in names if normalize_player_name_whitespace(n)]
    if not names_list:
        return None

    identity_keys = {name_identity_key(name) for name in names_list}
    if len(identity_keys) == 1:
        # Same person (particles / sen/jun / format) — keep an observed display spelling.
        for name in names_list:
            if "," in name:
                return normalize_player_label(name)
        return normalize_player_label(names_list[0])

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
