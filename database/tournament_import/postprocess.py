"""Cumulative score / rank enrichment for tournament postprocessed rows."""



from __future__ import annotations



from collections import defaultdict

from typing import Dict, List, Optional



from app.utils.tournament_stage_config import (

    list_tournament_stage_items,

    stage_cut_basis_for_round,

    stage_cut_rank_for_round,

)





def _player_key(row: Dict[str, str]) -> str:

    pid = str(row.get("Player ID") or "").strip()

    if pid:

        return pid

    return str(row.get("Player") or "").strip()





def _cut_map_for_event(season: str, event_name: str) -> Dict[int, tuple[int, str]]:

    """round_number -> (cut_rank, cut_basis)"""

    out: Dict[int, tuple[int, str]] = {}

    for item in list_tournament_stage_items(season, event_name):

        try:

            rn = int(item["id"])

        except (TypeError, ValueError, KeyError):

            continue

        cut_rank = stage_cut_rank_for_round(season, event_name, rn)

        if cut_rank is None:

            continue

        basis = stage_cut_basis_for_round(season, event_name, rn)

        out[rn] = (cut_rank, basis)

    return out





def postprocess_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:

    by_event: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    for row in rows:

        by_event[row["Event Name"]].append(row)



    out: List[Dict[str, str]] = []

    for _, event_rows in sorted(by_event.items()):

        season = str(event_rows[0].get("Season") or "").strip()

        event_name = str(event_rows[0].get("Event Name") or "").strip()

        cut_map = _cut_map_for_event(season, event_name)



        by_round: Dict[int, List[Dict[str, str]]] = defaultdict(list)

        for row in event_rows:

            by_round[int(row["Round Number"])].append(row)



        overall_running: Dict[str, int] = defaultdict(int)

        for round_number in sorted(by_round.keys()):

            round_rows = by_round[round_number]

            by_game: Dict[int, List[Dict[str, str]]] = defaultdict(list)

            for row in round_rows:

                by_game[int(row["Game Number"])].append(row)



            stage_running: Dict[str, int] = defaultdict(int)

            player_name_by_id: Dict[str, str] = {}

            for row in round_rows:

                player_name_by_id[_player_key(row)] = str(row.get("Player") or "")



            cut_players, cut_basis = cut_map.get(round_number, (0, ""))



            for game_number in sorted(by_game.keys()):

                game_rows = sorted(by_game[game_number], key=lambda r: (r["Player"], r["Player ID"]))

                for row in game_rows:

                    pid = _player_key(row)

                    score = int(row["Score"])

                    stage_running[pid] += score

                    overall_running[pid] += score



                ranking_source = overall_running if cut_basis != "stage_total" else stage_running

                ranked_pids = sorted(

                    ranking_source.keys(),

                    key=lambda pid: (-ranking_source[pid], player_name_by_id.get(pid, "")),

                )

                rank_by_pid = {pid: idx + 1 for idx, pid in enumerate(ranked_pids)}



                cut_line = ""

                if cut_players > 0 and ranked_pids:

                    cut_idx = min(cut_players, len(ranked_pids)) - 1

                    cut_line = str(ranking_source[ranked_pids[cut_idx]])



                for row in game_rows:

                    pid = _player_key(row)

                    out_row = dict(row)

                    out_row["Cumulative Score"] = str(stage_running[pid])

                    out_row["Stage Rank"] = str(rank_by_pid[pid])

                    out_row["Cut Line"] = cut_line

                    out_row["Cut Basis"] = cut_basis

                    out_row["Overall Cumulative Score"] = str(overall_running[pid])

                    out.append(out_row)

    return out

