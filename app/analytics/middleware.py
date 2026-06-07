"""Flask hooks for anonymized API request logging."""

from __future__ import annotations

import time
from typing import Optional

from flask import Flask, g, request

from app.analytics.request_log import (
    analytics_enabled,
    append_request_log,
    build_log_record,
    daily_visitor_id,
    is_logged_api_path,
    resolve_client_ip,
)


def register_request_analytics(app: Flask) -> None:
    if not analytics_enabled():
        app.logger.info("Request analytics logging is disabled (ANALYTICS_ENABLED=0).")
        return

    @app.before_request
    def _analytics_start_timer() -> None:
        if not is_logged_api_path(request.path):
            return
        g._analytics_started_at = time.perf_counter()

    @app.after_request
    def _analytics_log_request(response):
        path = request.path
        if not is_logged_api_path(path):
            return response
        if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            return response

        started = getattr(g, "_analytics_started_at", None)
        duration_ms: Optional[float] = None
        if started is not None:
            duration_ms = (time.perf_counter() - started) * 1000.0

        client_ip = resolve_client_ip(
            request.remote_addr,
            request.headers.get("X-Forwarded-For"),
            request.headers.get("X-Real-IP"),
        )
        visitor_id = daily_visitor_id(client_ip)
        cache_status = response.headers.get("X-League-Cache")

        record = build_log_record(
            method=request.method,
            path=path,
            query=request.args,
            status_code=response.status_code,
            cache_status=cache_status,
            visitor_id=visitor_id,
            duration_ms=duration_ms,
        )
        append_request_log(record)
        return response
