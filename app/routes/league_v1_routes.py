import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from app.config.database_config import database_config
from app.services.league_service import LeagueService

bp = Blueprint("league_v1", __name__, url_prefix="/api/v1/league")


def get_league_service() -> LeagueService:
    database = request.args.get("database") or database_config.get_default_source()
    return LeagueService(database=database)


def _meta() -> Dict[str, str]:
    return {
        "requestId": str(uuid.uuid4()),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "version": "v1",
    }


def _ok(data: Any, status: int = 200):
    response = jsonify({"success": True, "data": data, "meta": _meta()})
    response.status_code = status
    return response


def _error(code: str, message: str, status: int, details: Dict[str, Any] | None = None):
    payload: Dict[str, Any] = {
        "success": False,
        "error": {"code": code, "message": message},
        "meta": _meta(),
    }
    if details:
        payload["error"]["details"] = details
    response = jsonify(payload)
    response.status_code = status
    return response


def _required_arg(name: str) -> Tuple[str | None, Any]:
    value = request.args.get(name)
    if value is None or value == "":
        return None, _error(
            "MISSING_REQUIRED_PARAM",
            f"Missing required parameter: {name}",
            400,
            {"parameter": name},
        )
    return value, None


def _required_int_arg(name: str) -> Tuple[int | None, Any]:
    raw, err = _required_arg(name)
    if err:
        return None, err
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, _error(
            "INVALID_PARAM",
            f"Invalid parameter: {name} must be an integer",
            400,
            {"parameter": name},
        )
    if value < 1:
        return None, _error(
            "INVALID_PARAM",
            f"Invalid parameter: {name} must be >= 1",
            400,
            {"parameter": name},
        )
    return value, None


def _etag_for(items: List[Dict[str, Any]]) -> str:
    serialized = json.dumps(items, sort_keys=True, ensure_ascii=True)
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


def _with_selector_cache(response, items: List[Dict[str, Any]]):
    response.set_etag(_etag_for(items))
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


