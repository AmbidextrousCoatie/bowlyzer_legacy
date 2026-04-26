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

        # Normalize frequently used tournament keys so downstream groupby/pivot
        # logic is stable even when source CSV has empty cells (read as NaN).
        if Columns.club in df.columns:
            df[Columns.club] = df[Columns.club].fillna("").astype(str).str.strip()
        if Columns.player_name in df.columns:
            df[Columns.player_name] = df[Columns.player_name].fillna("").astype(str).str.strip()
        if Columns.player_id in df.columns:
            df[Columns.player_id] = df[Columns.player_id].fillna("").astype(str).str.strip()
        if Columns.round_name in df.columns:
            df[Columns.round_name] = df[Columns.round_name].fillna("").astype(str).str.strip()
        return df

    def get_tournaments(self, season: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=None)
        if df.empty or Columns.event_name not in df.columns:
            return []
        return sorted([x for x in df[Columns.event_name].dropna().astype(str).unique().tolist() if x.strip()])

    def get_seasons(self, tournament: Optional[str] = None) -> List[str]:
        df = self._get_tournament_df(season=None, tournament=tournament)
        if df.empty or Columns.season not in df.columns:
            return []
        vals = [str(x).strip() for x in df[Columns.season].dropna().astype(str).tolist() if str(x).strip()]
        return sorted(list(set(vals)))

    def get_players(self, season: str, tournament: str, round_number: Optional[int] = None) -> List[str]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if round_number is not None and not df.empty:
            df = self._scope_df(df, round_number)
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

    @staticmethod
    def _has_any_club_value(df: pd.DataFrame) -> bool:
        if Columns.club not in df.columns:
            return False
        vals = df[Columns.club].fillna("").astype(str).str.strip()
        return vals.ne("").any()

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
        latest_round_date_subtitle = ""
        if latest_round.get("round_number") is not None and Columns.date in scope_df.columns:
            latest_round_df_for_date = scope_df[
                pd.to_numeric(scope_df[Columns.round_number], errors="coerce").eq(float(latest_round["round_number"]))
            ].copy()
            date_vals = (
                latest_round_df_for_date[Columns.date].dropna().astype(str).str.strip().tolist()
                if not latest_round_df_for_date.empty
                else []
            )
            date_vals = sorted([d for d in date_vals if d])
            if date_vals:
                latest_round_date_subtitle = date_vals[0] if len(set(date_vals)) == 1 else f"{date_vals[0]} to {date_vals[-1]}"

        # Stage winner is specific to selected stage (or latest stage when none selected).
        stage_round_number = round_number if round_number is not None else latest_round.get("round_number")

        # Tournament leader should reflect cumulative totals up to the selected stage.
        # If no stage is selected, use the latest available stage as the cutoff.
        tournament_leader = None
        tournament_leader_avg = None
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
                    leader_name = str(tournament_leader[Columns.player_name])
                    leader_games = int(
                        cumulative_df[cumulative_df[Columns.player_name].astype(str).eq(leader_name)][Columns.score].count()
                    )
                    if leader_games > 0:
                        tournament_leader_avg = round(float(tournament_leader["total_score"]) / leader_games, 1)

        # Stage winner remains stage-specific for the selected/latest stage.
        stage_leaderboard = self._build_leaderboard_df(df, stage_round_number) if stage_round_number is not None else pd.DataFrame()
        stage_winner = stage_leaderboard.iloc[0] if not stage_leaderboard.empty else None
        stage_winner_avg = None
        if stage_winner is not None and stage_round_number is not None:
            stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(stage_round_number))].copy()
            stage_df[Columns.score] = pd.to_numeric(stage_df[Columns.score], errors="coerce").fillna(0)
            stage_winner_name = str(stage_winner["player"])
            stage_total = float(stage_winner["total_score"])
            stage_games = int(stage_df[stage_df[Columns.player_name].astype(str).eq(stage_winner_name)][Columns.score].count())
            if stage_games > 0:
                stage_winner_avg = round(stage_total / stage_games, 1)

        cards = [
            {"title": "Tournament", "value": tournament, "subtitle": season, "type": "stat"},
            {
                "title": "Current Round",
                "value": latest_round.get("round_name") or f"Round {latest_round.get('round_number')}",
                "subtitle": latest_round_date_subtitle
                or (f"#{latest_round.get('round_number')}" if latest_round.get("round_number") else ""),
                "type": "stat",
            },
        ]
        cut_line_card = None
        if Columns.cut_line in scope_df.columns and latest_round.get("round_number") is not None:
            latest_round_df = scope_df[pd.to_numeric(scope_df[Columns.round_number], errors="coerce").eq(float(latest_round["round_number"]))].copy()
            if not latest_round_df.empty:
                max_game = pd.to_numeric(latest_round_df[Columns.game_number], errors="coerce").max()
                latest_snap = latest_round_df[pd.to_numeric(latest_round_df[Columns.game_number], errors="coerce").eq(max_game)]
                cut_vals = pd.to_numeric(latest_snap[Columns.cut_line], errors="coerce").dropna()
                if not cut_vals.empty:
                    cut_score = int(cut_vals.iloc[0])
                    games_in_scope = int(max_game) + 1 if pd.notna(max_game) else 0
                    if games_in_scope > 0:
                        cut_display = f"{cut_score} pins (\u2300{(cut_score / games_in_scope):.1f})"
                    else:
                        cut_display = f"{cut_score} pins"

                    # Prefer the player sitting right on the cut score.
                    cut_player = "N/A"
                    if Columns.cumulative_score in latest_snap.columns and Columns.player_name in latest_snap.columns:
                        score_col = pd.to_numeric(latest_snap[Columns.cumulative_score], errors="coerce")
                        candidates = latest_snap[score_col.eq(float(cut_score))].copy()
                        if not candidates.empty:
                            if Columns.stage_rank in candidates.columns:
                                candidates["__rank_num__"] = pd.to_numeric(candidates[Columns.stage_rank], errors="coerce")
                                candidates = candidates.sort_values(by="__rank_num__", ascending=False)
                            cut_player = str(candidates.iloc[0].get(Columns.player_name, "N/A"))
                    cut_line_card = {
                        "title": "Cut Line",
                        "value": cut_player,
                        "subtitle": cut_display,
                        "type": "stat",
                    }
        if tournament_leader is not None:
            subtitle = f"{int(tournament_leader['total_score'])} pins"
            if tournament_leader_avg is not None:
                subtitle = f"{subtitle} (\u2300{tournament_leader_avg:.1f})"
            cards.append(
                {
                    "title": "Tournament Leader",
                    "value": tournament_leader[Columns.player_name],
                    "subtitle": subtitle,
                    "type": "stat",
                }
            )
        cards.append(
            {
                "title": "Participants",
                "value": participants,
                "subtitle": "Field size",
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
            stage_subtitle = f"{stage_name}: {int(stage_winner['total_score'])} pins"
            if stage_winner_avg is not None:
                stage_subtitle = f"{stage_subtitle} (\u2300{stage_winner_avg:.1f})"
            cards.append(
                {
                    "title": "Stage Winner",
                    "value": stage_winner["player"],
                    "subtitle": stage_subtitle,
                    "type": "stat",
                }
            )
        if cut_line_card is not None:
            cards.append(cut_line_card)
        return {"cards": cards}

    def _build_leaderboard_df(self, df: pd.DataFrame, round_number: Optional[int] = None) -> pd.DataFrame:
        work = df.copy()
        if round_number is not None:
            work = work[pd.to_numeric(work[Columns.round_number], errors="coerce").eq(float(round_number))]
        if work.empty:
            return pd.DataFrame()
        include_club = self._has_any_club_value(work)

        # If postprocessed data exists, use the last game snapshot per player.
        if Columns.cumulative_score in work.columns and Columns.stage_rank in work.columns:
            game_vals = pd.to_numeric(work[Columns.game_number], errors="coerce")
            max_game = game_vals.max()
            snap = work[game_vals.eq(max_game)].copy()
            snap["rank"] = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
            snap["total_score"] = pd.to_numeric(snap[Columns.cumulative_score], errors="coerce")
            snap["player"] = snap[Columns.player_name].astype(str)
            snap["player_id"] = snap[Columns.player_id].astype(str)
            snap["club"] = snap.get(Columns.club, "").astype(str) if include_club else ""
            out_cols = ["rank", "player", "player_id", "total_score"]
            if include_club:
                out_cols.insert(3, "club")
            out = snap[out_cols].dropna(subset=["total_score"])
            return out.sort_values(by=["rank", "player"]).reset_index(drop=True)

        group_keys = [Columns.player_name, Columns.player_id]
        if include_club:
            group_keys.append(Columns.club)
        grouped = (
            work.groupby(group_keys, dropna=False)[Columns.score]
            .sum()
            .reset_index()
            .rename(
                columns={
                    Columns.player_name: "player",
                    Columns.player_id: "player_id",
                    Columns.score: "total_score",
                }
            )
        )
        if include_club:
            grouped = grouped.rename(columns={Columns.club: "club"})
        else:
            grouped["club"] = ""
        grouped["rank"] = grouped["total_score"].rank(method="min", ascending=False).astype(int)
        return grouped.sort_values(by=["rank", "player"]).reset_index(drop=True)

    def get_leaderboard_table(self, season: str, tournament: str, round_number: Optional[int] = None) -> TableData:
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty:
            return TableData(columns=[], data=[], title=f"{tournament} Leaderboard")
        include_club = self._has_any_club_value(df)

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
                Column(title="Total", field="total_score", width="90px", align="center", decimal_places=0),
                Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1),
            ]
            if include_club:
                columns.insert(2, Column(title="Club", field="club", width="220px", align="left"))
                data_cols = ["rank", "player", "club", "total_score", "avg_score"]
            else:
                data_cols = ["rank", "player", "total_score", "avg_score"]
            data = leaderboard[data_cols].values.tolist() if not leaderboard.empty else []
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
        ]
        if include_club:
            columns.append(Column(title="Club", field="club", width="220px", align="left"))
        for rn in round_numbers:
            title = round_name_map.get(rn) or f"Round {rn}"
            columns.append(Column(title=title, field=f"round_{rn}", width="110px", align="center", decimal_places=0))
        columns.append(Column(title="Total", field="total_score", width="100px", align="center", decimal_places=0))
        columns.append(Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1))

        data = []
        for _, row in pivot.iterrows():
            entry = [int(row["rank"]), str(row.get(Columns.player_name, ""))]
            if include_club:
                entry.append(str(row.get(Columns.club, "")))
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
        include_club = self._has_any_club_value(df)

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

        key_cols = [Columns.round_number, Columns.round_name, Columns.player_name, id_col]
        if include_club:
            key_cols.append(Columns.club)

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

        include_stage_column = round_number is None
        columns = []
        if include_stage_column:
            columns.append(Column(title="Stage", field="round_name", width="150px", align="left"))
        columns.append(Column(title="Player", field="player", width="220px", align="left"))
        if include_club:
            columns.append(Column(title="Club", field="club", width="220px", align="left"))
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
            player_key = (
                str(row.get(Columns.player_name, "")),
                str(row.get(id_col, "")),
                str(row.get(Columns.club, "")) if include_club else "",
            )
            show_player = True
            if round_number is None and previous_player_key == player_key:
                # Visual "merge": blank repeated cells for player/club across stages.
                show_player = False

            entry = []
            if include_stage_column:
                entry.append(str(row.get(Columns.round_name, "")))
            entry.append(str(row.get(Columns.player_name, "")) if show_player else "")
            if include_club:
                entry.append(str(row.get(Columns.club, "")) if show_player else "")
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
        round_name_map = {rn: name for rn, name, _ in round_lengths}
        total_games = sum(length for _, _, length in round_lengths)
        labels = [f"G{i}" for i in range(1, total_games + 1)]

        # Derive per-round cut metadata from actual data snapshots (postprocessed CSV),
        # avoiding hardcoded cut positions that differ between tournaments.
        round_cut_meta: Dict[int, Dict[str, Optional[float]]] = {}
        if Columns.cut_line in all_df.columns:
            for rn, _, _ in round_lengths:
                stage_df = all_df[all_df[Columns.round_number].eq(float(rn))].copy()
                if stage_df.empty:
                    continue
                max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
                snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
                if snap.empty:
                    continue

                cut_vals = pd.to_numeric(snap[Columns.cut_line], errors="coerce").dropna()
                if cut_vals.empty:
                    continue
                cut_score = float(cut_vals.iloc[0])

                cut_position: Optional[float] = None
                if Columns.cumulative_score in snap.columns and Columns.stage_rank in snap.columns:
                    cum = pd.to_numeric(snap[Columns.cumulative_score], errors="coerce")
                    ranks = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
                    eq = ranks[cum.eq(cut_score)].dropna()
                    if not eq.empty:
                        cut_position = float(eq.max())
                    else:
                        ge = ranks[cum.ge(cut_score)].dropna()
                        if not ge.empty:
                            cut_position = float(ge.max())

                round_cut_meta[rn] = {"cut_score": cut_score, "cut_position": cut_position}
        cut_rounds_sorted = sorted(round_cut_meta.keys())
        qualifying_cut_round = cut_rounds_sorted[0] if len(cut_rounds_sorted) >= 1 else None
        round2_cut_round = cut_rounds_sorted[1] if len(cut_rounds_sorted) >= 2 else None

        player_df = all_df[all_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if player_df.empty:
            return {"labels": labels, "avg_series": [], "position_series": [], "round_end_lines": [], "cut_lines_avg": [], "cut_lines_position": []}

        avg_series: List[float] = []
        position_series: List[int] = []
        tournament_leader_avg_series: List[Optional[float]] = []
        round_end_lines: List[int] = []
        cut_lines_avg: List[float] = []
        cut_lines_position: List[int] = []
        dynamic_cut_series: Dict[int, List[Optional[float]]] = {rn: [] for rn in cut_rounds_sorted}

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

                # Tournament leader pace: cumulative average of the current leader at this game.
                add_games = upto_round.groupby(Columns.player_name, dropna=False)[Columns.score].count().to_dict()
                games_played = {}
                for p_name in set(list(base_games.keys()) + list(add_games.keys())):
                    games_played[p_name] = int(base_games.get(p_name, 0)) + int(add_games.get(p_name, 0))
                if ranked:
                    leader_name = ranked[0][0]
                    leader_total = float(scores.get(leader_name, 0.0))
                    leader_games = max(int(games_played.get(leader_name, 0)), 1)
                    tournament_leader_avg_series.append(round(leader_total / leader_games, 2))
                else:
                    tournament_leader_avg_series.append(None)

                # Dynamic cut-line averages by stage-local progress.
                # Cut Line in our data is stage cumulative, so divide by games played in THIS stage.
                games_in_stage_so_far = g + 1
                cut_avg_game: Optional[float] = None
                cut_vals_game = pd.to_numeric(
                    round_all[round_all[Columns.game_number].eq(float(g))][Columns.cut_line]
                    if Columns.cut_line in round_all.columns
                    else pd.Series([], dtype=float),
                    errors="coerce",
                ).dropna()
                cut_score_game = float(cut_vals_game.iloc[0]) if not cut_vals_game.empty else None
                if cut_score_game is not None:
                    cut_avg_game = round(cut_score_game / max(games_in_stage_so_far, 1), 2)

                for cut_rn in cut_rounds_sorted:
                    dynamic_cut_series[cut_rn].append(cut_avg_game if rn == cut_rn else None)

            x_cursor += length
            round_end_lines.append(x_cursor)
            # Horizontal cut-line references for stage-end snapshots.
            # Stage cut is stage cumulative, so normalize by stage length.
            stage_games = max(length, 1)
            cut_meta = round_cut_meta.get(rn) or {}
            cut_score = cut_meta.get("cut_score")
            cut_pos = cut_meta.get("cut_position")
            if cut_score is not None:
                cut_lines_avg.append(round(float(cut_score) / stage_games, 2))
            if cut_pos is not None:
                cut_lines_position.append(int(cut_pos))

        # pad to total length (flat line after elimination)
        while len(avg_series) < total_games:
            avg_series.append(avg_series[-1] if avg_series else 0.0)
        while len(position_series) < total_games:
            position_series.append(position_series[-1] if position_series else 999)
        while len(tournament_leader_avg_series) < total_games:
            tournament_leader_avg_series.append(None)
        for cut_rn in cut_rounds_sorted:
            while len(dynamic_cut_series[cut_rn]) < total_games:
                dynamic_cut_series[cut_rn].append(None)

        cut_line_series = []
        for rn in cut_rounds_sorted:
            cut_line_series.append(
                {
                    "key": f"round_{rn}",
                    "round_number": rn,
                    "label": round_name_map.get(rn) or f"Round {rn}",
                    "data": dynamic_cut_series[rn][:total_games],
                }
            )

        return {
            "labels": labels,
            "avg_series": avg_series[:total_games],
            "position_series": position_series[:total_games],
            "tournament_leader_avg_series": tournament_leader_avg_series[:total_games],
            "round_end_lines": round_end_lines,
            "cut_lines_avg": cut_lines_avg,
            "cut_lines_position": cut_lines_position,
            "cut_line_series": cut_line_series,
            "cut_lines_avg_dynamic": {
                f"round_{rn}": dynamic_cut_series[rn][:total_games] for rn in cut_rounds_sorted
            },
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
