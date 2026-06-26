"""Regression: concurrent OpenAPI + JSON-RPC must not break /api/jsonrpc."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

import code_analysis.hooks  # noqa: F401 — register commands
from code_analysis.core.storage_paths import load_raw_config
from code_analysis.main_app_factory import create_app_with_events
from code_analysis.openapi_mcp_proxy_compat import invalidate_openapi_cache


@pytest.fixture
def app():
    """Return app."""
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    app_config = load_raw_config(config_path)
    application = create_app_with_events(app_config, config_path, worker_manager=None)
    yield application
    invalidate_openapi_cache(application)


def test_concurrent_openapi_and_jsonrpc(app) -> None:
    """Verify test concurrent openapi and jsonrpc."""

    async def _run() -> None:
        """Return run."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:

            async def rpc() -> int:
                """Return rpc."""
                response = await client.post(
                    "/api/jsonrpc",
                    json={"jsonrpc": "2.0", "method": "help", "params": {}, "id": 1},
                    timeout=60,
                )
                return response.status_code

            async def openapi() -> int:
                """Return openapi."""
                response = await client.get("/openapi.json", timeout=180)
                return response.status_code

            assert await rpc() == 200

            for _round in range(3):
                tasks: list[asyncio.Task[int]] = []
                for _ in range(20):
                    tasks.append(asyncio.create_task(openapi()))
                    tasks.append(asyncio.create_task(rpc()))
                results = await asyncio.gather(*tasks)
                assert all(code == 200 for code in results), results

            assert await rpc() == 200

    asyncio.run(_run())


def test_openapi_schema_cached_per_app(app) -> None:
    """Verify test openapi schema cached per app."""
    first = app.openapi()
    second = app.openapi()
    assert first == second
    assert first is not second
