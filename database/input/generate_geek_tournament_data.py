"""
Generate a synthetic "Geek Tournament" dataset.

Outputs:
1) clean per-game CSV
2) postprocessed CSV with stage cumulative/rank/cut line
3) roster metadata CSV (franchise/faction/power/consistency)
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "database" / "data"

CLEAN_OUT = DATA_DIR / "tournament_geek_classic_2026_clean.csv"
POST_OUT = DATA_DIR / "tournament_geek_classic_2026_postprocessed.csv"
ROSTER_OUT = DATA_DIR / "tournament_geek_classic_2026_roster.csv"


@dataclass(frozen=True)
class Stage:
    number: int
    name: str
    date: str
    games: int
    cut_to: int | None


STAGES: List[Stage] = [
    Stage(1, "Qualifying", "2026-09-18", 8, 40),
    Stage(2, "Round 2", "2026-09-19", 6, 20),
    Stage(3, "Final", "2026-09-20", 6, None),
]


def build_franchise_roster() -> List[Dict[str, str]]:
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


def assign_attributes(roster: List[Dict[str, str]], rng: random.Random) -> List[Dict[str, str]]:
    # Power by role-ish ordering + some variety, consistency random [0..1]
    # Random player IDs in a safe range, unique.
    ids = rng.sample(range(50000, 99999), len(roster))
    out: List[Dict[str, str]] = []
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


def main() -> None:
    rng = random.Random(42)
    event_name = "Geek Masters Invitational"
    venue = "The Nexus Bowl"
    season = "2026"

    roster = assign_attributes(build_franchise_roster(), rng)

    clean_rows: List[Dict[str, object]] = []
    post_rows: List[Dict[str, object]] = []
    active = roster[:]
    cumulative_overall: Dict[str, int] = {p["player_id"]: 0 for p in roster}

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
                    "Season": season,
                    "Date": stage.date,
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
        stage_running: Dict[str, int] = {p["player_id"]: 0 for p in active}
        for g in range(stage.games):
            g_rows = [r for r in stage_rows if r["Game Number"] == g]
            for r in g_rows:
                pid = str(r["Player ID"])
                s = int(r["Score"])
                stage_running[pid] += s
                cumulative_overall[pid] = cumulative_overall.get(pid, 0) + s

            ranked_stage = sorted(active, key=lambda p: (-stage_running[p["player_id"]], p["player"]))
            rank_map = {p["player_id"]: i + 1 for i, p in enumerate(ranked_stage)}
            cut_line = ""
            if stage.cut_to is not None and ranked_stage:
                cut_line = stage_running[ranked_stage[stage.cut_to - 1]["player_id"]]

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
            active = sorted(active, key=lambda p: (-cumulative_overall[p["player_id"]], p["player"]))[: stage.cut_to]

    clean_headers = [
        "Season", "Date", "Location", "Event Type", "Event Name", "Round Number", "Round Name",
        "Player", "Player ID", "Club", "Game Number", "Score", "Handicap",
    ]
    post_headers = clean_headers + ["Cumulative Score", "Stage Rank", "Cut Line", "Overall Cumulative Score"]
    roster_headers = ["Player", "Player ID", "Franchise", "Club", "Power", "Consistency"]

    roster_rows = [
        {
            "Player": p["player"],
            "Player ID": p["player_id"],
            "Franchise": p["franchise"],
            "Club": p["club"],
            "Power": p["power"],
            "Consistency": p["consistency"],
        }
        for p in roster
    ]

    write_csv(CLEAN_OUT, clean_headers, clean_rows)
    write_csv(POST_OUT, post_headers, post_rows)
    write_csv(ROSTER_OUT, roster_headers, roster_rows)

    print(f"Wrote clean: {CLEAN_OUT.name} ({len(clean_rows)} rows)")
    print(f"Wrote postprocessed: {POST_OUT.name} ({len(post_rows)} rows)")
    print(f"Wrote roster: {ROSTER_OUT.name} ({len(roster_rows)} players)")
    print("Cuts applied: Qualifying -> top 40, Round 2 -> top 20, Final winner by scratch total.")


if __name__ == "__main__":
    main()

