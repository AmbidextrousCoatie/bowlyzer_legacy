from flask import Flask, request
import os

from app.spa import register_spa

_API_PATH_PREFIXES = (
    "/league/",
    "/player/",
    "/team/",
    "/tournament/",
    "/switch-database",
    "/get-data-sources-info",
    "/home/",
    "/data-source-changed",
    "/set-season/",
)


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production")
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600
    app.config["SESSION_FILE_THRESHOLD"] = 500

    @app.before_request
    def ensure_fresh_data():
        """Reload DataManager from session on API requests only (skip static SPA assets)."""
        path = request.path
        if not any(path.startswith(prefix) for prefix in _API_PATH_PREFIXES):
            return
        try:
            from app.services.data_manager import DataManager

            data_manager = DataManager()
            data_manager.force_reload_from_session()
        except Exception as e:
            print(f"Warning: Could not ensure fresh data: {e}")

    from app.routes import main, player_routes, league_routes, team_routes, tournament_routes

    app.register_blueprint(team_routes.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(player_routes.bp)
    app.register_blueprint(league_routes.bp)
    app.register_blueprint(tournament_routes.bp)
    register_spa(app)

    try:
        from app.cache.league_response_cache import preload_league_revision_indexes

        preload_league_revision_indexes()
    except Exception as exc:
        print(f"Warning: could not preload league revision index: {exc}")

    try:
        from app.cache.cache_warmup import start_cache_warmup_background

        start_cache_warmup_background(app)
    except Exception as exc:
        print(f"Warning: could not start cache warmup: {exc}")

    return app