def _normalize_options(raw_items: List[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in raw_items or []:
        if isinstance(raw, dict):
            value = raw.get("value") or raw.get("short_name") or raw.get("name")
            label = raw.get("label") or raw.get("long_name") or value
            if value is None:
                continue
            meta = {k: v for k, v in raw.items() if k not in {"value", "label", "short_name", "long_name", "name"}}
            option: Dict[str, Any] = {"value": str(value), "label": str(label)}
            if meta:
                option["meta"] = meta
            items.append(option)
        else:
            items.append({"value": str(raw), "label": str(raw)})
    return items


def _flatten_table_fields(columns: List[Dict[str, Any]]) -> List[str]:
    fields: List[str] = []
    for group in columns or []:
        for col in group.get("columns", []):
            field = col.get("field")
            if field:
                fields.append(field)
    return fields


def _tabledata_to_v1(table_data: Dict[str, Any]) -> Dict[str, Any]:
    columns = table_data.get("columns", [])
    fields = _flatten_table_fields(columns)
    legacy_rows = table_data.get("data", [])
    rows: List[Dict[str, Any]] = []

    if legacy_rows and isinstance(legacy_rows[0], dict):
        rows = legacy_rows
    else:
        for row in legacy_rows:
            if isinstance(row, list):
                mapped = {field: row[idx] if idx < len(row) else None for idx, field in enumerate(fields)}
                rows.append(mapped)

    config = table_data.get("config", {}) or {}
    if table_data.get("default_sort") and "defaultSort" not in config:
        config["defaultSort"] = table_data["default_sort"]

    payload: Dict[str, Any] = {
        "title": table_data.get("title"),
        "description": table_data.get("description"),
        "columns": columns,
        "rows": rows,
        "config": config,
        "metadata": table_data.get("metadata", {}) or {},
    }
    rm = table_data.get("row_metadata")
    if rm is not None:
        payload["row_metadata"] = rm
    cm = table_data.get("cell_metadata")
    if cm is not None:
        payload["cell_metadata"] = cm
    return payload


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _series_to_chart_v1(series_data: Dict[str, Any]) -> Dict[str, Any]:
    sorted_names = series_data.get("sorted_by_total") or list((series_data.get("data_accumulated") or {}).keys())
    accumulated = series_data.get("data_accumulated", {})
    x_categories = list(range(1, int(series_data.get("length", 0)) + 1))

    series = []
    for name in sorted_names:
        series.append(
            {
                "id": _slugify(name),
                "name": name,
                "data": accumulated.get(name, []),
            }
        )

    return {
        "chartType": "line",
        "title": series_data.get("name"),
        "xAxis": {
            "label": series_data.get("label_x_axis", "Week"),
            "categories": x_categories,
        },
        "yAxis": {
            "label": series_data.get("label_y_axis", "Value"),
        },
        "series": series,
        "metadata": {
            "query": series_data.get("query_params", {}),
            "totals": series_data.get("total", {}),
            "averages": series_data.get("average", {}),
            "counts": series_data.get("counts", {}),
        },
    }


@bp.route("/options/leagues")
def get_leagues_options():
    try:
        season = request.args.get("season")
        service = get_league_service()
        leagues = service.get_leagues(season=season)
        items = _normalize_options(leagues)
        response = _ok({"items": items})
        return _with_selector_cache(response, items)
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/options/seasons")
def get_seasons_options():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        seasons = service.get_seasons(league_name=league, team_name=request.args.get("team"))
        items = _normalize_options(seasons)
        response = _ok({"items": items})
        return _with_selector_cache(response, items)
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/options/weeks")
def get_weeks_options():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    try:
        service = get_league_service()
        weeks = service.get_weeks(league_name=league, season=season)
        items = _normalize_options(weeks)
        response = _ok({"items": items})
        return _with_selector_cache(response, items)
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/options/teams")
def get_teams_options():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    try:
        service = get_league_service()
        teams = service.get_teams_in_league_season(league, season)
        items = _normalize_options(teams)
        response = _ok({"items": items})
        return _with_selector_cache(response, items)
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/season/standings")
def get_season_standings():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_league_history_table_data(league_name=league, season=season).to_dict()
        return _ok(_tabledata_to_v1(table_data))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/season/team-points")
def get_season_team_points():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week = request.args.get("week")
    if week:
        _, err = _required_int_arg("week")
        if err:
            return err
    try:
        service = get_league_service()
        points = service.get_team_points_simple(league_name=league, season=season)
        return _ok(_series_to_chart_v1(points))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/season/team-positions")
def get_season_team_positions():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week = request.args.get("week")
    if week:
        _, err = _required_int_arg("week")
        if err:
            return err
    try:
        service = get_league_service()
        positions = service.get_team_positions_simple(league_name=league, season=season)
        return _ok(_series_to_chart_v1(positions))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/season/team-averages")
def get_season_team_averages():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week = request.args.get("week")
    if week:
        _, err = _required_int_arg("week")
        if err:
            return err
    try:
        service = get_league_service()
        averages = service.get_team_averages_simple(league_name=league, season=season)
        return _ok(_series_to_chart_v1(averages))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/matchday/standings")
def get_matchday_standings():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week, err = _required_int_arg("week")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_league_week_table_simple(season=season, league=league, week=week)
        if not table_data:
            return _error(
                "NOT_FOUND",
                "No standings found for the selected filters",
                404,
                {"league": league, "season": season, "week": week},
            )
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/matchday/honor-scores")
def get_matchday_honor_scores():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week, err = _required_int_arg("week")
    if err:
        return err
    try:
        service = get_league_service()
        honor_scores = service.get_honor_scores(
            league=league,
            season=season,
            week=week,
            number_of_individual_scores=3,
            number_of_team_scores=3,
            number_of_individual_averages=3,
            number_of_team_averages=3,
        )
        return _ok({"cards": honor_scores})
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/team-week/classic")
def get_team_week_classic():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week, err = _required_int_arg("week")
    if err:
        return err
    team, err = _required_arg("team")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_team_week_details_table_data(
            league=league,
            season=season,
            team=team,
            week=week,
        )
        if not table_data:
            return _error(
                "NOT_FOUND",
                "No team-week classic data found for selected filters",
                404,
                {"league": league, "season": season, "week": week, "team": team},
            )
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/team-week/individual-scores")
def get_team_week_individual_scores():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week, err = _required_int_arg("week")
    if err:
        return err
    team, err = _required_arg("team")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_team_individual_scores_table(
            league=league,
            season=season,
            team=team,
            week=week,
        )
        if not table_data:
            return _error(
                "NOT_FOUND",
                "No team-week individual scores data found for selected filters",
                404,
                {"league": league, "season": season, "week": week, "team": team},
            )
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/team-week/head-to-head")
def get_team_week_head_to_head():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week, err = _required_int_arg("week")
    if err:
        return err
    team, err = _required_arg("team")
    if err:
        return err
    view_mode = request.args.get("viewMode", "own_team")
    try:
        service = get_league_service()
        table_data = service.get_team_week_head_to_head_table_data(
            league=league,
            season=season,
            team=team,
            week=week,
            view_mode=view_mode,
        )
        if not table_data:
            return _error(
                "NOT_FOUND",
                "No team-week head-to-head data found for selected filters",
                404,
                {"league": league, "season": season, "week": week, "team": team, "viewMode": view_mode},
            )
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/aggregation/averages-history")
def get_aggregation_averages_history():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        data = service.get_league_averages_history(league=league, debug=False)
        return _ok(_series_to_chart_v1(data))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/aggregation/points-to-win-history")
def get_aggregation_points_to_win_history():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        data = service.get_points_to_win_history(league=league, debug=False)
        return _ok(_series_to_chart_v1(data))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/aggregation/top-team-performances")
def get_aggregation_top_team_performances():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_top_team_performances(league=league)
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/aggregation/top-individual-performances")
def get_aggregation_top_individual_performances():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_top_individual_performances(league=league)
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/aggregation/record-games")
def get_aggregation_record_games():
    league, err = _required_arg("league")
    if err:
        return err
    try:
        service = get_league_service()
        table_data = service.get_record_games(league=league)
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)


@bp.route("/season/team-vs-team")
def get_season_team_vs_team():
    league, err = _required_arg("league")
    if err:
        return err
    season, err = _required_arg("season")
    if err:
        return err
    week_raw = request.args.get("week")
    week = None
    if week_raw:
        week, err = _required_int_arg("week")
        if err:
            return err
    try:
        service = get_league_service()
        table_data = service.get_team_vs_team_comparison_table(league, season, week)
        return _ok(_tabledata_to_v1(table_data.to_dict()))
    except Exception as exc:
        return _error("INTERNAL_ERROR", str(exc), 500)
