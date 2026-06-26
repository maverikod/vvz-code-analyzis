"""
Harden POST /api/jsonrpc routes against body-validation races.

Under concurrent OpenAPI generation, FastAPI/Pydantic can occasionally validate
POST /api/jsonrpc against the wrong object (e.g. full app config), returning
HTTP 422 before handle_json_rpc runs. Parsing JSON from Request bypasses that
layer; handle_json_rpc keeps strict JSON-RPC validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Union, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from mcp_proxy_adapter.api.handlers import handle_batch_json_rpc, handle_json_rpc
from mcp_proxy_adapter.api.schemas import JsonRpcErrorResponse, JsonRpcSuccessResponse


def _remove_post_routes(app: FastAPI, paths: set[str]) -> None:
    """Return remove post routes."""
    kept: list[Any] = []
    for route in app.router.routes:
        if isinstance(route, APIRoute):
            if route.path in paths and "POST" in route.methods:
                continue
        kept.append(route)
    app.router.routes = kept


def patch_jsonrpc_routes_request_body(app: FastAPI) -> None:
    """Replace Pydantic body parsing on JSON-RPC routes with Request.json()."""
    _remove_post_routes(app, {"/api/jsonrpc", "/api/jsonrpc/batch"})

    @app.post(
        "/api/jsonrpc",
        response_model=Union[JsonRpcSuccessResponse, JsonRpcErrorResponse],
    )
    async def jsonrpc(http_request: Request) -> Any:
        """Return jsonrpc."""
        request_id = getattr(http_request.state, "request_id", None)
        try:
            body_raw = await http_request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"detail": "Invalid JSON body"}
            )
        if not isinstance(body_raw, dict):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": [
                        {
                            "type": "dict_type",
                            "loc": ["body"],
                            "msg": "Request body must be a JSON object",
                            "input": body_raw,
                        }
                    ]
                },
            )
        body_dict = cast(Dict[str, Any], body_raw)
        return await handle_json_rpc(body_dict, request_id, http_request)

    @app.post(
        "/api/jsonrpc/batch",
        response_model=List[Union[JsonRpcSuccessResponse, JsonRpcErrorResponse]],
    )
    async def jsonrpc_batch(http_request: Request) -> Any:
        """Return jsonrpc batch."""
        try:
            payload = await http_request.json()
        except Exception:
            return JSONResponse(
                status_code=400, content={"detail": "Invalid JSON body"}
            )
        if not isinstance(payload, list):
            return JSONResponse(
                status_code=422,
                content={"detail": "Batch body must be a JSON array"},
            )
        requests_list = [
            cast(Dict[str, Any], item) for item in payload if isinstance(item, dict)
        ]
        return await handle_batch_json_rpc(requests_list, http_request)
