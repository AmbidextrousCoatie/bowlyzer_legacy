# Verein vs Club disambiguation (future)

## Context

German bowling org hierarchy (simplified):

| Tier | Example | In Bowl-A-Lyzer today |
|------|---------|------------------------|
| National association | DBU | Not modeled |
| State association | BBU | Not modeled |
| **Verein** | BV 68 Regensburg | Sometimes appears as tournament `Club` |
| **Club** (Einzelmitglied / Mannschaft club) | REG - BC Castra Regina Regensburg | League teams + `clubs_registry` canonical names |

Tournament exports may label a player at **Verein** level (`BV 68 Regensburg`) or **Club** level (`REG - BC Castra Regina Regensburg`). League and Clubpokal are club-level; open/state/national championships often mix both.

## Proposed simple rule (not implemented)

1. Maintain `verein_club.csv`: known Verein → member Club(s).
2. When a tournament row has a Verein label (not resolving to a league club):
   - Same season: did this player compete for a club under that Verein in league?
   - **Yes** → replace Verein with that club (canonical from registry).
   - **No** → keep Verein as display identity (or map to a Verein canonical if we add that layer).

## Effort estimate (discussion only)

| Piece | Scope | Rough effort |
|-------|--------|--------------|
| `verein_club.csv` schema + manual seed | Curated lookup (tens of Vereine, not hundreds) | **0.5–1 d** data + import script |
| Detect “Verein label” vs “club label” | Heuristics (prefix `BV \d+`, no `REG -`, not in registry) + optional allowlist | **1 d** |
| Season player ↔ league club join | Reuse merged league + tournament by `Player ID` / name, same `Season` | **1–2 d** (edge cases: substitutes, mid-season transfers) |
| Apply in `normalize_tournament_dataframe` | After `clubs_registry`, before quality audit | **0.5 d** |
| Validation UI / audit rows for Verein fallback | Show “kept as Verein” vs “promoted to club” | **0.5–1 d** |
| Tests + docs | Fixture seasons with mixed labels | **1 d** |

**Total: ~4–6 days** for a first useful version, assuming manual `verein_club.csv` maintenance (no auto-scrape from GF).

## Risks / open questions

- **Ambiguity**: one Verein, multiple clubs in same city — league history may not uniquely identify club for a player who only plays tournaments.
- **Out-of-league players**: Open championships → no league row → rule correctly keeps Verein; product must not show wrong club.
- **Data model**: do we store Verein as a separate dimension (matrix, filters) or only as a normalization fallback?
- **Scope creep**: modeling BBU/DBU tiers is out of scope; keep Verein/Club as a two-level alias problem.

## Current state (2026-07)

- `clubs_registry` + `club_mapping.csv` handle **club-level** GF aliases (55 manual mappings imported).
- No Verein layer; labels like `BV 68 Regensburg` remain unresolved until mapped or covered by future work.
