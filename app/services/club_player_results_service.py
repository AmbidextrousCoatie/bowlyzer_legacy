"""Club-wide player results table (one row per player at the club)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from app.models.table_data import Column, ColumnGroup, TableData
from app.services.club_legends_service import (
    ClubLegendsService,
    _display_name,
    _player_keys,
)
from app.services.i18n_service import i18n_service
from app.services.league_service import ColumnWidths
from data_access.schema import Columns
from data_access.score_utils import mean_scores

# rainbowPastel[2] / [5] — matches frontend TEAM_COLOR_PALETTES (active vs alumni)
_CLUB_ACTIVE_ACCENT = "#8CBF8A"
_CLUB_INACTIVE_ACCENT = "#E86E56"


def _season_sort_key(label: str) -> tuple[int, str]:
    t = str(label or "").strip()
    m2 = re.match(r"^(\d{2})/(\d{2})$", t)
    if m2:
        return (int(m2.group(1)), t)
    m4 = re.match(r"^(\d{4})/(\d{4})$", t)
    if m4:
        return (int(m4.group(1)) % 100, t)
    return (-1, t)


def _latest_season(seasons: List[str]) -> str:
    return max(seasons, key=_season_sort_key)


def _empty_table(club: str = "") -> Dict[str, Any]:
    return {"club": club, "table": TableData(columns=[], data=[]).to_dict()}


class ClubPlayerResultsService(ClubLegendsService):
    def get_club_player_results_table(self, club: str) -> Dict[str, Any]:
        clubs = self._league_service.get_available_clubs()
        resolved = self._league_service.resolve_club_name(club, clubs)
        if not resolved:
            return _empty_table(str(club or "").strip())

        df = self._club_frame(resolved)
        if df.empty or Columns.player_name not in df.columns or Columns.season not in df.columns:
            return _empty_table(resolved)

        keys, names = _player_keys(df)
        work = df.copy()
        work["_pk"] = keys
        work["_pname"] = names
        work = work.loc[work["_pk"].astype(str).str.strip().ne("")]
        if work.empty:
            return _empty_table(resolved)

        def pid_for_group(g: pd.DataFrame) -> str:
            if Columns.player_id not in g.columns:
                return ""
            vals = g[Columns.player_id].fillna("").astype(str).str.strip()
            vals = vals[~vals.str.lower().isin({"", "nan", "none"})]
            return str(vals.iloc[0]) if len(vals) else ""

        alltime = (
            work.groupby("_pk", sort=False)
            .agg(
                average=(Columns.score, lambda s: mean_scores(s)),
                games=(Columns.score, "size"),
                membership_seasons=(Columns.season, "nunique"),
                _pname=("_pname", lambda s: _display_name(s)),
            )
            .reset_index()
        )

        season_stats = (
            work.groupby(["_pk", Columns.season], sort=False)
            .agg(
                average=(Columns.score, lambda s: mean_scores(s)),
                games=(Columns.score, "size"),
            )
            .reset_index()
        )
        season_stats = season_stats.sort_values(
            by=["_pk", "average", "games", Columns.season],
            ascending=[True, False, False, False],
        )
        best_by_player = season_stats.groupby("_pk", sort=False).first().reset_index()

        merged = alltime.merge(
            best_by_player[["_pk", Columns.season, "average"]],
            on="_pk",
            how="left",
            suffixes=("", "_best"),
        )

        merged = merged.sort_values(
            by=["average", "games", "_pname"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
        merged["rank"] = range(1, len(merged) + 1)

        unique_seasons = work[Columns.season].astype(str).str.strip().unique().tolist()
        latest_season = _latest_season(unique_seasons)
        active_pks = set(
            work.loc[
                work[Columns.season].astype(str).str.strip().eq(latest_season),
                "_pk",
            ]
            .astype(str)
            .tolist()
        )

        rows: List[Dict[str, Any]] = []
        row_metadata: List[Dict[str, Any]] = []
        for _, row in merged.iterrows():
            pk = row["_pk"]
            sub = work.loc[work["_pk"].eq(pk)]
            best_season = row.get(Columns.season)
            best_avg = row.get("average_best")
            club_active = str(pk) in active_pks
            rows.append(
                {
                    "rank": int(row["rank"]),
                    "player_name": str(row["_pname"]),
                    "player_id": pid_for_group(sub),
                    "average": round(float(row["average"]), 2) if pd.notna(row["average"]) else None,
                    "games": int(row["games"]),
                    "best_season": str(best_season) if pd.notna(best_season) else "",
                    "best_season_average": round(float(best_avg), 2) if pd.notna(best_avg) else None,
                    "membership_seasons": int(row["membership_seasons"]),
                    "club_active": club_active,
                }
            )
            row_metadata.append(
                {
                    "rowAccentColor": _CLUB_ACTIVE_ACCENT if club_active else _CLUB_INACTIVE_ACCENT,
                }
            )

        table = TableData(
            columns=[
                ColumnGroup(
                    title=i18n_service.get_text("ui.team.club_player_group"),
                    title_key="ui.team.club_player_group",
                    frozen="left",
                    columns=[
                        Column(
                            title=i18n_service.get_text("position"),
                            title_key="position",
                            field="rank",
                            width=ColumnWidths.position,
                            align="center",
                            decimal_places=0,
                        ),
                        Column(
                            title=i18n_service.get_text("player"),
                            title_key="player",
                            field="player_name",
                            width=ColumnWidths.player,
                            align="left",
                        ),
                        Column(
                            title="ID",
                            title_key="ui.team.player_id_col",
                            field="player_id",
                            width=ColumnWidths.misc,
                            align="left",
                        ),
                    ],
                ),
                ColumnGroup(
                    title=i18n_service.get_text("ui.team.club_alltime_group"),
                    title_key="ui.team.club_alltime_group",
                    columns=[
                        Column(
                            title=i18n_service.get_text("ui.player.average_col"),
                            title_key="ui.player.average_col",
                            field="average",
                            width=ColumnWidths.average,
                            align="center",
                            decimal_places=2,
                        ),
                        Column(
                            title=i18n_service.get_text("ui.player.games"),
                            title_key="ui.player.games",
                            field="games",
                            width=ColumnWidths.games,
                            align="center",
                            decimal_places=0,
                        ),
                    ],
                ),
                ColumnGroup(
                    title=i18n_service.get_text("ui.team.club_best_season_group"),
                    title_key="ui.team.club_best_season_group",
                    columns=[
                        Column(
                            title=i18n_service.get_text("season"),
                            title_key="season",
                            field="best_season",
                            width=ColumnWidths.season,
                            align="center",
                        ),
                        Column(
                            title=i18n_service.get_text("ui.player.average_col"),
                            title_key="ui.player.average_col",
                            field="best_season_average",
                            width=ColumnWidths.average,
                            align="center",
                            decimal_places=2,
                        ),
                    ],
                ),
                ColumnGroup(
                    title=i18n_service.get_text("ui.team.club_membership_group"),
                    title_key="ui.team.club_membership_group",
                    columns=[
                        Column(
                            title=i18n_service.get_text("ui.team.club_membership_years"),
                            title_key="ui.team.club_membership_years",
                            field="membership_seasons",
                            width=ColumnWidths.games,
                            align="center",
                            decimal_places=0,
                        ),
                    ],
                ),
            ],
            data=rows,
            row_metadata=row_metadata,
            default_sort={"field": "average", "dir": "desc"},
            metadata={"kind": "club_player_results", "latest_season": latest_season},
        )

        return {"club": resolved, "table": table.to_dict()}
