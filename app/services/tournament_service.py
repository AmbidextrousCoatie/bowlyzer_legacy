from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.table_data import Column, TableData
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns


class TournamentService:
    def __init__(self, adapter_type=DataAdapterSelector.PANDAS, database: str = None):
        self.database = database
        self.adapter = DataAdapterFactory.create_adapter(adapter_type, database=database)

    def _get_tournament_df(self, season: Optional[str] = None, tournament: Optional[str] = None) -> pd.DataFrame:
        """
        Load data and apply robust string-based filters.
        This avoids dtype mismatches (e.g., Season 2026 as int in CSV vs "2026" in query).
        """
        df = self.adapter.get_filtered_data(filters={})
        if df.empty:
            return df

        # Event type filter is mandatory for this service.
        if Columns.event_type in df.columns:
            event_type_series = df[Columns.event_type].astype(str).str.strip().str.lower()
            df = df[event_type_series.eq("tournament")]
        else:
            return df.iloc[0:0].copy()

        if season and Columns.season in df.columns:
            season_norm = str(season).strip()
            df = df[df[Columns.season].astype(str).str.strip().eq(season_norm)]

        if tournament and Columns.event_name in df.columns:
            tournament_norm = str(tournament).strip()
            df = df[df[Columns.event_name].astype(str).str.strip().eq(tournament_norm)]

        return df

    def get_tournaments(self, season: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=None)
        if df.empty or Columns.event_name not in df.columns:
            return []
        return sorted([x for x in df[Columns.event_name].dropna().astype(str).unique().tolist() if x.strip()])

    def get_players(self, season: str, tournament: str) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty or Columns.player_name not in df.columns:
            return []
        return sorted([x for x in df[Columns.player_name].dropna().astype(str).unique().tolist() if x.strip()])

    def get_rounds(self, season: str, tournament: str) -> List[Dict[str, Any]]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return []
        pairs = (
            df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .copy()
        )
        pairs[Columns.round_number] = pd.to_numeric(pairs[Columns.round_number], errors="coerce").astype("Int64")
        pairs = pairs.dropna(subset=[Columns.round_number]).sort_values(by=Columns.round_number)
        out = []
        for _, row in pairs.iterrows():
            out.append(
                {
                    "round_number": int(row[Columns.round_number]),
                    "round_name": str(row.get(Columns.round_name, "") or "").strip(),
                }
            )
        return out

    def _scope_df(self, df: pd.DataFrame, round_number: Optional[int]) -> pd.DataFrame:
        if round_number is None:
            return df.copy()
        return df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(round_number))].copy()

    def _top_n_games(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        game_df = scope_df.copy()
        game_df[Columns.score] = pd.to_numeric(game_df[Columns.score], errors="coerce")
        game_df = game_df.dropna(subset=[Columns.score]).sort_values(by=Columns.score, ascending=False).head(n)
        out: List[Dict[str, Any]] = []
        for _, row in game_df.iterrows():
            g = int(pd.to_numeric(row.get(Columns.game_number), errors="coerce")) + 1
            out.append(
                {
                    "player": str(row.get(Columns.player_name, "")),
                    "club": str(row.get(Columns.club, "")),
                    "stage": str(row.get(Columns.round_name, "")),
                    "label": f"G{g}",
                    "value": int(row[Columns.score]),
                    "display_value": f"{int(row[Columns.score])}",
                }
            )
        return out

    def _top_n_pairs(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        pair_rows: List[Dict[str, Any]] = []
        work = scope_df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")
        grouped = work.groupby([Columns.round_name, Columns.player_name, Columns.club], dropna=False)
        for (round_name, player_name, club), gdf in grouped:
            scores = {int(r[Columns.game_number]): int(r[Columns.score]) for _, r in gdf.iterrows() if pd.notna(r[Columns.game_number])}
            one_based_games = sorted([x + 1 for x in scores.keys()])
            for start in one_based_games:
                if start % 2 == 1 and (start + 1) in one_based_games:
                    pair_rows.append(
                        {
                            "player": str(player_name),
                            "club": str(club),
                            "stage": str(round_name or ""),
                            "label": f"G{start}+G{start+1}",
                            "value": int(scores[start - 1] + scores[start]),
                            "display_value": f"{int(scores[start - 1] + scores[start])}",
                        }
                    )
        if not pair_rows:
            return []
        return (
            pd.DataFrame(pair_rows)
            .sort_values(by="value", ascending=False)
            .head(n)
            .to_dict(orient="records")
        )

    def _top_n_blocks(self, scope_df: pd.DataFrame, n: int) -> List[Dict[str, Any]]:
        if scope_df.empty:
            return []
        work = scope_df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        block_df = (
            work.groupby([Columns.round_name, Columns.player_name, Columns.club], dropna=False)[Columns.score]
            .agg(["sum", "count"])
            .reset_index()
            .rename(columns={"sum": "value", "count": "games"})
            .sort_values(by="value", ascending=False)
            .head(n)
        )
        out: List[Dict[str, Any]] = []
        for _, r in block_df.iterrows():
            avg = float(r["value"]) / max(int(r["games"]), 1)
            out.append(
                {
                    "player": str(r[Columns.player_name]),
                    "club": str(r.get(Columns.club, "")),
                    "stage": str(r[Columns.round_name]),
                    "label": "Block",
                    "value": int(r["value"]),
                    "display_value": f"{int(r['value'])} (\u2300{avg:.1f})",
                }
            )
        return out

    def _build_best_efforts_scope_payload(self, scope_df: pd.DataFrame, stage_label: str, n: int) -> Dict[str, Any]:
        return {
            "scope": stage_label,
            "best_games": self._top_n_games(scope_df, n),
            "best_pairs": self._top_n_pairs(scope_df, n),
            "best_blocks": self._top_n_blocks(scope_df, n),
        }

    def get_best_efforts(self, season: str, tournament: str, round_number: Optional[int] = None, top_n: int = 5) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"n": top_n, "sections": []}

        if round_number is not None:
            scope_df = self._scope_df(df, round_number)
            stage_name = (
                str(scope_df[Columns.round_name].dropna().iloc[0])
                if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                else f"Round {round_number}"
            )
            return {"n": top_n, "sections": [self._build_best_efforts_scope_payload(scope_df, stage_name, top_n)]}

        sections: List[Dict[str, Any]] = []
        round_rows = (
            df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        for _, rr in round_rows.iterrows():
            rn = int(pd.to_numeric(rr[Columns.round_number], errors="coerce"))
            stage_name = str(rr.get(Columns.round_name, "") or f"Round {rn}")
            stage_df = self._scope_df(df, rn)
            sections.append(self._build_best_efforts_scope_payload(stage_df, stage_name, top_n))

        sections.append(self._build_best_efforts_scope_payload(df, "Overall", top_n))
        return {"n": top_n, "sections": sections}

    def get_summary_cards(self, season: str, tournament: str, round_number: Optional[int] = None, top_n: int = 5) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"cards": []}
        scope_df = self._scope_df(df, round_number)
        if scope_df.empty:
            return {"cards": []}

        participants = int(scope_df[Columns.player_id].nunique()) if Columns.player_id in scope_df.columns else 0
        rounds = self.get_rounds(season, tournament) if round_number is None else [
            {"round_number": round_number, "round_name": str(scope_df[Columns.round_name].dropna().iloc[0]) if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty else f"Round {round_number}"}
        ]
        latest_round = rounds[-1] if rounds else {"round_number": None, "round_name": ""}

        # Stage winner is specific to selected stage (or latest stage when none selected).
        stage_round_number = round_number if round_number is not None else latest_round.get("round_number")

        # Tournament leader should reflect cumulative totals up to the selected stage.
        # If no stage is selected, use the latest available stage as the cutoff.
        tournament_leader = None
        if stage_round_number is not None:
            cumulative_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(stage_round_number))].copy()
            if not cumulative_df.empty:
                cumulative_df[Columns.score] = pd.to_numeric(cumulative_df[Columns.score], errors="coerce").fillna(0)
                tournament_totals = (
                    cumulative_df.groupby([Columns.player_name], dropna=False)[Columns.score]
                    .sum()
                    .reset_index(name="total_score")
                    .sort_values(by=["total_score", Columns.player_name], ascending=[False, True])
                    .reset_index(drop=True)
                )
                if not tournament_totals.empty:
                    tournament_leader = tournament_totals.iloc[0]

        # Stage winner remains stage-specific for the selected/latest stage.
        stage_leaderboard = self._build_leaderboard_df(df, stage_round_number) if stage_round_number is not None else pd.DataFrame()
        stage_winner = stage_leaderboard.iloc[0] if not stage_leaderboard.empty else None

        cards = [
            {"title": "Tournament", "value": tournament, "subtitle": season, "type": "stat"},
            {
                "title": "Participants",
                "value": participants,
                "subtitle": "Field size",
                "type": "stat",
            },
            {
                "title": "Current Round",
                "value": latest_round.get("round_name") or f"Round {latest_round.get('round_number')}",
                "subtitle": f"#{latest_round.get('round_number')}" if latest_round.get("round_number") else "",
                "type": "stat",
            },
        ]
        if Columns.cut_line in scope_df.columns and latest_round.get("round_number") is not None:
            latest_round_df = scope_df[pd.to_numeric(scope_df[Columns.round_number], errors="coerce").eq(float(latest_round["round_number"]))].copy()
            if not latest_round_df.empty:
                max_game = pd.to_numeric(latest_round_df[Columns.game_number], errors="coerce").max()
                latest_snap = latest_round_df[pd.to_numeric(latest_round_df[Columns.game_number], errors="coerce").eq(max_game)]
                cut_vals = pd.to_numeric(latest_snap[Columns.cut_line], errors="coerce").dropna()
                if not cut_vals.empty:
                    cards.append(
                        {
                            "title": "Cut Line",
                            "value": int(cut_vals.iloc[0]),
                            "subtitle": "Current threshold",
                            "type": "stat",
                        }
                    )
        if tournament_leader is not None:
            cards.append(
                {
                    "title": "Tournament Leader",
                    "value": tournament_leader[Columns.player_name],
                    "subtitle": f"{int(tournament_leader['total_score'])} pins",
                    "type": "stat",
                }
            )
        if stage_winner is not None and stage_round_number is not None:
            stage_name = (
                latest_round.get("round_name")
                if round_number is None
                else str(scope_df[Columns.round_name].dropna().iloc[0]) if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                else f"Round {stage_round_number}"
            )
            cards.append(
                {
                    "title": "Stage Winner",
                    "value": stage_winner["player"],
                    "subtitle": f"{stage_name}: {int(stage_winner['total_score'])} pins",
                    "type": "stat",
                }
            )
        return {"cards": cards}

    def _build_leaderboard_df(self, df: pd.DataFrame, round_number: Optional[int] = None) -> pd.DataFrame:
        work = df.copy()
        if round_number is not None:
            work = work[pd.to_numeric(work[Columns.round_number], errors="coerce").eq(float(round_number))]
        if work.empty:
            return pd.DataFrame()

        # If postprocessed data exists, use the last game snapshot per player.
        if Columns.cumulative_score in work.columns and Columns.stage_rank in work.columns:
            game_vals = pd.to_numeric(work[Columns.game_number], errors="coerce")
            max_game = game_vals.max()
            snap = work[game_vals.eq(max_game)].copy()
            snap["rank"] = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
            snap["total_score"] = pd.to_numeric(snap[Columns.cumulative_score], errors="coerce")
            snap["player"] = snap[Columns.player_name].astype(str)
            snap["player_id"] = snap[Columns.player_id].astype(str)
            snap["club"] = snap.get(Columns.club, "").astype(str)
            out = snap[["rank", "player", "player_id", "club", "total_score"]].dropna(subset=["total_score"])
            return out.sort_values(by=["rank", "player"]).reset_index(drop=True)

        grouped = (
            work.groupby([Columns.player_name, Columns.player_id, Columns.club], dropna=False)[Columns.score]
            .sum()
            .reset_index()
            .rename(
                columns={
                    Columns.player_name: "player",
                    Columns.player_id: "player_id",
                    Columns.club: "club",
                    Columns.score: "total_score",
                }
            )
        )
        grouped["rank"] = grouped["total_score"].rank(method="min", ascending=False).astype(int)
        return grouped.sort_values(by=["rank", "player"]).reset_index(drop=True)

    def get_leaderboard_table(self, season: str, tournament: str, round_number: Optional[int] = None) -> TableData:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Leaderboard")

        # Single-stage mode: keep stage-specific leaderboard behavior.
        if round_number is not None:
            leaderboard = self._build_leaderboard_df(df, round_number)
            games_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(round_number))].copy()
            games_per_player = (
                games_df.groupby([Columns.player_name], dropna=False).size().to_dict()
                if not games_df.empty and "player" in leaderboard.columns and Columns.player_name in games_df.columns
                else {}
            )
            if not leaderboard.empty:
                leaderboard["avg_score"] = leaderboard.apply(
                    lambda r: round(float(r["total_score"]) / max(int(games_per_player.get(r["player"], 1)), 1), 1),
                    axis=1,
                )
            columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0),
                Column(title="Player", field="player", width="220px", align="left"),
                Column(title="Club", field="club", width="220px", align="left"),
                Column(title="Total", field="total_score", width="90px", align="center", decimal_places=0),
                Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1),
            ]
            data = leaderboard[["rank", "player", "club", "total_score", "avg_score"]].values.tolist() if not leaderboard.empty else []
            return TableData(columns=columns, data=data, title=f"{tournament} Leaderboard")

        # Multi-stage mode: total = sum across all rounds, plus one column per round.
        work = df.copy()
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")

        id_col = Columns.player_id if Columns.player_id in work.columns else "__player_id_missing__"
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)

        round_meta = (
            work[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        round_numbers = [int(x) for x in round_meta[Columns.round_number].tolist()]
        round_name_map = {
            int(row[Columns.round_number]): str(row.get(Columns.round_name, "") or f"Round {int(row[Columns.round_number])}")
            for _, row in round_meta.iterrows()
        }

        grouped = (
            work.groupby([Columns.player_name, id_col, Columns.club, Columns.round_number], dropna=False)[Columns.score]
            .sum()
            .reset_index(name="round_total")
        )
        pivot = grouped.pivot_table(
            index=[Columns.player_name, id_col, Columns.club],
            columns=Columns.round_number,
            values="round_total",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        for rn in round_numbers:
            if rn not in pivot.columns:
                pivot[rn] = 0

        pivot["total_score"] = pivot[round_numbers].sum(axis=1) if round_numbers else 0
        games_per_player_all = work.groupby([Columns.player_name, id_col], dropna=False).size().reset_index(name="games_played")
        pivot = pivot.merge(games_per_player_all, on=[Columns.player_name, id_col], how="left")
        pivot["games_played"] = pd.to_numeric(pivot["games_played"], errors="coerce").fillna(1)
        pivot["avg_score"] = (pivot["total_score"] / pivot["games_played"]).round(1)
        pivot = pivot.sort_values(by=["total_score", Columns.player_name], ascending=[False, True]).reset_index(drop=True)
        pivot["rank"] = pivot["total_score"].rank(method="min", ascending=False).astype(int)

        columns = [
            Column(title="#", field="rank", width="60px", align="center", decimal_places=0),
            Column(title="Player", field="player", width="220px", align="left"),
            Column(title="Club", field="club", width="220px", align="left"),
        ]
        for rn in round_numbers:
            title = round_name_map.get(rn) or f"Round {rn}"
            columns.append(Column(title=title, field=f"round_{rn}", width="110px", align="center", decimal_places=0))
        columns.append(Column(title="Total", field="total_score", width="100px", align="center", decimal_places=0))
        columns.append(Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1))

        data = []
        for _, row in pivot.iterrows():
            entry = [
                int(row["rank"]),
                str(row.get(Columns.player_name, "")),
                str(row.get(Columns.club, "")),
            ]
            for rn in round_numbers:
                entry.append(int(row.get(rn, 0)))
            entry.append(int(row.get("total_score", 0)))
            entry.append(float(row.get("avg_score", 0.0)))
            data.append(entry)

        return TableData(columns=columns, data=data, title=f"{tournament} Leaderboard")

    def get_round_results_table(self, season: str, tournament: str, round_number: Optional[int] = None) -> TableData:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Round Results")

        work = df.copy()
        if round_number is not None:
            work = work[pd.to_numeric(work[Columns.round_number], errors="coerce").eq(float(round_number))]
        if work.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Round Results")
        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0).astype(int)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        id_col = Columns.player_id if Columns.player_id in work.columns else "__player_id_missing__"
        if id_col == "__player_id_missing__":
            work[id_col] = work[Columns.player_name].astype(str)

        key_cols = [Columns.round_number, Columns.round_name, Columns.player_name, id_col, Columns.club]

        # One row per stage + player with explicit game columns.
        game_numbers = sorted([int(g) for g in work[Columns.game_number].dropna().unique().tolist()])
        per_game = (
            work.groupby(key_cols + [Columns.game_number], dropna=False)[Columns.score]
            .sum()
            .reset_index()
        )
        pivot = per_game.pivot_table(
            index=key_cols,
            columns=Columns.game_number,
            values=Columns.score,
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        for g in game_numbers:
            if g not in pivot.columns:
                pivot[g] = 0

        pivot["round_total"] = pivot[game_numbers].sum(axis=1) if game_numbers else 0
        pivot["avg_score"] = (
            (pivot["round_total"] / max(len(game_numbers), 1)).round(1)
            if len(game_numbers) > 0
            else 0.0
        )
        pivot = pivot.sort_values(by=[Columns.player_name, Columns.round_number]).reset_index(drop=True)
        pivot["overall_total"] = pivot.groupby([Columns.player_name, id_col], dropna=False)["round_total"].cumsum()

        # Sort for display: stage first, then strongest totals.
        pivot = pivot.sort_values(
            by=[Columns.round_number, "round_total", Columns.player_name],
            ascending=[True, False, True],
        ).reset_index(drop=True)

        columns = [
            Column(title="Stage", field="round_name", width="150px", align="left"),
            Column(title="Player", field="player", width="220px", align="left"),
            Column(title="Club", field="club", width="220px", align="left"),
        ]
        for g in game_numbers:
            columns.append(
                Column(
                    title=f"G{g}",
                    field=f"game_{g}",
                    width="75px",
                    align="center",
                    decimal_places=0,
                )
            )
        columns.extend(
            [
                Column(title="Round Total", field="round_total", width="110px", align="center", decimal_places=0),
                Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1),
                Column(title="Overall Total", field="overall_total", width="120px", align="center", decimal_places=0),
            ]
        )

        data = []
        previous_player_key = None
        for _, row in pivot.iterrows():
            player_key = (str(row.get(Columns.player_name, "")), str(row.get(id_col, "")), str(row.get(Columns.club, "")))
            show_player = True
            if round_number is None and previous_player_key == player_key:
                # Visual "merge": blank repeated cells for player/club across stages.
                show_player = False

            entry = [
                str(row.get(Columns.round_name, "")),
                str(row.get(Columns.player_name, "")) if show_player else "",
                str(row.get(Columns.club, "")) if show_player else "",
            ]
            for g in game_numbers:
                entry.append(int(row.get(g, 0)))
            entry.append(int(row.get("round_total", 0)))
            entry.append(float(row.get("avg_score", 0.0)))
            entry.append(int(row.get("overall_total", 0)))
            data.append(entry)
            previous_player_key = player_key

        return TableData(columns=columns, data=data, title=f"{tournament} Round Results")

    def get_player_round_table(self, season: str, tournament: str, player: str) -> TableData:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{player} - Tournament Progress")

        work = df.copy()
        work = work[work[Columns.player_name].astype(str).str.strip().eq(str(player).strip())]
        if work.empty:
            return TableData(columns=[], data=[], title=f"{player} - Tournament Progress")

        all_df = self._get_tournament_df(season=season, tournament=tournament).copy()
        all_df[Columns.score] = pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0)
        all_df[Columns.round_number] = pd.to_numeric(all_df[Columns.round_number], errors="coerce").astype("Int64")
        all_df[Columns.game_number] = pd.to_numeric(all_df[Columns.game_number], errors="coerce").astype("Int64")

        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce").astype("Int64")
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        round_meta = (
            all_df[[Columns.round_number, Columns.round_name]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        round_numbers = [int(r) for r in round_meta[Columns.round_number].tolist()]
        round_name_map = {int(r[Columns.round_number]): str(r.get(Columns.round_name, "") or f"Round {int(r[Columns.round_number])}") for _, r in round_meta.iterrows()}
        max_game = int(pd.to_numeric(all_df[Columns.game_number], errors="coerce").dropna().max()) if not all_df.empty else -1
        game_cols = list(range(max_game + 1)) if max_game >= 0 else []

        rows = []
        running_total = 0
        running_games = 0

        for rn in round_numbers:
            round_all = all_df[all_df[Columns.round_number].eq(float(rn))].copy()
            round_player = work[work[Columns.round_number].eq(float(rn))].copy()
            if round_player.empty:
                # Skip non-participated rounds for this player.
                continue

            player_game_scores = {
                int(r[Columns.game_number]): int(r[Columns.score])
                for _, r in round_player.iterrows()
                if pd.notna(r[Columns.game_number])
            }
            round_total = int(round_player[Columns.score].sum())
            round_games = int(round_player[Columns.score].count())
            round_avg = round(round_total / max(round_games, 1), 1)

            # Rank within round by total pins.
            round_totals = (
                round_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
            )
            round_rank = int(round_totals.rank(method="min", ascending=False).get(player, float("nan"))) if player in round_totals.index else None

            running_total += round_total
            running_games += round_games
            cum_avg = round(running_total / max(running_games, 1), 1)

            # Cumulative rank up to current round.
            upto_all = all_df[all_df[Columns.round_number].le(float(rn))].copy()
            cum_totals = (
                upto_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
            )
            cum_rank = int(cum_totals.rank(method="min", ascending=False).get(player, float("nan"))) if player in cum_totals.index else None

            row = [round_name_map.get(rn, f"Round {rn}")]
            for g in game_cols:
                row.append(int(player_game_scores.get(g, 0)) if g in player_game_scores else "")
            row.extend(
                [
                    round_total,
                    round_avg,
                    round_rank if round_rank is not None else "",
                    running_total,
                    cum_avg,
                    cum_rank if cum_rank is not None else "",
                ]
            )
            rows.append(row)

        columns = [Column(title="Stage", field="stage", width="140px", align="left")]
        for g in game_cols:
            columns.append(Column(title=f"G{g}", field=f"game_{g}", width="70px", align="center", decimal_places=0))
        columns.extend(
            [
                Column(title="Round Total", field="round_total", width="105px", align="center", decimal_places=0),
                Column(title="Round Avg", field="round_avg", width="90px", align="center", decimal_places=1),
                Column(title="Round Rank", field="round_rank", width="95px", align="center", decimal_places=0),
                Column(title="Cum Total", field="cum_total", width="95px", align="center", decimal_places=0),
                Column(title="Cum Avg", field="cum_avg", width="90px", align="center", decimal_places=1),
                Column(title="Cum Rank", field="cum_rank", width="90px", align="center", decimal_places=0),
            ]
        )
        return TableData(columns=columns, data=rows, title=f"{player} - Tournament Progress")

    def get_player_best_efforts(self, season: str, tournament: str, player: str) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"highest_game": None, "highest_pair": None, "highest_block": None}
        work = df[df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if work.empty:
            return {"highest_game": None, "highest_pair": None, "highest_block": None}

        work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
        work[Columns.game_number] = pd.to_numeric(work[Columns.game_number], errors="coerce").astype("Int64")

        # Highest game
        hg_row = work.sort_values(by=Columns.score, ascending=False).iloc[0]
        highest_game = {
            "score": int(hg_row[Columns.score]),
            "stage": str(hg_row.get(Columns.round_name, "")),
            "game": int(hg_row[Columns.game_number]) + 1 if pd.notna(hg_row[Columns.game_number]) else None,
        }

        # Highest pair
        pair_best = None
        for stage, gdf in work.groupby(Columns.round_name, dropna=False):
            scores = {int(r[Columns.game_number]): int(r[Columns.score]) for _, r in gdf.iterrows() if pd.notna(r[Columns.game_number])}
            one_based = sorted([x + 1 for x in scores.keys()])
            for start in one_based:
                if start % 2 == 1 and (start + 1) in one_based:
                    total = int(scores[start - 1] + scores[start])
                    cand = {"score": total, "stage": str(stage or ""), "pair": f"G{start}+G{start+1}"}
                    if pair_best is None or total > pair_best["score"]:
                        pair_best = cand

        # Highest block (stage total)
        block_df = (
            work.groupby(Columns.round_name, dropna=False)[Columns.score]
            .sum()
            .reset_index(name="score")
            .sort_values(by="score", ascending=False)
        )
        highest_block = None
        if not block_df.empty:
            b = block_df.iloc[0]
            highest_block = {"score": int(b["score"]), "stage": str(b.get(Columns.round_name, ""))}

        return {"highest_game": highest_game, "highest_pair": pair_best, "highest_block": highest_block}

    def get_player_progress_series(self, season: str, tournament: str, player: str) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return {"labels": [], "avg_series": [], "position_series": [], "round_end_lines": [], "cut_lines_avg": [], "cut_lines_position": []}

        all_df = df.copy()
        all_df[Columns.score] = pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0)
        all_df[Columns.round_number] = pd.to_numeric(all_df[Columns.round_number], errors="coerce").astype("Int64")
        all_df[Columns.game_number] = pd.to_numeric(all_df[Columns.game_number], errors="coerce").astype("Int64")

        round_meta = (
            all_df[[Columns.round_number, Columns.round_name, Columns.game_number]]
            .dropna(subset=[Columns.round_number, Columns.game_number])
            .groupby([Columns.round_number, Columns.round_name], dropna=False)[Columns.game_number]
            .max()
            .reset_index()
            .sort_values(by=Columns.round_number)
        )
        # max game index + 1 == number of games in round
        round_lengths = [
            (int(r[Columns.round_number]), str(r.get(Columns.round_name, "")), int(r[Columns.game_number]) + 1)
            for _, r in round_meta.iterrows()
        ]
        total_games = sum(length for _, _, length in round_lengths)
        labels = [f"G{i}" for i in range(1, total_games + 1)]

        player_df = all_df[all_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if player_df.empty:
            return {"labels": labels, "avg_series": [], "position_series": [], "round_end_lines": [], "cut_lines_avg": [], "cut_lines_position": []}

        avg_series: List[float] = []
        position_series: List[int] = []
        round_end_lines: List[int] = []
        cut_lines_avg: List[float] = []
        cut_lines_position: List[int] = []

        cum_player_score = 0
        cum_player_games = 0
        x_cursor = 0

        for rn, _, length in round_lengths:
            round_all = all_df[all_df[Columns.round_number].eq(float(rn))].copy()
            round_player = player_df[player_df[Columns.round_number].eq(float(rn))].copy()

            # Build cumulative snapshots at each game in this round.
            round_all_scores = (
                round_all.groupby([Columns.player_name, Columns.game_number], dropna=False)[Columns.score]
                .sum()
                .reset_index()
            )
            player_game_scores = {
                int(g): int(s)
                for g, s in round_player.groupby(Columns.game_number, dropna=False)[Columns.score].sum().to_dict().items()
            }

            # cumulative totals up to this round (for all players)
            prev_all = all_df[all_df[Columns.round_number].lt(float(rn))].copy()
            base_totals = prev_all.groupby(Columns.player_name, dropna=False)[Columns.score].sum().to_dict()
            base_games = prev_all.groupby(Columns.player_name, dropna=False)[Columns.score].count().to_dict()

            for g in range(length):
                # player cumulative
                if g in player_game_scores:
                    cum_player_score += player_game_scores[g]
                    cum_player_games += 1
                if cum_player_games > 0:
                    avg_series.append(round(cum_player_score / cum_player_games, 2))
                else:
                    avg_series.append(avg_series[-1] if avg_series else 0.0)

                # position cumulative among all players
                upto_round = round_all_scores[round_all_scores[Columns.game_number].le(float(g))]
                add_totals = upto_round.groupby(Columns.player_name, dropna=False)[Columns.score].sum().to_dict()
                scores = {}
                for p_name in set(list(base_totals.keys()) + list(add_totals.keys())):
                    scores[p_name] = float(base_totals.get(p_name, 0)) + float(add_totals.get(p_name, 0))
                ranked = sorted(scores.items(), key=lambda t: (-t[1], t[0]))
                rank_map = {name: idx + 1 for idx, (name, _) in enumerate(ranked)}
                position_series.append(int(rank_map.get(player, position_series[-1] if position_series else len(ranked) + 1)))

            x_cursor += length
            round_end_lines.append(x_cursor)

            # Cut line averages should be based on cumulative standings at cut points.
            # This avoids stage-only cut values distorting cumulative average reference lines.
            total_games_upto = sum(l for rno, _, l in round_lengths if rno <= rn)
            upto_all = all_df[all_df[Columns.round_number].le(float(rn))].copy()
            cum_totals = (
                upto_all.groupby(Columns.player_name, dropna=False)[Columns.score]
                .sum()
                .sort_values(ascending=False)
                .tolist()
            )
            # position cut targets by round number from configured format
            if rn == 1:
                cut_lines_position.append(40)
                if len(cum_totals) >= 40:
                    cut_lines_avg.append(round(float(cum_totals[39]) / max(total_games_upto, 1), 2))
            elif rn == 2:
                cut_lines_position.append(20)
                if len(cum_totals) >= 20:
                    cut_lines_avg.append(round(float(cum_totals[19]) / max(total_games_upto, 1), 2))
            elif rn == 3:
                cut_lines_position.append(1)

        # pad to total length (flat line after elimination)
        while len(avg_series) < total_games:
            avg_series.append(avg_series[-1] if avg_series else 0.0)
        while len(position_series) < total_games:
            position_series.append(position_series[-1] if position_series else 999)

        return {
            "labels": labels,
            "avg_series": avg_series[:total_games],
            "position_series": position_series[:total_games],
            "round_end_lines": round_end_lines,
            "cut_lines_avg": cut_lines_avg,
            "cut_lines_position": cut_lines_position,
        }

    def get_tournament_section(self, season: str, tournament: str, round_number: Optional[int] = None, top_n: int = 5) -> Dict[str, Any]:
        return {
            "cards": self.get_summary_cards(season, tournament, round_number=round_number, top_n=top_n).get("cards", []),
            "leaderboard": self.get_leaderboard_table(season, tournament, round_number).to_dict(),
            "round_results": self.get_round_results_table(season, tournament, round_number).to_dict(),
            "rounds": self.get_rounds(season, tournament),
            "best_efforts": self.get_best_efforts(season, tournament, round_number=round_number, top_n=top_n),
        }

    def get_player_section(self, season: str, tournament: str, player: str) -> Dict[str, Any]:
        progress = self.get_player_progress_series(season, tournament, player)
        player_df = self._get_tournament_df(season=season, tournament=tournament)
        player_df = player_df[player_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())]
        player_club = None
        if not player_df.empty and Columns.club in player_df.columns:
            club_vals = player_df[Columns.club].dropna().astype(str).tolist()
            player_club = club_vals[0] if club_vals else None
        avg_series = progress.get("avg_series", []) or []
        pos_series = progress.get("position_series", []) or []
        labels = progress.get("labels", []) or []

        avg_value = round(float(avg_series[-1]), 2) if avg_series else None
        final_position = int(pos_series[-1]) if pos_series else None
        best_position = None
        best_position_game = None
        if pos_series:
            best_position = int(min(pos_series))
            try:
                best_idx = pos_series.index(best_position)
                best_position_game = labels[best_idx] if best_idx < len(labels) else None
            except ValueError:
                best_position_game = None

        return {
            "player": player,
            "player_club": player_club,
            "round_table": self.get_player_round_table(season, tournament, player).to_dict(),
            "best_efforts": self.get_player_best_efforts(season, tournament, player),
            "progress_series": progress,
            "summary": {
                "average": avg_value,
                "best_position": best_position,
                "best_position_game": best_position_game,
                "final_position": final_position,
            },
        }
