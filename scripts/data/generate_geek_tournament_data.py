"""
Generate synthetic multi-season tournament datasets.

Outputs per tournament family:
1) clean per-game CSV
2) postprocessed CSV with stage cumulative/rank/cut line
3) roster metadata CSV (franchise/faction/power/consistency)
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "database" / "data"

GEEK_CLEAN_OUT = DATA_DIR / "tournament_geek_classic_2024_2026_clean.csv"
GEEK_POST_OUT = DATA_DIR / "tournament_geek_classic_2024_2026_postprocessed.csv"
GEEK_ROSTER_OUT = DATA_DIR / "tournament_geek_classic_2024_2026_roster.csv"

MYTH_CLEAN_OUT = DATA_DIR / "tournament_mythic_legends_2024_2026_clean.csv"
MYTH_POST_OUT = DATA_DIR / "tournament_mythic_legends_2024_2026_postprocessed.csv"
MYTH_ROSTER_OUT = DATA_DIR / "tournament_mythic_legends_2024_2026_roster.csv"
CLASH_CLEAN_OUT = DATA_DIR / "tournament_clash_imaginary_entities_2024_2026_clean.csv"
CLASH_POST_OUT = DATA_DIR / "tournament_clash_imaginary_entities_2024_2026_postprocessed.csv"
COMBINED_POST_OUT = DATA_DIR / "tournament_combined_2024_2026_postprocessed.csv"


@dataclass(frozen=True)
class Stage:
    number: int
    name: str
    date: str
    games: int
    cut_to: int | None


STAGES: List[Stage] = [
    Stage(1, "Qualifying", "{season}-09-18", 8, 40),
    Stage(2, "Round 2", "{season}-09-19", 6, 20),
    Stage(3, "Final", "{season}-09-20", 6, None),
]

CLASH_STAGES: List[Stage] = [
    Stage(1, "Qualifying A", "{season}-10-02", 4, None),
    Stage(2, "Qualifying B", "{season}-10-02", 4, 20),
    Stage(3, "Positioning", "{season}-10-03", 4, 5),
    Stage(4, "Elimination", "{season}-10-03", 4, None),
]


def build_geek_roster() -> List[Dict[str, str]]:
    # 10 franchises (5 fantasy + 5 sci-fi), 2 factions each, 4 chars per faction => 80
    franchises = [
        ("Star Wars", "Jedi Order", ["Luke Skywalker", "Obi-Wan Kenobi", "Ahsoka Tano", "Mace Windu"]),
        ("Star Wars", "Sith Empire", ["Darth Vader", "Emperor Palpatine", "Darth Maul", "Count Dooku"]),
        ("Lord of the Rings", "Free Peoples", ["Gandalf", "Aragorn", "Legolas", "Gimli"]),
        ("Lord of the Rings", "Forces of Mordor", ["Sauron", "Witch-king", "Saruman", "Uruk-hai Lurtz"]),
        ("Harry Potter", "Order of the Phoenix", ["Harry Potter", "Hermione Granger", "Albus Dumbledore", "Severus Snape"]),
        ("Harry Potter", "Death Eaters", ["Lord Voldemort", "Bellatrix Lestrange", "Lucius Malfoy", "Barty Crouch Jr."]),
        ("Game of Thrones", "Stark-Targaryen Alliance", ["Jon Snow", "Daenerys Targaryen", "Arya Stark", "Bran Stark"]),
        ("Game of Thrones", "Lannister-Crown", ["Cersei Lannister", "Jaime Lannister", "Tywin Lannister", "The Mountain"]),
        ("LucasArts Games", "Jedi Knight Era", ["Kyle Katarn", "Mara Jade", "Jaden Korr", "Jan Ors"]),
        ("LucasArts Games", "Monkey Island & Legacy", ["Guybrush Threepwood", "LeChuck", "Elaine Marley", "Manny Calavera"]),
        ("Dune", "House Atreides", ["Paul Atreides", "Lady Jessica", "Duncan Idaho", "Gurney Halleck"]),
        ("Dune", "Harkonnen-Sardaukar", ["Baron Harkonnen", "Feyd-Rautha", "Count Fenring", "Glossu Rabban"]),
        ("Star Trek", "Federation", ["Jean-Luc Picard", "Spock", "Benjamin Sisko", "Kathryn Janeway"]),
        ("Star Trek", "Klingon-Romulan", ["Worf", "Gowron", "Commander Sela", "General Chang"]),
        ("Mass Effect", "Alliance Crew", ["Commander Shepard", "Garrus Vakarian", "Liara T'Soni", "Tali'Zorah"]),
        ("Mass Effect", "Cerberus-Reapers", ["Illusive Man", "Harbinger", "Kai Leng", "Saren Arterius"]),
        ("Warhammer 40K", "Imperium", ["Roboute Guilliman", "Marneus Calgar", "Saint Celestine", "Inquisitor Eisenhorn"]),
        ("Warhammer 40K", "Chaos", ["Abaddon the Despoiler", "Magnus the Red", "Ahriman", "Kharn the Betrayer"]),
        ("Disney Characters", "Disney Heroes", ["Mickey Mouse", "Mulan", "Simba", "Moana"]),
        ("Disney Characters", "Disney Villains", ["Maleficent", "Scar", "Ursula", "Jafar"]),
    ]
    roster = []
    for franchise, faction, chars in franchises:
        for c in chars:
            roster.append({"franchise": franchise, "club": f"{franchise} - {faction}", "player": c})
    return roster


def build_mythology_roster() -> List[Dict[str, str]]:
    # Smaller field than geek roster: 6 myth groups x 2 factions x 4 chars = 48 players.
    groups = [
        ("Greek Myth", "Olympians", ["Zeus", "Athena", "Apollo", "Artemis"]),
        ("Greek Myth", "Titans & Primordials", ["Cronus", "Rhea", "Atlas", "Hyperion"]),
        ("Egyptian Myth", "Solar Court", ["Ra", "Horus", "Bastet", "Thoth"]),
        ("Egyptian Myth", "Underworld Powers", ["Osiris", "Anubis", "Set", "Sekhmet"]),
        ("Norse Myth", "Aesir", ["Odin", "Thor", "Tyr", "Frigg"]),
        ("Norse Myth", "Giants & Tricksters", ["Loki", "Hel", "Fenrir", "Jormungandr"]),
        ("Celtic Myth", "Tuatha De Danann", ["The Dagda", "Lugh", "Brigid", "Nuada"]),
        ("Celtic Myth", "Fomorians", ["Balor", "Bres", "Elatha", "Tethra"]),
        ("Mesopotamian Myth", "Sky Kings", ["Marduk", "Ishtar", "Shamash", "Nanna"]),
        ("Mesopotamian Myth", "Chaos Ancients", ["Tiamat", "Kingu", "Nergal", "Ereshkigal"]),
        ("Hindu Myth", "Devas", ["Indra", "Vishnu", "Shiva", "Durga"]),
        ("Hindu Myth", "Asuras", ["Mahishasura", "Ravana", "Hiranyakashipu", "Vritra"]),
    ]
    roster = []
    for franchise, faction, chars in groups:
        for c in chars:
            roster.append({"franchise": franchise, "club": f"{franchise} - {faction}", "player": c})
    return roster


def assign_attributes(
    roster: List[Dict[str, str]],
    rng: random.Random,
    id_min: int = 50000,
    id_max: int = 99999,
) -> List[Dict[str, Any]]:
    # Power by role-ish ordering + some variety, consistency random [0..1]
    # Random player IDs in a safe range, unique.
    ids = rng.sample(range(id_min, id_max), len(roster))
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(roster):
        # First 2 in each faction tend to be stronger.
        in_faction_idx = i % 4
        base_power = 10 - in_faction_idx * 2
        power = max(1, min(10, base_power + rng.randint(-1, 1)))
        consistency = round(rng.uniform(0.2, 0.95), 3)
        out.append(
            {
                **row,
                "player_id": str(ids[i]),
                "power": power,
                "consistency": consistency,
            }
        )
    return out


def score_game(
    power: int,
    consistency: float,
    game_idx: int,
    stage_idx: int,
    stage_form_offset: float,
    streak_offset: float,
    rng: random.Random,
) -> int:
    # Score model tuned for avg floor/ceiling target.
    # Base mean approximately 160..230 across power 1..10.
    base = 145 + (power * 6.7)
    # Consistency controls variance: low consistency => bigger spread.
    sigma = 4 + (1.0 - consistency) * 20

    # Momentum effect: occasional game-level streak/slump bursts.
    roll = rng.random()
    momentum = 0
    if roll < 0.12:
        momentum = rng.randint(4, 9)   # streak
    elif roll > 0.88:
        momentum = -rng.randint(4, 9)  # slump

    # Mild progression trend by game/stage + persistent stage/player form.
    trend = game_idx * 0.7 + stage_idx * 0.5

    raw = rng.gauss(base + trend + momentum + stage_form_offset + streak_offset, sigma)
    return int(max(120, min(259, round(raw))))


def write_csv(path: Path, headers: List[str], rows: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def format_season_label(start_year: int) -> str:
    """Convert 2024 -> '24/25' style season label."""
    return f"{start_year % 100:02d}/{(start_year + 1) % 100:02d}"


def simulate_tournament(
    roster: List[Dict[str, Any]],
    seasons: List[int],
    event_name: str,
    venue: str,
    rng: random.Random,
) -> Dict[str, List[Dict[str, object]]]:
    clean_rows: List[Dict[str, object]] = []
    post_rows: List[Dict[str, object]] = []
    for season in seasons:
        active = roster[:]
        cumulative_overall: Dict[str, int] = {str(p["player_id"]): 0 for p in roster}

        for stage_idx, stage in enumerate(STAGES):
            stage_rows: List[Dict[str, object]] = []
            for p in active:
                # Round-to-round form variance scales with inconsistency:
                # low consistency => potentially large stage offset, high consistency => smaller.
                consistency = float(p["consistency"])
                form_sigma = 1.5 + (1.0 - consistency) * 7.0
                stage_form_offset = rng.gauss(0, form_sigma)
                # Persistent hot/cold streak for this player in this stage.
                streak_roll = rng.random()
                if streak_roll < 0.22:
                    streak_offset = rng.randint(3, 7)
                elif streak_roll > 0.78:
                    streak_offset = -rng.randint(3, 7)
                else:
                    streak_offset = 0
                for g in range(stage.games):
                    score = score_game(
                        int(p["power"]),
                        consistency,
                        g,
                        stage_idx,
                        stage_form_offset,
                        streak_offset,
                        rng,
                    )
                    row = {
                        "Season": format_season_label(season),
                        "Date": stage.date.format(season=season),
                        "Location": venue,
                        "Event Type": "tournament",
                        "Event Name": event_name,
                        "Round Number": stage.number,
                        "Round Name": stage.name,
                        "Player": p["player"],
                        "Player ID": p["player_id"],
                        "Club": p["club"],
                        "Game Number": g,
                        "Score": score,
                        "Handicap": 0,
                    }
                    stage_rows.append(row)
                    clean_rows.append(row)

            # Stage-postprocessing snapshots by game
            stage_running: Dict[str, int] = {str(p["player_id"]): 0 for p in active}
            for g in range(stage.games):
                g_rows = [r for r in stage_rows if r["Game Number"] == g]
                for r in g_rows:
                    pid = str(r["Player ID"])
                    s = int(r["Score"])
                    stage_running[pid] += s
                    cumulative_overall[pid] = cumulative_overall.get(pid, 0) + s

                ranked_stage = sorted(active, key=lambda p: (-stage_running[str(p["player_id"])], p["player"]))
                rank_map = {str(p["player_id"]): i + 1 for i, p in enumerate(ranked_stage)}
                cut_line = ""
                if stage.cut_to is not None and ranked_stage:
                    cut_line = stage_running[str(ranked_stage[stage.cut_to - 1]["player_id"])]

                for r in g_rows:
                    pid = str(r["Player ID"])
                    rr = dict(r)
                    rr["Cumulative Score"] = stage_running[pid]
                    rr["Stage Rank"] = rank_map[pid]
                    rr["Cut Line"] = cut_line
                    rr["Overall Cumulative Score"] = cumulative_overall[pid]
                    post_rows.append(rr)

            # Apply stage cut by cumulative tournament totals up to this point (scratch).
            if stage.cut_to is not None:
                active = sorted(
                    active,
                    key=lambda p: (-cumulative_overall[str(p["player_id"])], p["player"]),
                )[: stage.cut_to]

    return {"clean_rows": clean_rows, "post_rows": post_rows}


def _latest_totals_from_post_rows(post_rows: List[Dict[str, object]], season_label: str) -> Dict[str, int]:
    season_rows = [r for r in post_rows if str(r.get("Season", "")) == season_label]
    if not season_rows:
        return {}
    max_round = max(int(r.get("Round Number", 0)) for r in season_rows)
    round_rows = [r for r in season_rows if int(r.get("Round Number", 0)) == max_round]
    max_game = max(int(r.get("Game Number", 0)) for r in round_rows) if round_rows else -1
    snap = [r for r in round_rows if int(r.get("Game Number", -1)) == max_game]
    out: Dict[str, int] = {}
    for r in snap:
        pid = str(r.get("Player ID", ""))
        if pid:
            out[pid] = int(r.get("Overall Cumulative Score", 0))
    return out


def _top_n_players_by_season(post_rows: List[Dict[str, object]], season_label: str, n: int) -> List[str]:
    totals = _latest_totals_from_post_rows(post_rows, season_label)
    ranked = sorted(totals.items(), key=lambda t: (-t[1], t[0]))
    return [pid for pid, _ in ranked[:n]]


def simulate_clash_tournament(
    all_players_by_id: Dict[str, Dict[str, Any]],
    geek_post_rows: List[Dict[str, object]],
    myth_post_rows: List[Dict[str, object]],
    seasons: List[int],
    rng: random.Random,
) -> Dict[str, List[Dict[str, object]]]:
    clean_rows: List[Dict[str, object]] = []
    post_rows: List[Dict[str, object]] = []
    event_name = "Clash of Imaginary Entities"
    venue = "Arena of Echoes"

    for season in seasons:
        season_label = format_season_label(season)
        geek_top = _top_n_players_by_season(geek_post_rows, season_label, 20)
        myth_top = _top_n_players_by_season(myth_post_rows, season_label, 20)
        participant_ids = geek_top + myth_top
        participants = [dict(all_players_by_id[pid]) for pid in participant_ids if pid in all_players_by_id]
        if not participants:
            continue

        active = participants[:]
        cumulative_overall: Dict[str, int] = {str(p["player_id"]): 0 for p in participants}

        for stage_idx, stage in enumerate(CLASH_STAGES):
            stage_rows: List[Dict[str, object]] = []

            if stage.number < 4:
                stage_players = active[:]
                stage_running: Dict[str, int] = {str(p["player_id"]): 0 for p in stage_players}
                for p in stage_players:
                    consistency = float(p["consistency"])
                    form_sigma = 1.5 + (1.0 - consistency) * 7.0
                    stage_form_offset = rng.gauss(0, form_sigma)
                    streak_roll = rng.random()
                    if streak_roll < 0.22:
                        streak_offset = rng.randint(3, 7)
                    elif streak_roll > 0.78:
                        streak_offset = -rng.randint(3, 7)
                    else:
                        streak_offset = 0
                    for g in range(stage.games):
                        score = score_game(
                            int(p["power"]),
                            consistency,
                            g,
                            stage_idx,
                            stage_form_offset,
                            streak_offset,
                            rng,
                        )
                        row = {
                            "Season": season_label,
                            "Date": stage.date.format(season=season),
                            "Location": venue,
                            "Event Type": "tournament",
                            "Event Name": event_name,
                            "Round Number": stage.number,
                            "Round Name": stage.name,
                            "Player": p["player"],
                            "Player ID": p["player_id"],
                            "Club": p["club"],
                            "Game Number": g,
                            "Score": score,
                            "Handicap": 0,
                        }
                        stage_rows.append(row)
                        clean_rows.append(row)

                for g in range(stage.games):
                    g_rows = [r for r in stage_rows if int(r["Game Number"]) == g]
                    for r in g_rows:
                        pid = str(r["Player ID"])
                        s = int(r["Score"])
                        stage_running[pid] += s
                        cumulative_overall[pid] = cumulative_overall.get(pid, 0) + s

                    ranked_stage = sorted(stage_players, key=lambda p: (-stage_running[str(p["player_id"])], p["player"]))
                    rank_map = {str(p["player_id"]): i + 1 for i, p in enumerate(ranked_stage)}
                    cut_line = ""
                    if stage.cut_to is not None and len(stage_players) >= stage.cut_to:
                        ranked_cum = sorted(stage_players, key=lambda p: (-cumulative_overall[str(p["player_id"])], p["player"]))
                        cut_line = cumulative_overall[str(ranked_cum[stage.cut_to - 1]["player_id"])]

                    for r in g_rows:
                        pid = str(r["Player ID"])
                        rr = dict(r)
                        rr["Cumulative Score"] = stage_running[pid]
                        rr["Stage Rank"] = rank_map[pid]
                        rr["Cut Line"] = cut_line
                        rr["Overall Cumulative Score"] = cumulative_overall[pid]
                        post_rows.append(rr)

                if stage.cut_to is not None:
                    active = sorted(
                        stage_players,
                        key=lambda p: (-cumulative_overall[str(p["player_id"])], p["player"]),
                    )[: stage.cut_to]
                else:
                    active = stage_players
            else:
                finalists = active[:]
                elimination_active = finalists[:]
                stage_running: Dict[str, int] = {str(p["player_id"]): 0 for p in finalists}
                survival_games: Dict[str, int] = {str(p["player_id"]): 0 for p in finalists}

                for g in range(stage.games):
                    if not elimination_active:
                        break
                    g_rows: List[Dict[str, object]] = []
                    for p in elimination_active:
                        consistency = float(p["consistency"])
                        score = score_game(
                            int(p["power"]),
                            consistency,
                            g,
                            stage_idx,
                            rng.gauss(0, 1.5 + (1.0 - consistency) * 7.0),
                            rng.randint(-4, 4),
                            rng,
                        )
                        row = {
                            "Season": season_label,
                            "Date": stage.date.format(season=season),
                            "Location": venue,
                            "Event Type": "tournament",
                            "Event Name": event_name,
                            "Round Number": stage.number,
                            "Round Name": stage.name,
                            "Player": p["player"],
                            "Player ID": p["player_id"],
                            "Club": p["club"],
                            "Game Number": g,
                            "Score": score,
                            "Handicap": 0,
                        }
                        g_rows.append(row)
                        clean_rows.append(row)
                        pid = str(p["player_id"])
                        stage_running[pid] += score
                        cumulative_overall[pid] += score
                        survival_games[pid] += 1

                    # Eliminate lowest single-game score after each game (until one remains).
                    if len(elimination_active) > 1:
                        score_by_pid = {str(r["Player ID"]): int(r["Score"]) for r in g_rows}
                        elimination_active = sorted(
                            elimination_active,
                            key=lambda p: (
                                -score_by_pid[str(p["player_id"])],
                                -cumulative_overall[str(p["player_id"])],
                                p["player"],
                            ),
                        )
                        elimination_active = elimination_active[:-1]

                    ranked_final = sorted(
                        finalists,
                        key=lambda p: (
                            -survival_games[str(p["player_id"])],
                            -stage_running[str(p["player_id"])],
                            p["player"],
                        ),
                    )
                    rank_map = {str(p["player_id"]): i + 1 for i, p in enumerate(ranked_final)}

                    for r in g_rows:
                        pid = str(r["Player ID"])
                        rr = dict(r)
                        rr["Cumulative Score"] = stage_running[pid]
                        rr["Stage Rank"] = rank_map[pid]
                        rr["Cut Line"] = ""
                        rr["Overall Cumulative Score"] = cumulative_overall[pid]
                        post_rows.append(rr)

                active = finalists

    return {"clean_rows": clean_rows, "post_rows": post_rows}


def main() -> None:
    rng = random.Random(42)
    seasons = [2024, 2025, 2026]

    clean_headers = [
        "Season", "Date", "Location", "Event Type", "Event Name", "Round Number", "Round Name",
        "Player", "Player ID", "Club", "Game Number", "Score", "Handicap",
    ]
    post_headers = clean_headers + ["Cumulative Score", "Stage Rank", "Cut Line", "Overall Cumulative Score"]
    roster_headers = ["Player", "Player ID", "Franchise", "Club", "Power", "Consistency"]

    geek_roster = assign_attributes(build_geek_roster(), rng, id_min=50000, id_max=99999)
    geek_results = simulate_tournament(
        roster=geek_roster,
        seasons=seasons,
        event_name="Geek Masters Invitational",
        venue="The Nexus Bowl",
        rng=rng,
    )
    geek_roster_rows = [
        {
            "Player": p["player"],
            "Player ID": p["player_id"],
            "Franchise": p["franchise"],
            "Club": p["club"],
            "Power": p["power"],
            "Consistency": p["consistency"],
        }
        for p in geek_roster
    ]
    write_csv(GEEK_CLEAN_OUT, clean_headers, geek_results["clean_rows"])
    write_csv(GEEK_POST_OUT, post_headers, geek_results["post_rows"])
    write_csv(GEEK_ROSTER_OUT, roster_headers, geek_roster_rows)

    myth_roster = assign_attributes(build_mythology_roster(), rng, id_min=100000, id_max=199999)
    myth_results = simulate_tournament(
        roster=myth_roster,
        seasons=seasons,
        event_name="Mythic Legends Invitational",
        venue="Pantheon Lanes",
        rng=rng,
    )
    myth_roster_rows = [
        {
            "Player": p["player"],
            "Player ID": p["player_id"],
            "Franchise": p["franchise"],
            "Club": p["club"],
            "Power": p["power"],
            "Consistency": p["consistency"],
        }
        for p in myth_roster
    ]
    write_csv(MYTH_CLEAN_OUT, clean_headers, myth_results["clean_rows"])
    write_csv(MYTH_POST_OUT, post_headers, myth_results["post_rows"])
    write_csv(MYTH_ROSTER_OUT, roster_headers, myth_roster_rows)

    all_players_by_id: Dict[str, Dict[str, Any]] = {
        str(p["player_id"]): p for p in (geek_roster + myth_roster)
    }
    clash_results = simulate_clash_tournament(
        all_players_by_id=all_players_by_id,
        geek_post_rows=geek_results["post_rows"],
        myth_post_rows=myth_results["post_rows"],
        seasons=seasons,
        rng=rng,
    )
    write_csv(CLASH_CLEAN_OUT, clean_headers, clash_results["clean_rows"])
    write_csv(CLASH_POST_OUT, post_headers, clash_results["post_rows"])

    combined_post_rows = (
        geek_results["post_rows"] + myth_results["post_rows"] + clash_results["post_rows"]
    )
    combined_post_rows = sorted(
        combined_post_rows,
        key=lambda r: (
            str(r.get("Season", "")),
            str(r.get("Event Name", "")),
            int(r.get("Round Number", 0)),
            int(r.get("Game Number", 0)),
            str(r.get("Player", "")),
        ),
    )
    write_csv(COMBINED_POST_OUT, post_headers, combined_post_rows)

    print(f"Wrote clean: {GEEK_CLEAN_OUT.name} ({len(geek_results['clean_rows'])} rows)")
    print(f"Wrote postprocessed: {GEEK_POST_OUT.name} ({len(geek_results['post_rows'])} rows)")
    print(f"Wrote roster: {GEEK_ROSTER_OUT.name} ({len(geek_roster_rows)} players)")
    print(f"Wrote clean: {MYTH_CLEAN_OUT.name} ({len(myth_results['clean_rows'])} rows)")
    print(f"Wrote postprocessed: {MYTH_POST_OUT.name} ({len(myth_results['post_rows'])} rows)")
    print(f"Wrote roster: {MYTH_ROSTER_OUT.name} ({len(myth_roster_rows)} players)")
    print(f"Wrote clean: {CLASH_CLEAN_OUT.name} ({len(clash_results['clean_rows'])} rows)")
    print(f"Wrote postprocessed: {CLASH_POST_OUT.name} ({len(clash_results['post_rows'])} rows)")
    print(f"Wrote postprocessed: {COMBINED_POST_OUT.name} ({len(combined_post_rows)} rows)")
    print("Cuts applied for all seasons: Qualifying -> top 40, Round 2 -> top 20, Final winner by scratch total.")


if __name__ == "__main__":
    main()

