"""
Live MCP-style integration for project_cross_search queue and sync budgets.

Requires a running code-analysis-server with project 8772a086 in list_projects.
Skip when server is down: pytest -m 'not live_server'.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    init_global_queue_manager,
    shutdown_global_queue_manager,
)

import code_analysis.hooks  # noqa: F401
from code_analysis.core.command_execution_job_patch import (
    ensure_shared_database_for_current_process,
)

pytestmark = pytest.mark.live_server

PROJECT_ID = "8772a086-688d-4198-a0c4-f03817cc0e6c"
_XPATH_GREP = ["xpath"]
_QUERY = "XPath selector path expression tree node query"


def _live_enabled() -> bool:
    """Return live enabled."""
    return os.environ.get("RUN_PROJECT_CROSS_SEARCH_LIVE", "").lower() in (
        "1",
        "true",
        "yes",
    )


async def _run(command_name: str, **params: Any) -> Dict[str, Any]:
    """Return run."""
    cmd_cls = registry.get_command(command_name)
    result_obj = await cmd_cls.run(**params)
    return result_obj.to_dict()


def _payload(res: Dict[str, Any]) -> Dict[str, Any]:
    """Return payload."""
    data = res.get("data")
    return data if isinstance(data, dict) else {}


def _extract_job_id(res: Dict[str, Any]) -> Optional[str]:
    """Return extract job id."""
    for key in ("job_id", "queue_job_id"):
        val = res.get(key)
        if isinstance(val, str) and val:
            return val
    data = res.get("data")
    if isinstance(data, dict):
        for key in ("job_id", "queue_job_id"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


async def _poll_job(job_id: str, timeout: float = 120.0) -> Dict[str, Any]:
    """Return poll job."""
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        status_res = await _run("queue_get_job_status", job_id=job_id)
        assert status_res.get("success") is True
        last = status_res["data"]
        if last.get("status") in {"completed", "failed", "stopped", "deleted"}:
            return last
        await asyncio.sleep(0.25)
    return last


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _queue_manager_lifecycle():
    """Return queue manager lifecycle."""
    if not _live_enabled():
        pytest.skip("Set RUN_PROJECT_CROSS_SEARCH_LIVE=1 to run live server tests")
    hooks.execute_custom_commands_hooks(registry)
    await shutdown_global_queue_manager()
    await init_global_queue_manager(
        in_memory=True,
        max_concurrent_jobs=2,
        completed_job_retention_seconds=3600,
    )
    try:
        ensure_shared_database_for_current_process()
        health = await _run("health")
        if not health.get("success"):
            pytest.skip("code-analysis-server health check failed")
        yield
    finally:
        await shutdown_global_queue_manager()


@pytest.mark.asyncio
async def test_live_sync_bounded_project_cross_search() -> None:
    """Sync grep-only call returns structured result within budget (no transport failure)."""
    res = await _run(
        "project_cross_search",
        project_id=PROJECT_ID,
        query=_QUERY,
        grep_patterns=_XPATH_GREP,
        file_pattern="code_analysis",
        semantic_limit=0,
        fulltext_limit=0,
        grep_limit=30,
        limit=20,
        grep_sync_max_wall_seconds=30,
    )
    assert res.get("success") is True, res
    data = _payload(res)
    assert data.get("success") is True
    assert data.get("execution_mode") in ("sync", "queued_recommended")
    assert "grep_budget" in data
    assert "warnings" in data


@pytest.mark.asyncio
async def test_live_queued_project_cross_search_command_result() -> None:
    """Queued job: poll until command result.success is available."""
    job_id = f"live_pcs_{int(time.time() * 1000)}"
    submit = await _run(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={
            "command": "project_cross_search",
            "params": {
                "project_id": PROJECT_ID,
                "query": _QUERY,
                "grep_patterns": _XPATH_GREP,
                "file_pattern": "code_analysis",
                "semantic_limit": 0,
                "fulltext_limit": 0,
                "grep_limit": 50,
                "limit": 20,
            },
        },
    )
    assert submit.get("success") is True, submit
    started = await _run("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    terminal = await _poll_job(job_id, timeout=180.0)
    assert terminal.get("status") == "completed", terminal
    assert terminal.get("command_name") == "project_cross_search"
    assert terminal.get("command_success") is True
    assert terminal.get("inner_success") is True

    status = await _run("queue_get_job_status", job_id=job_id)
    assert status.get("success") is True
    result_block = (status.get("data") or {}).get("result") or {}
    command_block = result_block.get("command") or result_block
    cmd_payload = command_block.get("result") or command_block
    assert cmd_payload.get("success") is True, status
    data = cmd_payload.get("data") or cmd_payload
    assert data.get("execution_mode") == "queued"
    assert data.get("grep_budget", {}).get("limits", {}).get("mode") == "full"
