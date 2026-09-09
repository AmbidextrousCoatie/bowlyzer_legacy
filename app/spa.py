"""Serve the React production build and map legacy Jinja URLs to React routes."""

from __future__ import annotations

import os

from flask import Flask, jsonify, redirect, request, send_from_directory

LEGACY_PATH_MAP: dict[str, str] = {
    "/league/stats": "/liga",
    "/league/club_matrix": "/diagnose/club-matrix",
    "/league/week_matrix": "/diagnose/liga-wochen",
    "/team/stats": "/club",
    "/mannschaft": "/club",
    "/player/stats": "/spieler",
    "/tournament/stats": "/turnier",
}

_API_PATH_PREFIXES = (
    "/league/",
    "/player/",
    "/team/",
    "/tournament/",
    "/pipeline/",
    "/switch-database",
    "/get-data-sources-info",
    "/home/",
    "/data-source-changed",
    "/set-season/",
    "/debug-session",
    "/test-database-param",
    "/test-filter-endpoints",
)


def spa_dir() -> str:
    env = os.environ.get("BOWLYZER_SPA_DIR")
    if env:
        return env
    root = os.environ.get(
        "BOWLYZER_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    )
    return os.path.join(root, "frontend", "dist")


def _redirect_preserving_query(target: str):
    qs = request.query_string.decode()
    if qs:
        joiner = "&" if "?" in target else "?"
        return redirect(f"{target}{joiner}{qs}", code=301)
    return redirect(target, code=301)


def register_spa(app: Flask) -> None:
    dist = spa_dir()
    if not os.path.isdir(dist):
        app.logger.warning(
            "SPA build not found at %s — run `cd frontend && pnpm build` or set BOWLYZER_SPA_DIR",
            dist,
        )

    @app.get("/overall/<path:subpath>")
    def legacy_overall_redirect(subpath: str):
        return _redirect_preserving_query("/liga")

    for old_path, new_path in LEGACY_PATH_MAP.items():
        endpoint = "legacy_redirect_" + old_path.strip("/").replace("/", "_")

        def _view(dest: str = new_path):
            return _redirect_preserving_query(dest)

        app.add_url_rule(old_path, endpoint=endpoint, view_func=_view, methods=["GET"])

    @app.route("/", defaults={"path": ""}, methods=["GET"])
    @app.route("/<path:path>", methods=["GET"])
    def spa_fallback(path: str):
        if any(request.path.startswith(prefix) for prefix in _API_PATH_PREFIXES):
            app.logger.warning(
                "API path hit SPA fallback (no Flask route matched): %s — "
                "redeploy bowlyzer:release or check nginx proxy_pass to :8080",
                request.path,
            )
            return jsonify({"error": "Not found", "path": request.path}), 404

        if not os.path.isdir(dist):
            return (
                jsonify(
                    {
                        "error": "SPA not built",
                        "hint": "cd frontend && pnpm build",
                    }
                ),
                503,
            )

        if path:
            candidate = os.path.join(dist, path)
            if os.path.isfile(candidate):
                return send_from_directory(dist, path)

        index = os.path.join(dist, "index.html")
        if os.path.isfile(index):
            return send_from_directory(dist, "index.html")
        return jsonify({"error": "index.html missing in SPA build"}), 503
