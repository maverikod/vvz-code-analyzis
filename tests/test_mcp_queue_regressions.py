"""
MCP-level queue regression coverage using real registered commands.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest
import pytest_asyncio
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    init_global_queue_manager,
    shutdown_global_queue_manager,
)

import code_analysis.hooks  # noqa: F401

PROJECT_ID = "900fe94a-1d93-41be-bba1-0ebddbd1e5d1"


async def _run_command(command_name: str, **params: Any) -> Dict[str, Any]:
    cmd_cls = registry.get_command(command_name)
    result_obj = await cmd_cls.run(**params)
    return result_obj.to_dict()


def _job_id(prefix: str) -> str:
    return f"qa_queuefix_{int(time.time() * 1000)}_{prefix}"


async def _poll_terminal_status(job_id: str, timeout: float = 30.0) -> Dict[str, Any]:
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    while time.time() < deadline:
        status_res = await _run_command("queue_get_job_status", job_id=job_id)
        assert status_res.get("success") is True
        last = status_res["data"]
        if last.get("status") in {"completed", "failed", "stopped", "deleted"}:
            return last
        await asyncio.sleep(0.2)
    return last


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _queue_manager_lifecycle():
    hooks.execute_custom_commands_hooks(registry)
    await shutdown_global_queue_manager()
    await init_global_queue_manager(
        in_memory=True,
        max_concurrent_jobs=2,
        completed_job_retention_seconds=3600,
    )
    try:
        yield
    finally:
        await shutdown_global_queue_manager()


@pytest.mark.asyncio
async def test_health_and_queue_health_include_dependency_versions() -> None:
    health = await _run_command("health")
    assert health.get("success") is True
    deps = health["data"]["components"]["queue_dependencies"]
    assert "versions" in deps
    assert "code_analysis_server" in deps["versions"]
    assert "mcp_proxy_adapter" in deps["versions"]
    assert "queuemgr" in deps["versions"]

    queue_health = await _run_command("queue_health")
    assert queue_health.get("success") is True
    qh_data = queue_health["data"]
    assert "dependency_versions" in qh_data
    assert "dependency_compatibility" in qh_data


@pytest.mark.asyncio
async def test_regression_a_command_execution_health_completed_diagnostics() -> None:
    job_id = _job_id("health")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={"command": "health", "params": {}},
    )
    assert added.get("success") is True

    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert final.get("status") == "completed"
    assert final.get("job_success") is True
    assert final.get("command_execution") is True
    assert final.get("command_name") == "health"
    assert final.get("command_success") is True
    assert final.get("inner_success") is True
    assert final.get("completed_with_error") is False

    completed = await _run_command(
        "queue_list_jobs", status_filter="completed", limit=200
    )
    assert completed.get("success") is True
    jobs = completed["data"]["jobs"]
    assert any(j.get("job_id") == job_id for j in jobs)


@pytest.mark.asyncio
async def test_regression_b_delete_file_missing_preserves_inner_failure_visibility() -> None:
    job_id = _job_id("delete_missing")
    missing_rel_path = f"notes/queue_missing_{int(time.time())}.txt"
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={
            "command": "delete_file",
            "params": {"project_id": PROJECT_ID, "file_path": missing_rel_path},
        },
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert final.get("status") in {"completed", "failed"}
    assert final.get("command_execution") is True
    assert final.get("command_name") == "delete_file"
    assert final.get("job_success") is False
    assert final.get("command_success") is False
    assert final.get("inner_success") is False
    if final.get("status") == "completed":
        assert final.get("completed_with_error") is True
    inner = ((final.get("result") or {}).get("result") or {}).get("error") or {}
    assert inner.get("code") == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_regression_c_stopped_lifecycle_with_real_queue_commands() -> None:
    job_id = _job_id("stoppable")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={"command": "qa_sleep", "params": {"seconds": 60, "tick_seconds": 0.5}},
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    saw_running = False
    for _ in range(25):
        status_res = await _run_command("queue_get_job_status", job_id=job_id)
        assert status_res.get("success") is True
        if status_res["data"].get("status") == "running":
            saw_running = True
            break
        await asyncio.sleep(0.2)
    assert saw_running is True

    for _ in range(3):
        await _run_command("queue_stop_job", job_id=job_id)
        await asyncio.sleep(0.5)

    final = await _poll_terminal_status(job_id, timeout=45.0)
    assert final.get("status") == "stopped"
    assert final.get("job_success") is False

    stopped_list = await _run_command("queue_list_jobs", status_filter="stopped", limit=200)
    assert stopped_list.get("success") is True
    assert any(j.get("job_id") == job_id for j in stopped_list["data"]["jobs"])

    logs = await _run_command("queue_get_job_logs", job_id=job_id)
    assert logs.get("success") is True
    logs_data = logs["data"]
    assert logs_data.get("stdout_lines", 0) >= 1 or logs_data.get("stderr_lines", 0) >= 1


@pytest.mark.asyncio
async def test_regression_d_native_internal_error_mapping_not_false_success() -> None:
    job_id = _job_id("native_error")
    added = await _run_command(
        "queue_add_job",
        job_type="file_operation",
        job_id=job_id,
        params={
            "operation": "read",
            "file_path": f"/tmp/qa_queuefix_missing_{int(time.time())}.txt",
        },
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert not (
        final.get("status") == "completed" and final.get("job_success") is True
    )
    assert final.get("job_success") is False


@pytest.mark.asyncio
async def test_regression_e_deleted_retention_keeps_visibility_and_logs() -> None:
    job_id = _job_id("deleted_retention")
    added = await _run_command(
        "queue_add_job",
        job_type="command_execution",
        job_id=job_id,
        params={"command": "health", "params": {}},
    )
    assert added.get("success") is True
    started = await _run_command("queue_start_job", job_id=job_id)
    assert started.get("success") is True

    final = await _poll_terminal_status(job_id)
    assert final.get("status") == "completed"

    completed_list = await _run_command(
        "queue_list_jobs", status_filter="completed", limit=200
    )
    assert completed_list.get("success") is True
    assert any(j.get("job_id") == job_id for j in completed_list["data"]["jobs"])

    deleted = await _run_command("queue_delete_job", job_id=job_id)
    assert deleted.get("success") is True

    after_delete = await _poll_terminal_status(job_id)
    assert after_delete.get("status") == "deleted"

    deleted_list = await _run_command("queue_list_jobs", status_filter="deleted", limit=200)
    assert deleted_list.get("success") is True
    assert any(j.get("job_id") == job_id for j in deleted_list["data"]["jobs"])

    logs = await _run_command("queue_get_job_logs", job_id=job_id)
    assert logs.get("success") is True
