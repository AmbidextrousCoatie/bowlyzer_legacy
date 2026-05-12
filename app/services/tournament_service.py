import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from app.models.table_data import Column, ColumnGroup, TableData
from app.services.i18n_service import i18n_service
from app.utils.color_constants import get_theme_color
from data_access.adapters.data_adapter_factory import DataAdapterFactory, DataAdapterSelector
from data_access.schema import Columns

# KO-Finale last cluster: best-of-3 pin games vs two-game scratch total (see database/data/tournament_ko_config.json).
KO_FINALE_SERIES_BO3 = "bo3_pins"
KO_FINALE_SERIES_SCRATCH_2G = "scratch_total_2g"


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

    @staticmethod
    def _played_games_count(series: pd.Series) -> int:
        scores = pd.to_numeric(series, errors="coerce").fillna(0)
        return int(scores.gt(0).sum())

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

        ko_bracket_pre = self._build_ko_bracket_payload(season, tournament)
        ko_fin_rn = self._ko_finale_round_number(df)
        is_ko_finale_view = (
            round_number is not None
            and ko_fin_rn is not None
            and int(round_number) == int(ko_fin_rn)
            and bool(ko_bracket_pre.get("matches"))
        )
        fin_m = next((m for m in ko_bracket_pre.get("matches", []) if m.get("key") == "F"), None)
        ko_final_winner_name = self._ko_match_winner_name(fin_m) if fin_m else None
        # Gesamt + decided KO final: same summary as KO-finale filter — winner only, no pin-leader / stage cards.
        gesamt_ko_tournament_winner = (
            round_number is None
            and ko_fin_rn is not None
            and bool(ko_bracket_pre.get("matches"))
            and bool(ko_final_winner_name)
        )

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

        # Helper: total games up to a round (for cumulative averages).
        def _games_upto_round(target_round: Optional[int]) -> int:
            if target_round is None or Columns.round_number not in df.columns or Columns.game_number not in df.columns:
                return 0
            upto = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(target_round))].copy()
            if upto.empty:
                return 0
            meta = (
                upto[[Columns.round_number, Columns.game_number]]
                .dropna(subset=[Columns.round_number, Columns.game_number])
                .groupby(Columns.round_number, dropna=False)[Columns.game_number]
                .max()
                .reset_index()
            )
            if meta.empty:
                return 0
            return int(meta[Columns.game_number].apply(lambda g: int(g) + 1).sum())

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
                        self._played_games_count(
                            cumulative_df[cumulative_df[Columns.player_name].astype(str).eq(leader_name)][Columns.score]
                        )
                    )
                    if leader_games > 0:
                        tournament_leader_avg = round(float(tournament_leader["total_score"]) / leader_games, 1)

        # Stage winner remains stage-specific for the selected/latest stage:
        # winner is determined from stage-only scores (not cumulative totals).
        stage_winner = None
        stage_winner_avg = None
        if stage_round_number is not None:
            stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(stage_round_number))].copy()
            stage_df[Columns.score] = pd.to_numeric(stage_df[Columns.score], errors="coerce").fillna(0)
            if not stage_df.empty:
                grouped = (
                    stage_df.groupby(Columns.player_name, dropna=False)[Columns.score]
                    .sum()
                    .reset_index(name="total_score")
                    .sort_values(by=["total_score", Columns.player_name], ascending=[False, True])
                    .reset_index(drop=True)
                )
                if not grouped.empty:
                    winner_name = str(grouped.iloc[0][Columns.player_name])
                    winner_total = float(grouped.iloc[0]["total_score"])
                    stage_games = int(
                        self._played_games_count(
                            stage_df[stage_df[Columns.player_name].astype(str).eq(winner_name)][Columns.score]
                        )
                    )
                    stage_winner = {"player": winner_name, "total_score": winner_total}
                    if stage_games > 0:
                        stage_winner_avg = round(winner_total / stage_games, 1)

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
                    games_in_scope = _games_upto_round(int(latest_round["round_number"]))
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
                                # At tied cut scores, show the best (lowest) rank at the cut.
                                candidates = candidates.sort_values(by="__rank_num__", ascending=True)
                            cut_player = str(candidates.iloc[0].get(Columns.player_name, "N/A"))
                    cut_line_card = {
                        "title": "Cut Line",
                        "value": cut_player,
                        "subtitle": cut_display,
                        "type": "stat",
                    }
        if cut_line_card is None:
            cut_line_card = self._ko_cut_line_card_from_config_rank(df, season, tournament)
        if tournament_leader is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
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
        if (is_ko_finale_view or gesamt_ko_tournament_winner) and ko_final_winner_name:
            cards.append(
                {
                    "title": "Tournament Winner",
                    "value": ko_final_winner_name,
                    "subtitle": self._ko_final_winner_card_subtitle(fin_m) if fin_m else "",
                    "type": "stat",
                }
            )
        if stage_winner is not None and stage_round_number is not None and not is_ko_finale_view and not gesamt_ko_tournament_winner:
            stage_name = (
                latest_round.get("round_name")
                if round_number is None
                else str(scope_df[Columns.round_name].dropna().iloc[0]) if Columns.round_name in scope_df.columns and not scope_df[Columns.round_name].dropna().empty
                else f"Round {stage_round_number}"
            )
            stage_subtitle = f"{stage_name}: {int(stage_winner['total_score'])} pins"
            if stage_winner_avg is not None:
                # Stage Winner is stage-local: stage total divided by games in this stage.
                stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(stage_round_number))].copy()
                stage_df[Columns.score] = pd.to_numeric(stage_df[Columns.score], errors="coerce").fillna(0)
                stage_winner_name = str(stage_winner["player"])
                stage_total = float(stage_winner["total_score"])
                stage_games = int(stage_df[stage_df[Columns.player_name].astype(str).eq(stage_winner_name)][Columns.score].count())
                stage_games = int(
                    self._played_games_count(
                        stage_df[stage_df[Columns.player_name].astype(str).eq(stage_winner_name)][Columns.score]
                    )
                )
                if stage_games > 0:
                    stage_winner_avg = round(stage_total / stage_games, 1)
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

        ko_fin_rn = self._ko_finale_round_number(df)
        ko_bracket = self._build_ko_bracket_payload(season, tournament)
        if (
            round_number is not None
            and ko_fin_rn is not None
            and int(round_number) == int(ko_fin_rn)
            and ko_bracket.get("matches")
        ):
            return self._ko_placements_table_data(season, tournament, df, ko_bracket)

        def _cut_position_for_round(source_df: pd.DataFrame, target_round: int) -> Optional[int]:
            return self._resolved_cut_position_for_round(source_df, target_round, season, tournament)

        # Single-stage mode: keep stage-specific leaderboard behavior.
        if round_number is not None:
            work = df.copy()
            work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
            work[Columns.round_number] = pd.to_numeric(work[Columns.round_number], errors="coerce")
            scoped = work[work[Columns.round_number].eq(float(round_number))].copy()
            if scoped.empty:
                return TableData(columns=[], data=[], title=f"{tournament} Leaderboard")

            id_col = Columns.player_id if Columns.player_id in work.columns else "__player_id_missing__"
            if id_col == "__player_id_missing__":
                work[id_col] = work[Columns.player_name].astype(str)
                scoped[id_col] = scoped[Columns.player_name].astype(str)

            group_keys = [Columns.player_name, id_col]
            if include_club:
                group_keys.append(Columns.club)

            # Selected round score.
            round_scores = (
                scoped.groupby(group_keys, dropna=False)[Columns.score]
                .sum()
                .reset_index(name="round_score")
            )

            # Tournament total up to selected round.
            upto = work[work[Columns.round_number].le(float(round_number))].copy()
            total_scores = (
                upto.groupby(group_keys, dropna=False)[Columns.score]
                .sum()
                .reset_index(name="total_score")
            )

            leaderboard = round_scores.merge(total_scores, on=group_keys, how="left")
            leaderboard["rank"] = leaderboard["total_score"].rank(method="min", ascending=False).astype(int)
            games_per_player = (
                scoped[scoped[Columns.score].gt(0)]
                .groupby([Columns.player_name], dropna=False)
                .size()
                .to_dict()
            )
            leaderboard["avg_score"] = leaderboard.apply(
                lambda r: round(float(r["round_score"]) / max(int(games_per_player.get(r[Columns.player_name], 1)), 1), 1),
                axis=1,
            )
            games_upto_player = (
                upto[upto[Columns.score].gt(0)].groupby([Columns.player_name], dropna=False).size().to_dict()
                if not upto.empty and Columns.player_name in upto.columns
                else {}
            )
            leaderboard["total_avg"] = leaderboard.apply(
                lambda r: round(float(r["total_score"]) / max(int(games_upto_player.get(r[Columns.player_name], 1)), 1), 1),
                axis=1,
            )
            leaderboard = leaderboard.sort_values(
                by=["total_score", Columns.player_name], ascending=[False, True]
            ).reset_index(drop=True)

            base_columns = [
                Column(title="#", field="rank", width="60px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("player"), field="player", width="220px", align="left"),
            ]
            if include_club:
                base_columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))
            total_group = ColumnGroup(
                title=i18n_service.get_text("ui.tournament.total_results"),
                highlighted=True,
                style={"backgroundColor": get_theme_color("surface_alt")},
                header_style={"fontWeight": "bold"},
                columns=[
                    Column(title=i18n_service.get_text("score"), field="total_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="total_avg", width="110px", align="center", decimal_places=1),
                ],
            )
            stage_group = ColumnGroup(
                title=i18n_service.get_text("ui.tournament.stage_results"),
                columns=[
                    Column(title=i18n_service.get_text("score"), field="round_score", width="110px", align="center", decimal_places=0),
                    Column(title=i18n_service.get_text("average"), field="avg_score", width="100px", align="center", decimal_places=1),
                ],
            )
            data = []
            row_metadata = []
            cell_metadata: Dict[str, Dict[str, Any]] = {}
            for row_idx, (_, row) in enumerate(leaderboard.iterrows()):
                entry = [int(row["rank"]), str(row.get(Columns.player_name, ""))]
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                entry.append(int(row.get("total_score", 0)))
                entry.append(float(row.get("total_avg", 0.0)))
                entry.append(int(row.get("round_score", 0)))
                entry.append(float(row.get("avg_score", 0.0)))
                data.append(entry)

                # Stage table shading: qualified zone + emphasized cut row.
                cut_pos = _cut_position_for_round(df, int(round_number))
                rank_val = int(row.get("rank", 0))
                style: Dict[str, Any] = {}
                if cut_pos is not None and rank_val > 0:
                    if rank_val == 1:
                        style = {"backgroundColor": "#cfead6", "fontWeight": "700"}
                    elif rank_val < cut_pos:
                        style = {"backgroundColor": "#e6f4ea"}
                    elif rank_val == cut_pos:
                        style = {"backgroundColor": "#ffe8a1", "fontWeight": "700"}
                row_metadata.append({"styling": {}})
                if style:
                    cell_metadata[f"{row_idx}:0"] = style
            return TableData(
                columns=[
                    ColumnGroup(
                        title=i18n_service.get_text("ranking"),
                        frozen="left",
                        style={"backgroundColor": "#f8f9fa"},
                        columns=base_columns,
                    ),
                    total_group,
                    stage_group,
                ],
                data=data,
                title=f"{tournament} Leaderboard",
                default_sort={"field": "total_score", "dir": "desc"},
                row_metadata=row_metadata,
                cell_metadata=cell_metadata,
                config={
                    "stickyHeader": True,
                    "striped": True,
                    "hover": True,
                    "responsive": True,
                    "compact": False,
                    "stripedColGroups": True,
                },
            )

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
        games_per_player_all = (
            work[work[Columns.score].gt(0)]
            .groupby([Columns.player_name, id_col], dropna=False)
            .size()
            .reset_index(name="games_played")
        )
        pivot = pivot.merge(games_per_player_all, on=[Columns.player_name, id_col], how="left")
        pivot["games_played"] = pd.to_numeric(pivot["games_played"], errors="coerce").fillna(1)
        pivot["total_avg"] = (pivot["total_score"] / pivot["games_played"]).round(1)
        pivot = pivot.sort_values(by=["total_score", Columns.player_name], ascending=[False, True]).reset_index(drop=True)
        pivot["rank"] = pivot["total_score"].rank(method="min", ascending=False).astype(int)

        columns = [
            Column(title="#", field="rank", width="60px", align="center", decimal_places=0),
            Column(title=i18n_service.get_text("player"), field="player", width="220px", align="left"),
        ]
        if include_club:
            columns.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))
        for rn in round_numbers:
            title = round_name_map.get(rn) or f"Round {rn}"
            columns.append(Column(title=title, field=f"round_{rn}", width="110px", align="center", decimal_places=0))
        columns.append(Column(title=i18n_service.get_text("total"), field="total_score", width="100px", align="center", decimal_places=0))
        columns.append(Column(title=i18n_service.get_text("average"), field="total_avg", width="110px", align="center", decimal_places=1))

        data = []
        row_metadata = []
        cell_metadata: Dict[str, Dict[str, Any]] = {}
        # Total table shading: multi-band cut lines (first 3 stage cuts, if available).
        round_meta = (
            work[[Columns.round_number]]
            .dropna(subset=[Columns.round_number])
            .drop_duplicates()
            .sort_values(by=Columns.round_number)
        )
        cut_positions: List[int] = []
        for _, rr in round_meta.iterrows():
            rn = int(rr[Columns.round_number])
            pos = _cut_position_for_round(df, rn)
            if pos is not None and pos > 0 and pos not in cut_positions:
                cut_positions.append(pos)
            if len(cut_positions) >= 3:
                break
        cut_positions = sorted(cut_positions)

        for row_idx, (_, row) in enumerate(pivot.iterrows()):
            entry = [int(row["rank"]), str(row.get(Columns.player_name, ""))]
            if include_club:
                entry.append(str(row.get(Columns.club, "")))
            for rn in round_numbers:
                entry.append(int(row.get(rn, 0)))
            entry.append(int(row.get("total_score", 0)))
            entry.append(float(row.get("total_avg", 0.0)))
            data.append(entry)

            rank_val = int(row.get("rank", 0))
            style: Dict[str, Any] = {}
            if cut_positions and rank_val > 0:
                # Band 1 strongest, then progressively lighter up to cut line 3.
                if rank_val <= cut_positions[0]:
                    style = {"backgroundColor": "#cfead6"}
                elif len(cut_positions) >= 2 and rank_val <= cut_positions[1]:
                    style = {"backgroundColor": "#e0f1e4"}
                elif len(cut_positions) >= 3 and rank_val <= cut_positions[2]:
                    style = {"backgroundColor": "#edf7ef"}
                if rank_val == 1:
                    style["fontWeight"] = "700"
            row_metadata.append({"styling": {}})
            if style:
                cell_metadata[f"{row_idx}:0"] = style

        lead_count = 2 + (1 if include_club else 0)
        leading_cols = columns[:lead_count]
        remaining_cols = columns[lead_count:]
        grouped_columns = [
            ColumnGroup(
                title="",
                frozen="left",
                style={"backgroundColor": "#f8f9fa"},
                columns=leading_cols,
            ),
            ColumnGroup(title="", columns=remaining_cols),
        ]

        return TableData(
            columns=grouped_columns,
            data=data,
            title=f"{tournament} Leaderboard",
            default_sort={"field": "total_score", "dir": "desc"},
            row_metadata=row_metadata,
            cell_metadata=cell_metadata,
            config={
                "stickyHeader": True,
                "striped": True,
                "hover": True,
                "responsive": True,
                "compact": False,
                "stripedColGroups": True,
            },
        )

    def get_round_results_table(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
    ) -> TableData:
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
        game_cols = [g for g in game_numbers if g in pivot.columns]
        if game_cols:
            played_games = pivot[game_cols].apply(pd.to_numeric, errors="coerce").fillna(0).gt(0).sum(axis=1)
            pivot["avg_score"] = (pivot["round_total"] / played_games.replace(0, 1)).round(1)
        else:
            pivot["avg_score"] = 0.0
        pivot = pivot.sort_values(by=[Columns.player_name, Columns.round_number]).reset_index(drop=True)
        pivot["overall_total"] = pivot.groupby([Columns.player_name, id_col], dropna=False)["round_total"].cumsum()

        # Sort for display: stage first, then strongest totals.
        pivot = pivot.sort_values(
            by=[Columns.round_number, "round_total", Columns.player_name],
            ascending=[True, False, True],
        ).reset_index(drop=True)

        include_stage_column = round_number is None

        # Single-stage mode: grouped columns with overall-standing rank and total avg.
        if round_number is not None:
            all_work = df.copy()
            all_work[Columns.score] = pd.to_numeric(all_work[Columns.score], errors="coerce").fillna(0).astype(int)
            all_work[Columns.round_number] = pd.to_numeric(all_work[Columns.round_number], errors="coerce").astype("Int64")

            upto = all_work[all_work[Columns.round_number].le(float(round_number))].copy()
            overall = (
                upto.groupby([Columns.player_name, id_col], dropna=False)[Columns.score]
                .sum()
                .reset_index(name="overall_score")
            )
            overall_games = (
                upto[upto[Columns.score].gt(0)]
                .groupby([Columns.player_name, id_col], dropna=False)[Columns.score]
                .count()
                .reset_index(name="overall_games")
            )
            overall = overall.merge(overall_games, on=[Columns.player_name, id_col], how="left")
            overall["overall_games"] = pd.to_numeric(overall["overall_games"], errors="coerce").fillna(1)
            overall["overall_avg"] = (overall["overall_score"] / overall["overall_games"]).round(1)
            overall["overall_rank"] = overall["overall_score"].rank(method="min", ascending=False).astype(int)

            pivot = pivot.merge(
                overall[[Columns.player_name, id_col, "overall_score", "overall_avg", "overall_rank"]],
                on=[Columns.player_name, id_col],
                how="left",
            )
            pivot["overall_score"] = pd.to_numeric(pivot["overall_score"], errors="coerce").fillna(0).astype(int)
            pivot["overall_avg"] = pd.to_numeric(pivot["overall_avg"], errors="coerce").fillna(0.0)
            pivot["overall_rank"] = pd.to_numeric(pivot["overall_rank"], errors="coerce").fillna(0).astype(int)
            pivot = pivot.sort_values(by=["overall_rank", "round_total", Columns.player_name], ascending=[True, False, True]).reset_index(drop=True)

            rank_cols = [
                Column(title="#", field="overall_rank", width="70px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("player"), field="player", width="220px", align="left"),
            ]
            if include_club:
                rank_cols.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="220px", align="left"))
            game_cols_schema = [
                Column(title=f"{g + 1}", field=f"game_{g}", width="75px", align="center", decimal_places=0)
                for g in game_numbers
            ]
            stage_result_cols = [
                Column(title=i18n_service.get_text("score"), field="stage_score", width="110px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("average"), field="stage_avg", width="100px", align="center", decimal_places=1),
            ]
            total_cols = [
                Column(title=i18n_service.get_text("score"), field="total_score", width="110px", align="center", decimal_places=0),
                Column(title=i18n_service.get_text("average"), field="total_avg", width="100px", align="center", decimal_places=1),
            ]

            columns = [
                ColumnGroup(
                    title=i18n_service.get_text("ranking"),
                    frozen="left",
                    style={"backgroundColor": get_theme_color("background")},
                    columns=rank_cols,
                ),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.games"), columns=game_cols_schema),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.stage_results"), columns=stage_result_cols),
                ColumnGroup(title=i18n_service.get_text("ui.tournament.total_results"), columns=total_cols),
            ]

            data = []
            for _, row in pivot.iterrows():
                entry = [int(row.get("overall_rank", 0)), str(row.get(Columns.player_name, ""))]
                if include_club:
                    entry.append(str(row.get(Columns.club, "")))
                for g in game_numbers:
                    entry.append(int(row.get(g, 0)))
                entry.append(int(row.get("round_total", 0)))
                entry.append(float(row.get("avg_score", 0.0)))
                entry.append(int(row.get("overall_score", 0)))
                entry.append(float(row.get("overall_avg", 0.0)))
                data.append(entry)

            return TableData(
                columns=columns,
                data=data,
                title=f"{tournament} Round Results",
                default_sort={"field": "overall_rank", "dir": "asc"},
                metadata={
                    "heatmap_ranges": {
                        "game_score": {
                            "min": 130,
                            "max": 270,
                            "high_band_min": 271,
                            "high_band_max": 299,
                            "perfect_score": 300,
                        }
                    }
                },
            )

        columns = []
        if include_stage_column:
            columns.append(Column(title="Stage", field="round_name", width="150px", align="left"))
        columns.append(Column(title="Player", field="player", width="220px", align="left"))
        if include_club:
            columns.append(Column(title="Club", field="club", width="220px", align="left"))
        for g in game_numbers:
            columns.append(
                Column(
                    title=f"{g + 1}",
                    field=f"game_{g}",
                    width="75px",
                    align="center",
                    decimal_places=0,
                )
            )
        columns.extend(
            [
                Column(title="Stage Score", field="round_total", width="110px", align="center", decimal_places=0),
                Column(title="Average", field="avg_score", width="90px", align="center", decimal_places=1),
                Column(title="Total Score", field="overall_total", width="120px", align="center", decimal_places=0),
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

        return TableData(
            columns=columns,
            data=data,
            title=f"{tournament} Round Results",
            metadata={
                "heatmap_ranges": {
                    "game_score": {
                        "min": 130,
                        "max": 270,
                        "high_band_min": 271,
                        "high_band_max": 299,
                        "perfect_score": 300,
                    }
                }
            },
        )

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
            round_games = int(self._played_games_count(round_player[Columns.score]))
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

        stage_info_cols = [
            Column(title=i18n_service.get_text("ui.tournament.stage"), field="stage", width="140px", align="left"),
        ]
        game_score_cols = [
            Column(title=f"{g + 1}", field=f"game_{g}", width="70px", align="center", decimal_places=0)
            for g in game_cols
        ]
        stage_stat_cols = [
            Column(title=i18n_service.get_text("score"), field="score_total", width="105px", align="center", decimal_places=0),
            Column(title=i18n_service.get_text("average"), field="round_avg", width="90px", align="center", decimal_places=1),
            Column(title=i18n_service.get_text("ui.tournament.rank"), field="round_rank", width="95px", align="center", decimal_places=0),
        ]
        total_stat_cols = [
            Column(title=i18n_service.get_text("score"), field="cum_score", width="95px", align="center", decimal_places=0),
            Column(title=i18n_service.get_text("average"), field="cum_avg", width="90px", align="center", decimal_places=1),
            Column(title=i18n_service.get_text("ui.tournament.rank"), field="cum_rank", width="90px", align="center", decimal_places=0),
        ]
        columns = [
            ColumnGroup(
                title=i18n_service.get_text("ui.tournament.stage"),
                frozen="left",
                style={"backgroundColor": get_theme_color("background")},
                columns=stage_info_cols,
            ),
            ColumnGroup(title=i18n_service.get_text("ui.tournament.games"), columns=game_score_cols),
            ColumnGroup(title=i18n_service.get_text("ui.tournament.stage_results"), columns=stage_stat_cols),
            ColumnGroup(title=i18n_service.get_text("ui.tournament.total_results"), columns=total_stat_cols),
        ]
        return TableData(
            columns=columns,
            data=rows,
            title=f"{player} - Tournament Progress",
            metadata={
                "heatmap_ranges": {
                    "game_score": {
                        "min": 130,
                        "max": 270,
                        "high_band_min": 271,
                        "high_band_max": 299,
                        "perfect_score": 300,
                    }
                }
            },
        )

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
            return {
                "labels": [],
                "avg_series": [],
                "position_series": [],
                "round_end_lines": [],
                "cut_lines_avg": [],
                "cut_lines_position": [],
                "participant_count": 0,
            }

        all_df = df.copy()
        all_df[Columns.score] = pd.to_numeric(all_df[Columns.score], errors="coerce").fillna(0)
        all_df[Columns.round_number] = pd.to_numeric(all_df[Columns.round_number], errors="coerce").astype("Int64")
        all_df[Columns.game_number] = pd.to_numeric(all_df[Columns.game_number], errors="coerce").astype("Int64")
        participant_count = (
            int(all_df[Columns.player_name].astype(str).str.strip().replace("", pd.NA).dropna().nunique())
            if Columns.player_name in all_df.columns
            else 0
        )

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
        round_cut_meta: Dict[int, Dict[str, Any]] = {}
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
                cut_basis = "overall_total"
                if "Cut Basis" in snap.columns:
                    basis_vals = [str(x).strip().lower() for x in snap["Cut Basis"].dropna().tolist() if str(x).strip()]
                    if basis_vals and basis_vals[0] in ("overall_total", "stage_total"):
                        cut_basis = basis_vals[0]

                cut_position: Optional[float] = None
                if Columns.cumulative_score in snap.columns and Columns.stage_rank in snap.columns:
                    score_col_name = (
                        "Overall Cumulative Score"
                        if cut_basis == "overall_total" and "Overall Cumulative Score" in snap.columns
                        else Columns.cumulative_score
                    )
                    cum = pd.to_numeric(snap[score_col_name], errors="coerce")
                    ranks = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
                    eq = ranks[cum.eq(cut_score)].dropna()
                    if not eq.empty:
                        cut_position = float(eq.max())
                    else:
                        ge = ranks[cum.ge(cut_score)].dropna()
                        if not ge.empty:
                            cut_position = float(ge.max())

                round_cut_meta[rn] = {
                    "cut_score": cut_score,
                    "cut_position": cut_position,
                    "cut_basis": cut_basis,
                }
        cfg_span = self._ko_qualifying_cut_span_config(season, tournament)
        if cfg_span:
            crank = int(cfg_span["rank"])
            for rn in range(int(cfg_span["first_round"]), int(cfg_span["through_round"]) + 1):
                entry = round_cut_meta.setdefault(rn, {})
                if entry.get("cut_position") is None:
                    entry["cut_position"] = float(crank)
                entry.setdefault("cut_basis", "overall_total")
        if cfg_span and not all_df.empty:
            for rn in range(int(cfg_span["first_round"]), int(cfg_span["through_round"]) + 1):
                entry = round_cut_meta.get(rn)
                if entry and entry.get("cut_score") is None and entry.get("cut_position") is not None:
                    cs = self._overall_cumulative_total_at_rank(all_df, rn, int(entry["cut_position"]))
                    if cs is not None:
                        entry["cut_score"] = float(cs)
        cut_rounds_sorted = sorted(round_cut_meta.keys())
        qualifying_cut_round = cut_rounds_sorted[0] if len(cut_rounds_sorted) >= 1 else None
        round2_cut_round = cut_rounds_sorted[1] if len(cut_rounds_sorted) >= 2 else None

        player_df = all_df[all_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())].copy()
        if player_df.empty:
            return {
                "labels": labels,
                "avg_series": [],
                "position_series": [],
                "round_end_lines": [],
                "cut_lines_avg": [],
                "cut_lines_position": [],
                "participant_count": participant_count,
            }

        avg_series: List[float] = []
        position_series: List[int] = []
        game_score_series: List[Optional[int]] = []
        tournament_leader_avg_series: List[Optional[float]] = []
        tournament_lowest_avg_series: List[Optional[float]] = []
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
            # For "lowest average" we ignore placeholder/non-played zero rows.
            prev_all_valid = prev_all[prev_all[Columns.score].gt(0)].copy()
            base_totals_valid = prev_all_valid.groupby(Columns.player_name, dropna=False)[Columns.score].sum().to_dict()
            base_games_valid = prev_all_valid.groupby(Columns.player_name, dropna=False)[Columns.score].count().to_dict()

            for g in range(length):
                game_score_series.append(int(player_game_scores[g]) if g in player_game_scores else None)
                # player cumulative
                if g in player_game_scores and int(player_game_scores[g]) > 0:
                    cum_player_score += int(player_game_scores[g])
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
                add_games = (
                    upto_round[upto_round[Columns.score].gt(0)]
                    .groupby(Columns.player_name, dropna=False)[Columns.score]
                    .count()
                    .to_dict()
                )
                games_played = {}
                for p_name in set(list(base_games.keys()) + list(add_games.keys())):
                    games_played[p_name] = int(base_games.get(p_name, 0)) + int(add_games.get(p_name, 0))
                if ranked:
                    leader_name = ranked[0][0]
                    leader_total = float(scores.get(leader_name, 0.0))
                    leader_games = max(int(games_played.get(leader_name, 0)), 1)
                    tournament_leader_avg_series.append(round(leader_total / leader_games, 2))
                    add_valid = upto_round[upto_round[Columns.score].gt(0)].copy()
                    add_totals_valid = add_valid.groupby(Columns.player_name, dropna=False)[Columns.score].sum().to_dict()
                    add_games_valid = add_valid.groupby(Columns.player_name, dropna=False)[Columns.score].count().to_dict()
                    avg_values = [
                        (float(base_totals_valid.get(p_name, 0.0)) + float(add_totals_valid.get(p_name, 0.0)))
                        / max(int(base_games_valid.get(p_name, 0)) + int(add_games_valid.get(p_name, 0)), 1)
                        for p_name in scores.keys()
                        if (int(base_games_valid.get(p_name, 0)) + int(add_games_valid.get(p_name, 0))) > 0
                    ]
                    tournament_lowest_avg_series.append(round(min(avg_values), 2) if avg_values else None)
                else:
                    tournament_leader_avg_series.append(None)
                    tournament_lowest_avg_series.append(None)

                # Dynamic cut-line averages follow configured cut basis.
                games_in_stage_so_far = g + 1
                total_games_upto_point = sum(l for rno, _, l in round_lengths if rno < rn) + games_in_stage_so_far
                cut_avg_game: Optional[float] = None
                cut_vals_game = pd.to_numeric(
                    round_all[round_all[Columns.game_number].eq(float(g))][Columns.cut_line]
                    if Columns.cut_line in round_all.columns
                    else pd.Series([], dtype=float),
                    errors="coerce",
                ).dropna()
                cut_score_game = float(cut_vals_game.iloc[0]) if not cut_vals_game.empty else None
                if cut_score_game is not None:
                    cut_basis = str((round_cut_meta.get(rn) or {}).get("cut_basis") or "overall_total").lower()
                    denom = total_games_upto_point if cut_basis == "overall_total" else games_in_stage_so_far
                    cut_avg_game = round(cut_score_game / max(denom, 1), 2)
                elif cfg_span and ranked:
                    fr = int(cfg_span["first_round"])
                    tr = int(cfg_span["through_round"])
                    crank = int(cfg_span["rank"])
                    if fr <= rn <= tr and len(ranked) >= crank:
                        cut_total = float(ranked[crank - 1][1])
                        cut_avg_game = round(cut_total / max(total_games_upto_point, 1), 2)

                for cut_rn in cut_rounds_sorted:
                    dynamic_cut_series[cut_rn].append(cut_avg_game if rn == cut_rn else None)

            x_cursor += length
            round_end_lines.append(x_cursor)
            # Horizontal cut-line references for stage-end snapshots.
            stage_games = max(length, 1)
            total_games_upto = sum(l for rno, _, l in round_lengths if rno <= rn)
            cut_meta = round_cut_meta.get(rn) or {}
            cut_score = cut_meta.get("cut_score")
            cut_basis = str(cut_meta.get("cut_basis") or "overall_total").lower()
            cut_pos = cut_meta.get("cut_position")
            if cut_score is not None:
                denom = total_games_upto if cut_basis == "overall_total" else stage_games
                cut_lines_avg.append(round(float(cut_score) / max(denom, 1), 2))
            if cut_pos is not None:
                cut_lines_position.append(int(cut_pos))

        # pad to total length (flat line after elimination)
        while len(avg_series) < total_games:
            avg_series.append(avg_series[-1] if avg_series else 0.0)
        while len(position_series) < total_games:
            position_series.append(position_series[-1] if position_series else 999)
        while len(tournament_leader_avg_series) < total_games:
            tournament_leader_avg_series.append(None)
        while len(tournament_lowest_avg_series) < total_games:
            tournament_lowest_avg_series.append(None)
        while len(game_score_series) < total_games:
            game_score_series.append(None)
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
            "game_score_series": game_score_series[:total_games],
            "tournament_leader_avg_series": tournament_leader_avg_series[:total_games],
            "tournament_lowest_avg_series": tournament_lowest_avg_series[:total_games],
            "round_end_lines": round_end_lines,
            "cut_lines_avg": cut_lines_avg,
            "cut_lines_position": cut_lines_position,
            "participant_count": participant_count,
            "cut_line_series": cut_line_series,
            "cut_lines_avg_dynamic": {
                f"round_{rn}": dynamic_cut_series[rn][:total_games] for rn in cut_rounds_sorted
            },
        }

    @staticmethod
    def _is_ko_bye_player(name: str) -> bool:
        n = str(name or "").strip().lower()
        if not n:
            return True
        if "(no show)" in n:
            return True
        if "nicht angetreten" in n:
            return True
        if n in {"bye", "freilos", "tbd"}:
            return True
        return False

    @staticmethod
    def _ko_bracket_side_display_name(name: str) -> str:
        """Legacy rows used plain 'Nicht angetreten'; bracket shows '(No show)' for clarity."""
        raw = str(name or "").strip()
        if not raw:
            return raw
        low = raw.lower()
        if "(no show)" in low:
            return raw
        if TournamentService._ko_norm_name(raw) == TournamentService._ko_norm_name("Nicht angetreten"):
            return "Nicht angetreten (No show)"
        return raw

    @staticmethod
    def _ko_norm_name(name: str) -> str:
        return str(name or "").strip().casefold()

    @staticmethod
    def _ko_bracket_match_keys(n_matches: int) -> List[str]:
        if n_matches <= 0:
            return []
        if n_matches == 1:
            return ["F"]
        if n_matches == 2:
            return ["SF1", "F"]
        if n_matches == 3:
            return ["SF1", "SF2", "F"]
        if n_matches == 4:
            return ["QF1", "QF2", "SF1", "F"]
        if n_matches == 5:
            return ["QF1", "QF2", "SF1", "SF2", "F"]
        return [f"M{i + 1}" for i in range(n_matches)]

    @staticmethod
    def _ko_match_winner_name(match: Dict[str, Any]) -> Optional[str]:
        w = match.get("winner")
        if w == "a":
            return str(match.get("side_a", {}).get("name", "") or "")
        if w == "b":
            return str(match.get("side_b", {}).get("name", "") or "")
        return None

    @staticmethod
    def _ko_strip_no_show_suffix(name: str) -> str:
        raw = str(name or "").strip()
        low = raw.lower()
        if low.endswith("(no show)"):
            return raw[: low.rfind("(")].strip()
        return raw

    @staticmethod
    def _ko_find_player_id_in_qf_matches(qf1: Dict[str, Any], qf2: Dict[str, Any], player_name: str) -> str:
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(player_name))
        if not target:
            return ""
        for qm in (qf1, qf2):
            for side in ("side_a", "side_b"):
                s = qm.get(side, {})
                nm = TournamentService._ko_strip_no_show_suffix(str(s.get("name", "") or ""))
                if TournamentService._ko_norm_name(nm) == target:
                    return str(s.get("id", "") or "")
        return ""

    @staticmethod
    def _ko_sf_bye_is_placeholder(name: str) -> bool:
        """True when the sheet only gave a generic absentee label (to be replaced by QF-winner inference)."""
        base = TournamentService._ko_strip_no_show_suffix(str(name or ""))
        if not base:
            return True
        return TournamentService._ko_norm_name(base) == TournamentService._ko_norm_name("Nicht angetreten")

    @staticmethod
    def _ko_sf_match_has_placeholder_bye(sm: Dict[str, Any]) -> bool:
        na = str(sm.get("side_a", {}).get("name", "") or "")
        nb = str(sm.get("side_b", {}).get("name", "") or "")
        return TournamentService._ko_sf_bye_is_placeholder(na) or TournamentService._ko_sf_bye_is_placeholder(nb)

    def _ko_apply_bracket_overrides_json(
        self, season: str, tournament: str, matches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Optional database/data/ko_bracket_overrides.json — keys "Season||Event Name",
        block.replace_sf_bye: { "SF1": { "name": "…", "id": "…" } } fills a generic bye slot.
        """
        path = Path(__file__).resolve().parents[2] / "database" / "data" / "ko_bracket_overrides.json"
        if not path.is_file():
            return matches
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return matches
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        if not isinstance(block, dict):
            return matches
        rep = block.get("replace_sf_bye") or {}
        if not isinstance(rep, dict):
            return matches
        by_key = {str(m.get("key", "")): m for m in matches}
        for sf_key, spec in rep.items():
            if not isinstance(spec, dict):
                continue
            sm = by_key.get(str(sf_key))
            if not sm:
                continue
            name = str(spec.get("name") or "").strip()
            pid = str(spec.get("id") or "").strip()
            if not name:
                continue
            display = name if "(no show)" in name.lower() else f"{name} (No show)"
            for side in ("side_a", "side_b"):
                sd = sm.get(side) or {}
                nm = str(sd.get("name") or "")
                if not self._ko_sf_bye_is_placeholder(nm):
                    continue
                sd = dict(sd)
                sd["name"] = display
                if pid:
                    sd["id"] = pid
                sm[side] = sd
                break
        return matches

    def _ko_resolve_sf_walkover_absent_from_qfs(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        SF walkover rows often list only 'Nicht angetreten'. Resolve the absent player as the QF winner
        who is not the SF opponent and is not playing in the other semifinal (e.g. Christian Rechenberg).
        """
        by_key = {str(m.get("key", "")): m for m in matches}
        qf1, qf2 = by_key.get("QF1"), by_key.get("QF2")
        if not qf1 or not qf2:
            return matches
        w1 = self._ko_match_winner_name(qf1)
        w2 = self._ko_match_winner_name(qf2)
        if not w1 or not w2:
            return matches
        w1b = self._ko_strip_no_show_suffix(w1)
        w2b = self._ko_strip_no_show_suffix(w2)

        def other_sf_real_norms(sf_key: str) -> set:
            other_key = "SF2" if sf_key == "SF1" else "SF1"
            om = by_key.get(other_key)
            if not om:
                return set()
            out: set = set()
            for side in ("side_a", "side_b"):
                nm = str(om.get(side, {}).get("name") or "")
                if not self._is_ko_bye_player(nm):
                    out.add(self._ko_norm_name(self._ko_strip_no_show_suffix(nm)))
            return out

        def apply(sf_key: str) -> None:
            sm = by_key.get(sf_key)
            if not sm or sm.get("inferred"):
                return
            if not (sm.get("walkover") or self._ko_sf_match_has_placeholder_bye(sm)):
                return
            sa, sb = sm["side_a"], sm["side_b"]
            na, nb = str(sa.get("name") or ""), str(sb.get("name") or "")
            bye_dict = None
            present_dict = None
            if self._ko_sf_bye_is_placeholder(na) and not self._ko_sf_bye_is_placeholder(nb):
                bye_dict, present_dict = sa, sb
            elif self._ko_sf_bye_is_placeholder(nb) and not self._ko_sf_bye_is_placeholder(na):
                bye_dict, present_dict = sb, sa
            else:
                return
            if not bye_dict or not present_dict:
                return
            present_clean = self._ko_strip_no_show_suffix(str(present_dict.get("name") or ""))
            if not present_clean:
                return
            np = self._ko_norm_name(present_clean)
            other_names = other_sf_real_norms(sf_key)

            candidates: List[str] = []
            for wb in (w1b, w2b):
                if not wb:
                    continue
                nwb = self._ko_norm_name(wb)
                if nwb == np:
                    continue
                if nwb in other_names:
                    continue
                candidates.append(wb)

            absent: Optional[str] = None
            if len(candidates) == 1:
                absent = candidates[0]
            elif len(candidates) == 2:
                if np == self._ko_norm_name(w1b):
                    absent = w2b
                elif np == self._ko_norm_name(w2b):
                    absent = w1b
                else:
                    narrowed = [c for c in candidates if self._ko_norm_name(c) not in other_names]
                    if len(narrowed) == 1:
                        absent = narrowed[0]

            if not absent:
                return
            display = f"{absent} (No show)"
            new_id = self._ko_find_player_id_in_qf_matches(qf1, qf2, absent)
            bye_dict["name"] = display
            if new_id:
                bye_dict["id"] = new_id

        apply("SF1")
        apply("SF2")
        return matches

    def _maybe_insert_inferred_sf2(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        When KO-Finale has only four match clusters (QF1, QF2, SF1, Final), the sheet often
        omits rows for SF2 walkover. Infer the finalist who did not play SF1 and insert SF2.
        """
        if len(matches) != 4:
            return matches
        sf1, fin = matches[2], matches[3]
        s1_names = {
            self._ko_norm_name(sf1["side_a"]["name"]),
            self._ko_norm_name(sf1["side_b"]["name"]),
        }
        fa = str(fin["side_a"]["name"] or "")
        fb = str(fin["side_b"]["name"] or "")
        adv: Optional[str] = None
        for cand in (fa, fb):
            if self._ko_norm_name(cand) not in s1_names:
                adv = cand
                break
        if not adv or self._is_ko_bye_player(adv):
            return matches
        wa_id = str(fin["side_a"].get("id", "") or "")
        wb_id = str(fin["side_b"].get("id", "") or "")
        adv_id = wa_id if self._ko_norm_name(adv) == self._ko_norm_name(fa) else wb_id
        syn: Dict[str, Any] = {
            "key": "SF2",
            "label": "SF2",
            "phase": "sf",
            "side_a": {"name": adv, "id": adv_id, "games_won": 2},
            "side_b": {"name": "Nicht angetreten (No show)", "id": "", "games_won": 0},
            "pin_games": [],
            "walkover": True,
            "winner": "a",
            "first_game_number": int(fin.get("first_game_number") or 0),
            "inferred": True,
            "scratch_total_a": 0,
            "scratch_total_b": 0,
            "scratch_series": False,
            "scratch_final": False,
        }
        return matches[:3] + [syn] + [fin]

    def _relabel_ko_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        keys = self._ko_bracket_match_keys(len(matches))
        for i, m in enumerate(matches):
            if i < len(keys):
                m["key"] = keys[i]
                mk = keys[i]
                m["label"] = "Finale" if mk == "F" else mk
                m["phase"] = self._ko_bracket_tree_phase(i, len(matches))
        return matches

    def _ko_finalist_path_meta(self, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rainbow lane indices + which bracket keys each finalist played in (for UI path)."""
        by_key = {str(m.get("key", "")): m for m in matches}
        f = by_key.get("F")
        if not f:
            return {
                "finalist_a": None,
                "finalist_b": None,
                "path_keys_a": [],
                "path_keys_b": [],
                "palette_index_a": 2,
                "palette_index_b": 8,
            }
        fa = str(f["side_a"]["name"] or "")
        fb = str(f["side_b"]["name"] or "")

        def path_for(name: str) -> List[str]:
            nc = self._ko_norm_name(self._ko_strip_no_show_suffix(name))
            if not nc or self._is_ko_bye_player(name):
                return ["F"]
            p: List[str] = ["F"]
            for sk in ("SF2", "SF1"):
                sm = by_key.get(sk)
                if not sm:
                    continue
                sides = {
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(sm["side_a"].get("name", "") or ""))),
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(sm["side_b"].get("name", "") or ""))),
                }
                if nc in sides:
                    p.insert(0, sk)
            for qk in ("QF2", "QF1"):
                qm = by_key.get(qk)
                if not qm:
                    continue
                sides = {
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(qm["side_a"].get("name", "") or ""))),
                    self._ko_norm_name(self._ko_strip_no_show_suffix(str(qm["side_b"].get("name", "") or ""))),
                }
                if nc in sides:
                    p.insert(0, qk)
            return p

        return {
            "finalist_a": fa,
            "finalist_b": fb,
            "path_keys_a": path_for(fa),
            "path_keys_b": path_for(fb),
            "palette_index_a": 2,
            "palette_index_b": 8,
        }

    @staticmethod
    def _ko_bracket_tree_phase(match_index: int, n_matches: int) -> str:
        if n_matches <= 1:
            return "final"
        last = n_matches - 1
        if match_index == last:
            return "final"
        if n_matches == 5:
            return "qf" if match_index < 2 else "sf"
        if n_matches == 3:
            return "sf"
        if n_matches == 2:
            return "sf"
        if n_matches == 4:
            return "qf" if match_index < 2 else "sf"
        return "early" if match_index < last - 1 else "late"

    def _ko_bracket_empty_meta(self) -> Dict[str, Any]:
        return {
            "matches": [],
            "placements": [],
            "finalist_a": None,
            "finalist_b": None,
            "path_keys_a": [],
            "path_keys_b": [],
            "palette_index_a": 2,
            "palette_index_b": 8,
            "ko_finale_series": KO_FINALE_SERIES_BO3,
        }

    def _load_tournament_ko_config(self) -> Dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "database" / "data" / "tournament_ko_config.json"
        if not path.is_file():
            return {}
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            return obj if isinstance(obj, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _ko_finale_series_mode(self, season: str, tournament: str) -> str:
        raw = self._load_tournament_ko_config()
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        if not isinstance(block, dict):
            return KO_FINALE_SERIES_BO3
        v = str(block.get("ko_finale_series", "") or "").strip().lower()
        if v in ("scratch_total_2g", "scratch_total", "scratch_2g", "2g_scratch"):
            return KO_FINALE_SERIES_SCRATCH_2G
        if v in ("bo3_pins", "bo3", "pins"):
            return KO_FINALE_SERIES_BO3
        return KO_FINALE_SERIES_BO3

    def _ko_bracket_empty_payload(self, season: str, tournament: str) -> Dict[str, Any]:
        return {**self._ko_bracket_empty_meta(), "ko_finale_series": self._ko_finale_series_mode(season, tournament)}

    def _ko_config_entry(self, season: str, tournament: str) -> Dict[str, Any]:
        raw = self._load_tournament_ko_config()
        key = f"{str(season).strip()}||{str(tournament).strip()}"
        block = raw.get(key)
        return block if isinstance(block, dict) else {}

    def _ko_qualifying_cut_pair(self, season: str, tournament: str) -> Optional[tuple[int, int]]:
        """
        Optional (round_number, cut_rank) from tournament_ko_config.json when the export has no Cut Line column.
        """
        block = self._ko_config_entry(season, tournament)
        rank = self._ko_optional_int(block.get("ko_qualifying_cut_rank"))
        if rank is None or rank < 1:
            return None
        rnd = self._ko_optional_int(block.get("ko_qualifying_cut_round"))
        if rnd is None or rnd < 1:
            rnd = 1
        return (rnd, rank)

    def _ko_qualifying_cut_span_config(self, season: str, tournament: str) -> Optional[Dict[str, int]]:
        """
        Qualifying cut rank applied from first_round through through_round (inclusive) for charts and shading
        when the CSV has no Cut Line. Optional ko_qualifying_cut_through_round (default: first round only).
        """
        block = self._ko_config_entry(season, tournament)
        rank = self._ko_optional_int(block.get("ko_qualifying_cut_rank"))
        if rank is None or rank < 1:
            return None
        first_r = self._ko_optional_int(block.get("ko_qualifying_cut_round"))
        if first_r is None or first_r < 1:
            first_r = 1
        through_r = self._ko_optional_int(block.get("ko_qualifying_cut_through_round"))
        if through_r is None:
            through_r = first_r
        through_r = max(int(first_r), int(through_r))
        return {"rank": int(rank), "first_round": int(first_r), "through_round": through_r}

    @staticmethod
    def _overall_cumulative_total_at_rank(all_df: pd.DataFrame, upto_round: int, rank_k: int) -> Optional[float]:
        """Total pins up to and including upto_round for the player at overall place rank_k (1-based)."""
        if all_df.empty or rank_k < 1 or Columns.round_number not in all_df.columns:
            return None
        scope = all_df[pd.to_numeric(all_df[Columns.round_number], errors="coerce").le(float(upto_round))].copy()
        if scope.empty or Columns.player_name not in scope.columns:
            return None
        scope[Columns.score] = pd.to_numeric(scope[Columns.score], errors="coerce").fillna(0)
        totals = scope.groupby(Columns.player_name, dropna=False)[Columns.score].sum()
        ranked = sorted(totals.items(), key=lambda t: (-float(t[1]), str(t[0])))
        if len(ranked) < rank_k:
            return None
        return float(ranked[rank_k - 1][1])

    def _ko_finale_round_number(self, df: pd.DataFrame) -> Optional[int]:
        if df.empty or Columns.round_number not in df.columns or Columns.round_name not in df.columns:
            return None
        ko_rows = df[df[Columns.round_name].astype(str).str.contains("KO", case=False, na=False)]
        if ko_rows.empty:
            return None
        return int(pd.to_numeric(ko_rows[Columns.round_number], errors="coerce").max())

    @staticmethod
    def _tournament_gender_key(tournament: str) -> Optional[str]:
        t = str(tournament or "")
        if "Frauen" in t:
            return "f"
        if "Männer" in t:
            return "m"
        return None

    def _resolved_cut_position_for_round(
        self, source_df: pd.DataFrame, target_round: int, season: str, tournament: str
    ) -> Optional[int]:
        """Prefer CSV-derived cut rank; fall back to ko_qualifying_cut_* config for the configured round."""

        def _from_csv() -> Optional[int]:
            if (
                source_df.empty
                or Columns.cut_line not in source_df.columns
                or Columns.round_number not in source_df.columns
                or Columns.game_number not in source_df.columns
            ):
                return None
            stage_df = source_df[pd.to_numeric(source_df[Columns.round_number], errors="coerce").eq(float(target_round))].copy()
            if stage_df.empty:
                return None
            max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
            snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
            if snap.empty:
                return None
            cut_vals = pd.to_numeric(snap[Columns.cut_line], errors="coerce").dropna()
            if cut_vals.empty:
                return None
            cut_score = float(cut_vals.iloc[0])

            if Columns.stage_rank in snap.columns and Columns.cumulative_score in snap.columns:
                score_col = Columns.cumulative_score
                if "Cut Basis" in snap.columns:
                    basis_vals = [str(x).strip().lower() for x in snap["Cut Basis"].dropna().tolist() if str(x).strip()]
                    if basis_vals and basis_vals[0] == "overall_total" and "Overall Cumulative Score" in snap.columns:
                        score_col = "Overall Cumulative Score"
                ranks = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
                scores = pd.to_numeric(snap[score_col], errors="coerce")
                exact = ranks[scores.eq(cut_score)].dropna()
                if not exact.empty:
                    return int(exact.max())
                ge = ranks[scores.ge(cut_score)].dropna()
                if not ge.empty:
                    return int(ge.max())
                return None

            if Columns.score in snap.columns and Columns.player_name in snap.columns:
                work = snap.copy()
                work[Columns.score] = pd.to_numeric(work[Columns.score], errors="coerce").fillna(0)
                ranked = work.groupby(Columns.player_name, dropna=False)[Columns.score].sum().sort_values(ascending=False)
                rank_series = ranked.rank(method="min", ascending=False)
                candidates = rank_series[ranked.ge(cut_score)]
                if not candidates.empty:
                    return int(candidates.max())
            return None

        base = _from_csv()
        if base is not None:
            return base
        span = self._ko_qualifying_cut_span_config(season, tournament)
        if span is not None and int(span["first_round"]) <= int(target_round) <= int(span["through_round"]):
            return int(span["rank"])
        return None

    def _ko_cut_line_card_from_config_rank(
        self, df: pd.DataFrame, season: str, tournament: str
    ) -> Optional[Dict[str, Any]]:
        """Build Cut Line summary card from qualifying-round snapshot at configured cut rank (no Cut Line column)."""
        cfg = self._ko_qualifying_cut_pair(season, tournament)
        if not cfg:
            return None
        crn, crank = cfg
        stage_df = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(crn))].copy()
        if stage_df.empty or Columns.game_number not in stage_df.columns:
            return None
        max_game = pd.to_numeric(stage_df[Columns.game_number], errors="coerce").max()
        snap = stage_df[pd.to_numeric(stage_df[Columns.game_number], errors="coerce").eq(max_game)].copy()
        if snap.empty or Columns.stage_rank not in snap.columns:
            return None
        ranks = pd.to_numeric(snap[Columns.stage_rank], errors="coerce")
        at = snap[ranks.eq(float(crank))].copy()
        if at.empty:
            return None
        if Columns.cumulative_score in at.columns:
            at = at.sort_values(by=Columns.cumulative_score, ascending=False)
        player = str(at.iloc[0].get(Columns.player_name, "") or "").strip()
        if not player:
            return None
        score_col = Columns.cumulative_score
        if "Overall Cumulative Score" in at.columns:
            score_col = "Overall Cumulative Score"
        cut_score = pd.to_numeric(at.iloc[0].get(score_col), errors="coerce")
        if pd.isna(cut_score):
            return None
        games_upto = 0
        if Columns.round_number in df.columns and Columns.game_number in df.columns:
            upto = df[pd.to_numeric(df[Columns.round_number], errors="coerce").le(float(crn))].copy()
            if not upto.empty:
                meta = (
                    upto[[Columns.round_number, Columns.game_number]]
                    .dropna(subset=[Columns.round_number, Columns.game_number])
                    .groupby(Columns.round_number, dropna=False)[Columns.game_number]
                    .max()
                    .reset_index()
                )
                if not meta.empty:
                    games_upto = int(meta[Columns.game_number].apply(lambda g: int(g) + 1).sum())
        cut_display = f"{int(cut_score)} pins (\u2300{(float(cut_score) / max(games_upto, 1)):.1f})" if games_upto > 0 else f"{int(cut_score)} pins"
        return {"title": "Cut Line", "value": player, "subtitle": cut_display, "type": "stat"}

    def _ko_placements_from_matches(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Standard 6-player tree: 1, 2, two 3rd (SF losers), two 5th (QF losers)."""

        def loser_of(m: Dict[str, Any]) -> str:
            w = m.get("winner")
            if w == "a":
                return str(m.get("side_b", {}).get("name", "") or "")
            if w == "b":
                return str(m.get("side_a", {}).get("name", "") or "")
            return ""

        def winner_name_id(m: Dict[str, Any]) -> tuple[str, str]:
            w = m.get("winner")
            if w == "a":
                return str(m.get("side_a", {}).get("name", "") or ""), str(m.get("side_a", {}).get("id", "") or "")
            if w == "b":
                return str(m.get("side_b", {}).get("name", "") or ""), str(m.get("side_b", {}).get("id", "") or "")
            return "", ""

        by_key = {str(m.get("key", "")): m for m in matches}
        out: List[Dict[str, Any]] = []
        fin = by_key.get("F")
        if not fin:
            return out

        wn, wid = winner_name_id(fin)
        ln = loser_of(fin)
        lid = str(fin.get("side_b", {}).get("id", "") or "") if fin.get("winner") == "a" else str(fin.get("side_a", {}).get("id", "") or "")

        if wn and not self._is_ko_bye_player(wn):
            out.append({"place": 1, "player": wn, "player_id": wid})
        if ln and not self._is_ko_bye_player(ln):
            out.append({"place": 2, "player": ln, "player_id": lid})

        for sk in ("SF1", "SF2"):
            sm = by_key.get(sk)
            if not sm:
                continue
            lost = loser_of(sm)
            if lost and not self._is_ko_bye_player(lost):
                pid = str(sm.get("side_b", {}).get("id", "") or "") if sm.get("winner") == "a" else str(sm.get("side_a", {}).get("id", "") or "")
                out.append({"place": 3, "player": lost, "player_id": pid})

        for qk in ("QF1", "QF2"):
            qm = by_key.get(qk)
            if not qm:
                continue
            lost = loser_of(qm)
            if lost and not self._is_ko_bye_player(lost):
                pid = str(qm.get("side_b", {}).get("id", "") or "") if qm.get("winner") == "a" else str(qm.get("side_a", {}).get("id", "") or "")
                out.append({"place": 5, "player": lost, "player_id": pid})

        return out

    def _ko_final_winner_card_subtitle(self, fin_match: Dict[str, Any]) -> str:
        if not fin_match:
            return ""
        w = fin_match.get("winner")
        if fin_match.get("scratch_series"):
            ta = int(fin_match.get("scratch_total_a") or 0)
            tb = int(fin_match.get("scratch_total_b") or 0)
            if w == "a":
                return f"{ta}:{tb} Pins"
            if w == "b":
                return f"{tb}:{ta} Pins"
            return f"{ta}:{tb} Pins"
        sa = fin_match.get("side_a", {})
        sb = fin_match.get("side_b", {})
        wa = int(sa.get("games_won") or 0)
        wb = int(sb.get("games_won") or 0)
        return f"{wa}:{wb} Spiele"

    @staticmethod
    def _table_data_keep_rows_min_place(table: TableData, min_rank: int) -> TableData:
        """Filter tournament total leaderboard rows where rank (# column) >= min_rank."""
        if min_rank <= 1 or not table.data:
            return table
        keep_idx = [i for i, row in enumerate(table.data) if row and int(row[0]) >= min_rank]
        if not keep_idx:
            return TableData(columns=[], data=[], title=table.title, config=dict(table.config or {}))
        new_data = [table.data[i] for i in keep_idx]
        new_rm = [table.row_metadata[i] for i in keep_idx] if table.row_metadata and len(table.row_metadata) == len(table.data) else []
        new_cm: Dict[str, Dict[str, Any]] = {}
        if table.cell_metadata:
            for new_i, old_i in enumerate(keep_idx):
                for k, v in table.cell_metadata.items():
                    parts = str(k).split(":")
                    if len(parts) == 2 and int(parts[0]) == old_i:
                        new_cm[f"{new_i}:{parts[1]}"] = v
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=dict(table.metadata or {}),
            default_sort=table.default_sort,
        )

    @staticmethod
    def _table_data_exclude_normalized_player_keys(table: TableData, exclude_keys: Set[str]) -> TableData:
        """Drop rows whose player name (col 1, after KO no-show normalization) is in exclude_keys."""
        if not exclude_keys or not table.data:
            return table
        keep_idx: List[int] = []
        for i, row in enumerate(table.data):
            if not row or len(row) < 2:
                continue
            pk = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(row[1])))
            if pk not in exclude_keys:
                keep_idx.append(i)
        if not keep_idx:
            return TableData(columns=[], data=[], title=table.title, config=dict(table.config or {}))
        new_data = [table.data[i] for i in keep_idx]
        new_rm = (
            [table.row_metadata[i] for i in keep_idx]
            if table.row_metadata and len(table.row_metadata) == len(table.data)
            else []
        )
        new_cm: Dict[str, Dict[str, Any]] = {}
        if table.cell_metadata:
            for new_i, old_i in enumerate(keep_idx):
                for k, v in table.cell_metadata.items():
                    parts = str(k).split(":")
                    if len(parts) == 2 and int(parts[0]) == old_i:
                        new_cm[f"{new_i}:{parts[1]}"] = v
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=dict(table.metadata or {}),
            default_sort=table.default_sort,
        )

    def _ko_placements_table_data(self, _season: str, tournament: str, df: pd.DataFrame, bracket: Dict[str, Any]) -> TableData:
        placements = list(bracket.get("placements") or [])
        include_club = self._has_any_club_value(df)
        club_map: Dict[str, str] = {}
        if include_club and Columns.player_name in df.columns and Columns.club in df.columns:
            for _, r in df[[Columns.player_name, Columns.club]].drop_duplicates().iterrows():
                nm = str(r[Columns.player_name]).strip()
                c = str(r.get(Columns.club, "") or "").strip()
                if nm:
                    club_map.setdefault(nm, c)

        base_cols = [
            Column(title=i18n_service.get_text("position"), field="place", width="70px", align="center", decimal_places=0),
            Column(title=i18n_service.get_text("player"), field="player", width="240px", align="left"),
        ]
        if include_club:
            base_cols.append(Column(title=i18n_service.get_text("ui.player.club"), field="club", width="200px", align="left"))
        grouped_columns = [
            ColumnGroup(
                title="",
                frozen="left",
                style={"backgroundColor": "#f8f9fa"},
                columns=base_cols,
            )
        ]
        rows: List[List[Any]] = []
        for p in placements:
            pname = str(p.get("player", "") or "").strip()
            row = [int(p.get("place", 0)), pname]
            if include_club:
                row.append(club_map.get(pname, ""))
            rows.append(row)

        ko_rn = self._ko_finale_round_number(df)
        stage_lbl = ""
        if ko_rn is not None and Columns.round_name in df.columns:
            meta = df[pd.to_numeric(df[Columns.round_number], errors="coerce").eq(float(ko_rn))]
            if not meta.empty:
                stage_lbl = str(meta[Columns.round_name].iloc[0])

        return TableData(
            columns=grouped_columns,
            data=rows,
            title=f"{tournament} — {stage_lbl}".strip(" —"),
            metadata={"kind": "ko_placements"},
            default_sort={"field": "place", "dir": "asc"},
            config={
                "stickyHeader": True,
                "striped": True,
                "hover": True,
                "responsive": True,
                "compact": False,
                "stripedColGroups": True,
            },
        )

    def _integrate_ko_into_total_leaderboard(
        self,
        table: TableData,
        bracket: Dict[str, Any],
        df: pd.DataFrame,
        season: str,
        tournament: str,
    ) -> TableData:
        """
        Gesamt leaderboard: show KO bracket places (1, 2, 3/3, 5/5) in the # column for finalists;
        everyone else keeps cumulative scratch rank. Sort: total average desc, then # asc.
        Cut-line cell shading still follows scratch rank, not KO place.
        """
        placements = list(bracket.get("placements") or [])
        if not placements or not table.data:
            return table

        ko_by_key: Dict[str, int] = {}
        for p in placements:
            nm = str(p.get("player", "") or "").strip()
            k = self._ko_norm_name(self._ko_strip_no_show_suffix(nm))
            if k:
                ko_by_key[k] = int(p.get("place", 0))

        cut_positions: List[int] = []
        if not df.empty and Columns.round_number in df.columns:
            work_rn = (
                df[[Columns.round_number]]
                .dropna(subset=[Columns.round_number])
                .drop_duplicates()
                .sort_values(by=Columns.round_number)
            )
            for _, rr in work_rn.iterrows():
                rn = int(rr[Columns.round_number])
                pos = self._resolved_cut_position_for_round(df, rn, season, tournament)
                if pos is not None and pos > 0 and pos not in cut_positions:
                    cut_positions.append(pos)
                if len(cut_positions) >= 3:
                    break
            cut_positions = sorted(cut_positions)

        augmented: List[Dict[str, Any]] = []
        for row_idx, row in enumerate(table.data):
            if not row or len(row) < 3:
                continue
            scratch_r = int(row[0])
            pname = str(row[1]).strip()
            pk = self._ko_norm_name(self._ko_strip_no_show_suffix(pname))
            display_pos = int(ko_by_key.get(pk, scratch_r))
            total_avg = float(row[-1])
            augmented.append(
                {
                    "row": list(row),
                    "display_pos": display_pos,
                    "scratch_r": scratch_r,
                    "total_avg": total_avg,
                    "old_idx": row_idx,
                }
            )

        if len(augmented) != len(table.data):
            return table

        augmented.sort(key=lambda x: (-x["total_avg"], x["display_pos"]))

        new_data: List[List[Any]] = []
        new_rm: List[Dict[str, Any]] = []
        new_cm: Dict[str, Dict[str, Any]] = {}
        has_rm = bool(table.row_metadata) and len(table.row_metadata) == len(table.data)

        for new_i, item in enumerate(augmented):
            r = item["row"]
            r[0] = item["display_pos"]
            new_data.append(r)

            scratch_r = item["scratch_r"]
            display_pos = int(item["display_pos"])
            style: Dict[str, Any] = {}
            if cut_positions and scratch_r > 0:
                if scratch_r <= cut_positions[0]:
                    style = {"backgroundColor": "#cfead6"}
                elif len(cut_positions) >= 2 and scratch_r <= cut_positions[1]:
                    style = {"backgroundColor": "#e0f1e4"}
                elif len(cut_positions) >= 3 and scratch_r <= cut_positions[2]:
                    style = {"backgroundColor": "#edf7ef"}
                # Bold # cell only when it shows place 1 (KO or scratch); not when scratch leader shows KO 2, etc.
                if display_pos == 1:
                    style["fontWeight"] = "700"
            if has_rm:
                new_rm.append(dict(table.row_metadata[item["old_idx"]]))
            else:
                new_rm.append({"styling": {}})
            if style:
                new_cm[f"{new_i}:0"] = style

        meta = dict(table.metadata or {})
        meta["initial_sort"] = [
            {"field": "total_avg", "dir": "desc"},
            {"field": "rank", "dir": "asc"},
        ]
        return TableData(
            columns=table.columns,
            data=new_data,
            title=table.title,
            row_metadata=new_rm,
            cell_metadata=new_cm,
            config=dict(table.config or {}),
            metadata=meta,
            default_sort={"field": "total_avg", "dir": "desc"},
        )

    @staticmethod
    def _ko_optional_int(val: Any) -> Optional[int]:
        x = pd.to_numeric(val, errors="coerce")
        if pd.isna(x):
            return None
        return int(x)

    def _ko_series_tiebreak_side(self, cluster: List[tuple], side_a: str, side_b: str) -> Optional[str]:
        """
        When counted pin games are tied (e.g. 1-1 in BO3 but G3 missing from export), derive the
        series winner from Stage Rank on the last game row (tournament placement), then pin totals.
        """
        if not cluster:
            return None
        _last_gn, lp0, lp1 = cluster[-1]

        def sr_for(name: str) -> Optional[int]:
            for px in (lp0, lp1):
                if self._ko_norm_name(px["name"]) == self._ko_norm_name(name):
                    return self._ko_optional_int(px.get("stage_rank"))
            return None

        ra = sr_for(side_a)
        rb = sr_for(side_b)
        if ra is not None and rb is not None and ra != rb:
            return "a" if ra < rb else "b"

        ta = tb = 0
        for _gn, q0, q1 in cluster:
            for q in (q0, q1):
                s = int(q.get("score") or 0)
                if self._ko_norm_name(q["name"]) == self._ko_norm_name(side_a):
                    ta += s
                elif self._ko_norm_name(q["name"]) == self._ko_norm_name(side_b):
                    tb += s
        if ta > tb:
            return "a"
        if tb > ta:
            return "b"
        return None

    def _build_ko_bracket_payload(self, season: str, tournament: str) -> Dict[str, Any]:
        """
        Best-effort KO tree from rows whose round name mentions KO (e.g. KO-Finale).
        Groups consecutive game numbers that share the same opponent pair (BO3 series).
        Walkovers use Club KO_WO and/or placeholder opponent 'Nicht angetreten'.
        """
        df = self._get_tournament_df(season=season, tournament=tournament)
        if df.empty or Columns.round_name not in df.columns or Columns.game_number not in df.columns:
            return self._ko_bracket_empty_payload(season, tournament)
        rn = df[Columns.round_name].astype(str).str.strip()
        mask = rn.str.contains("KO", case=False, na=False)
        ko_df = df.loc[mask].copy()
        if ko_df.empty:
            return self._ko_bracket_empty_payload(season, tournament)
        ko_df["_gn"] = pd.to_numeric(ko_df[Columns.game_number], errors="coerce")
        ko_df = ko_df.dropna(subset=["_gn"])
        if ko_df.empty:
            return self._ko_bracket_empty_payload(season, tournament)
        ko_df["_gn"] = ko_df["_gn"].astype(int)
        ko_df = ko_df.reset_index(drop=False).rename(columns={"index": "_row_order"})
        ko_df = ko_df.sort_values(by=["_gn", "_row_order"], kind="mergesort")
        finale_mode = self._ko_finale_series_mode(season, tournament)

        games_blocks: List[tuple] = []
        for gn, gdf in ko_df.groupby("_gn", sort=True):
            rows: List[Dict[str, Any]] = []
            for _, r in gdf.iterrows():
                club_v = str(r.get(Columns.club, "") or "").strip()
                sr = None
                if Columns.stage_rank in ko_df.columns:
                    sr = self._ko_optional_int(r.get(Columns.stage_rank))
                rows.append(
                    {
                        "name": str(r.get(Columns.player_name, "") or "").strip(),
                        "id": str(r.get(Columns.player_id, "") or "").strip(),
                        "score": int(pd.to_numeric(r.get(Columns.score), errors="coerce") or 0),
                        "club": club_v,
                        "stage_rank": sr,
                    }
                )
            if len(rows) < 2:
                continue
            if len(rows) > 2:
                by_name: Dict[str, Dict[str, Any]] = {}
                for row in rows:
                    key = row["name"].casefold()
                    prev = by_name.get(key)
                    if prev is None:
                        by_name[key] = dict(row)
                    else:
                        prev["score"] += row["score"]
                        if row.get("stage_rank") is not None:
                            prev["stage_rank"] = row["stage_rank"]
                rows = list(by_name.values())
                if len(rows) < 2:
                    continue
            p0, p1 = rows[0], rows[1]
            pair_key = tuple(sorted([p0["name"], p1["name"]], key=str.casefold))
            games_blocks.append((int(gn), pair_key, p0, p1))

        if not games_blocks:
            return self._ko_bracket_empty_payload(season, tournament)

        clusters: List[List[tuple]] = []
        cur: List[tuple] = []
        cur_key: Optional[tuple] = None
        for item in games_blocks:
            gn, key, p0, p1 = item
            if not cur:
                cur_key = key
                cur.append((gn, p0, p1))
                continue
            if key == cur_key:
                cur.append((gn, p0, p1))
            else:
                clusters.append(cur)
                cur_key = key
                cur = [(gn, p0, p1)]
        if cur:
            clusters.append(cur)

        n_matches = len(clusters)
        keys = self._ko_bracket_match_keys(n_matches)
        matches_out: List[Dict[str, Any]] = []
        for idx, cluster in enumerate(clusters):
            first_gn, fp0, fp1 = cluster[0]
            side_a = fp0["name"]
            side_b = fp1["name"]
            id_a = fp0["id"]
            id_b = fp1["id"]
            mk = keys[idx] if idx < len(keys) else f"M{idx + 1}"

            walkover = False
            pin_games: List[List[int]] = []
            wins_a = wins_b = 0
            scratch_total_a = scratch_total_b = 0
            for _gn, p0, p1 in cluster:
                c0 = str(p0.get("club") or "")
                c1 = str(p1.get("club") or "")
                if c0 == "KO_WO" or c1 == "KO_WO":
                    walkover = True
                if self._is_ko_bye_player(p0["name"]) or self._is_ko_bye_player(p1["name"]):
                    walkover = True

                if p0["name"] == side_a:
                    sa, sb = p0["score"], p1["score"]
                elif p0["name"] == side_b:
                    sa, sb = p1["score"], p0["score"]
                else:
                    sa, sb = p0["score"], p1["score"]

                if not walkover and (sa > 0 or sb > 0):
                    pin_games.append([sa, sb])
                    scratch_total_a += int(sa)
                    scratch_total_b += int(sb)
                    if sa > sb:
                        wins_a += 1
                    elif sb > sa:
                        wins_b += 1

            scratch_series_match = False
            scratch_final = False
            if walkover:
                if not self._is_ko_bye_player(side_a) and self._is_ko_bye_player(side_b):
                    wins_a, wins_b = 2, 0
                    winner = "a"
                elif self._is_ko_bye_player(side_a) and not self._is_ko_bye_player(side_b):
                    wins_a, wins_b = 0, 2
                    winner = "b"
                else:
                    wins_a, wins_b = 2, 0
                    winner = "a"
            elif finale_mode == KO_FINALE_SERIES_SCRATCH_2G and pin_games:
                # Entire KO bracket is scratch totals (e.g. women): winner = higher combined pins per match.
                scratch_series_match = True
                scratch_final = mk == "F"
                if scratch_total_a > scratch_total_b:
                    winner = "a"
                elif scratch_total_b > scratch_total_a:
                    winner = "b"
                else:
                    winner = None
                    tb_sc = self._ko_series_tiebreak_side(cluster, side_a, side_b)
                    if tb_sc == "a":
                        winner = "a"
                    elif tb_sc == "b":
                        winner = "b"
            else:
                if wins_a > wins_b:
                    winner = "a"
                elif wins_b > wins_a:
                    winner = "b"
                else:
                    winner = None
                    # BO3 at 1-1 when G3 is missing from CSV (not the final: some finals are 2-game scratch only).
                    if (
                        winner is None
                        and pin_games
                        and wins_a == wins_b
                        and wins_a >= 1
                        and mk != "F"
                    ):
                        tb_side = self._ko_series_tiebreak_side(cluster, side_a, side_b)
                        if tb_side == "a":
                            wins_a, wins_b, winner = 2, 1, "a"
                        elif tb_side == "b":
                            wins_a, wins_b, winner = 1, 2, "b"

            matches_out.append(
                {
                    "key": mk,
                    "label": mk.replace("F", "Finale") if mk == "F" else mk,
                    "phase": self._ko_bracket_tree_phase(idx, n_matches),
                    "side_a": {"name": self._ko_bracket_side_display_name(side_a), "id": id_a, "games_won": wins_a},
                    "side_b": {"name": self._ko_bracket_side_display_name(side_b), "id": id_b, "games_won": wins_b},
                    "pin_games": pin_games,
                    "walkover": walkover,
                    "winner": winner,
                    "first_game_number": first_gn,
                    "scratch_total_a": scratch_total_a,
                    "scratch_total_b": scratch_total_b,
                    "scratch_series": scratch_series_match,
                    "scratch_final": scratch_final,
                }
            )

        matches_out = self._maybe_insert_inferred_sf2(matches_out)
        matches_out = self._relabel_ko_matches(matches_out)
        matches_out = self._ko_resolve_sf_walkover_absent_from_qfs(matches_out)
        matches_out = self._ko_apply_bracket_overrides_json(season, tournament, matches_out)
        placements = self._ko_placements_from_matches(matches_out)
        meta = self._ko_finalist_path_meta(matches_out)
        return {"matches": matches_out, "placements": placements, **meta, "ko_finale_series": finale_mode}

    @staticmethod
    def _ko_player_in_ko_matches(bracket: Optional[Dict[str, Any]], player: str) -> bool:
        if not bracket or not bracket.get("matches"):
            return False
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(player or "")))
        if not target:
            return False
        for m in bracket["matches"]:
            for side in ("side_a", "side_b"):
                s = m.get(side, {})
                nm = TournamentService._ko_strip_no_show_suffix(str(s.get("name", "") or ""))
                if TournamentService._ko_norm_name(nm) == target:
                    return True
        return False

    @staticmethod
    def _ko_placement_for_player(bracket: Optional[Dict[str, Any]], player: str) -> Optional[int]:
        """Official KO standing (1=champion, 2=finalist, …) when bracket placements list the player."""
        if not bracket:
            return None
        target = TournamentService._ko_norm_name(TournamentService._ko_strip_no_show_suffix(str(player or "")))
        if not target:
            return None
        for p in bracket.get("placements") or []:
            nm = TournamentService._ko_strip_no_show_suffix(str(p.get("player", "") or ""))
            if TournamentService._ko_norm_name(nm) != target:
                continue
            pl = int(p.get("place", 0) or 0)
            return pl if pl > 0 else None
        return None

    def _ko_bracket_with_highlights(self, bracket: Dict[str, Any], player: str) -> Dict[str, Any]:
        if not bracket or not bracket.get("matches"):
            return bracket
        pnorm = self._ko_norm_name(self._ko_strip_no_show_suffix(str(player or "")))
        out_matches: List[Dict[str, Any]] = []
        for m in bracket["matches"]:
            mm = dict(m)
            sa = dict(m["side_a"])
            sb = dict(m["side_b"])
            sa["highlight"] = self._ko_norm_name(self._ko_strip_no_show_suffix(str(sa.get("name", "") or ""))) == pnorm
            sb["highlight"] = self._ko_norm_name(self._ko_strip_no_show_suffix(str(sb.get("name", "") or ""))) == pnorm
            mm["side_a"] = sa
            mm["side_b"] = sb
            out_matches.append(mm)
        return {**bracket, "matches": out_matches}

    def get_tournament_section(
        self,
        season: str,
        tournament: str,
        round_number: Optional[int] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        df = self._get_tournament_df(season=season, tournament=tournament)
        ko_bracket = self._build_ko_bracket_payload(season, tournament)
        ko_rn = self._ko_finale_round_number(df)
        is_ko_finale = (
            round_number is not None
            and ko_rn is not None
            and int(round_number) == int(ko_rn)
            and bool(ko_bracket.get("matches"))
        )
        lb_table = self.get_leaderboard_table(season, tournament, round_number)
        lb_scratch = lb_table
        placements = list(ko_bracket.get("placements") or [])
        if (
            round_number is None
            and ko_rn is not None
            and ko_bracket.get("matches")
            and placements
            and bool(lb_table.data)
        ):
            lb_table = self._integrate_ko_into_total_leaderboard(lb_table, ko_bracket, df, season, tournament)

        ko_excl = {
            self._ko_norm_name(self._ko_strip_no_show_suffix(str(p.get("player", "") or ""))) for p in placements
        }
        ko_excl.discard("")

        payload: Dict[str, Any] = {
            "cards": self.get_summary_cards(season, tournament, round_number=round_number, top_n=top_n).get("cards", []),
            "leaderboard": lb_table.to_dict(),
            "round_results": self.get_round_results_table(season, tournament, round_number).to_dict(),
            "rounds": self.get_rounds(season, tournament),
            "best_efforts": self.get_best_efforts(season, tournament, round_number=round_number, top_n=top_n),
            "ko_bracket": ko_bracket,
            "tournament_gender": self._tournament_gender_key(tournament),
            "is_ko_finale_round": is_ko_finale,
            "ko_finale_round_number": ko_rn,
        }
        cfg_cut = self._ko_qualifying_cut_pair(season, tournament)
        if (
            round_number is None
            and ko_rn is not None
            and cfg_cut
            and ko_bracket.get("matches")
            and bool(lb_scratch.data)
        ):
            _, crank = cfg_cut
            base_pq = self._table_data_keep_rows_min_place(lb_scratch, crank + 1)
            payload["leaderboard_post_qualification"] = self._table_data_exclude_normalized_player_keys(
                base_pq, ko_excl
            ).to_dict()
            payload["round_results_ko"] = self.get_round_results_table(season, tournament, ko_rn).to_dict()
        return payload

    def get_player_section(self, season: str, tournament: str, player: str) -> Dict[str, Any]:
        ko_bracket = self._build_ko_bracket_payload(season, tournament)
        ko_place = self._ko_placement_for_player(ko_bracket, player)

        progress = self.get_player_progress_series(season, tournament, player)
        pos_series = list(progress.get("position_series") or [])
        if ko_place is not None and pos_series:
            pos_series = pos_series[:]
            pos_series[-1] = ko_place
        progress_out = {**progress, "position_series": pos_series}

        player_df = self._get_tournament_df(season=season, tournament=tournament)
        player_df = player_df[player_df[Columns.player_name].astype(str).str.strip().eq(str(player).strip())]
        player_club = None
        if not player_df.empty and Columns.club in player_df.columns:
            club_vals = player_df[Columns.club].dropna().astype(str).tolist()
            player_club = club_vals[0] if club_vals else None
        avg_series = progress_out.get("avg_series", []) or []
        labels = progress_out.get("labels", []) or []

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

        if not self._ko_player_in_ko_matches(ko_bracket, player):
            ko_for_player = self._ko_bracket_empty_payload(season, tournament)
        else:
            ko_for_player = {**self._ko_bracket_with_highlights(ko_bracket, player), "focus_player": str(player).strip()}
        return {
            "player": player,
            "player_club": player_club,
            "round_table": self.get_player_round_table(season, tournament, player).to_dict(),
            "best_efforts": self.get_player_best_efforts(season, tournament, player),
            "progress_series": progress_out,
            "summary": {
                "average": avg_value,
                "best_position": best_position,
                "best_position_game": best_position_game,
                "final_position": final_position,
            },
            "ko_bracket": ko_for_player,
        }
