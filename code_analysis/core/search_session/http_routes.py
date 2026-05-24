"""
FastAPI route registration for search job HTTP result access.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse

from code_analysis.core.search_session.http_access import (
    HttpAccessContext,
    handle_get_block,
    handle_get_index,
    handle_get_status,
)


def _json_response(status_code: int, payload: dict) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status_code)


def register_search_job_routes(app: Any, *, config_dir: Path) -> None:
    """Register non-streaming search job index, block, and status routes."""
    ctx = HttpAccessContext(config_dir=config_dir)

    def get_index(job_id: str) -> JSONResponse:
        status_code, payload = handle_get_index(ctx, job_id)
        return _json_response(status_code, payload)

    def get_block(job_id: str, position: int) -> JSONResponse:
        status_code, payload = handle_get_block(ctx, job_id, position)
        return _json_response(status_code, payload)

    def get_status(job_id: str) -> JSONResponse:
        status_code, payload = handle_get_status(ctx, job_id)
        return _json_response(status_code, payload)

    app.add_api_route(
        "/search/jobs/{job_id}/index",
        get_index,
        methods=["GET"],
        name="search_job_get_index",
    )
    app.add_api_route(
        "/search/jobs/{job_id}/blocks/{position}",
        get_block,
        methods=["GET"],
        name="search_job_get_block",
    )
    app.add_api_route(
        "/search/jobs/{job_id}/status",
        get_status,
        methods=["GET"],
        name="search_job_get_status",
    )
