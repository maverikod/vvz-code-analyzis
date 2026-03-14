"""
DB verification tests for MCP "other" write commands and queue flows.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.pipeline.config import PipelineConfig
from tests.pipeline.db_verification import query_db
from tests.pipeline.mcp_client import MCPClientWrapper, is_available

TERMINAL_OK = {
    "completed",
    "complete",
    "success",
    "succeeded",
    "done",
    "finished",
    "job_completed",
}
TERMINAL_ERROR = {
    "failed",
    "error",
    "cancelled",
    "canceled",
    "stopped",
    "timeout",
    "job_failed",
    "job_stopped",
}


def _data(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data")
    if isinstance(value, dict):
        return value
    result = response.get("result")
    if isinstance(result, dict):
        return result
    return response


def _ok(response: dict[str, Any]) -> bool:
    if response.get("success") is True:
        return True
    data = response.get("data")
    if isinstance(data, dict) and data.get("success") is True:
        return True
    status = str(response.get("status", "")).lower()
    return status in {"ok", "success", "completed"}


def _call(
    client: MCPClientWrapper,
    command: str,
    params: dict[str, Any],
    *,
    use_queue: bool | None = None,
) -> dict[str, Any]:
    try:
        response = client.call_command(
            command=command, params=params, use_queue=use_queue
        )
    except Exception as exc:  # pragma: no cover - depends on runtime server
        msg = str(exc).lower()
        if "connection" in msg and ("refused" in msg or "failed" in msg):
            pytest.skip(
                "Pipeline MCP server unavailable (connection failed); skip when server not running"
            )
        pytest.fail(f"Real server/direct client call failed for `{command}`: {exc}")
    if not isinstance(response, dict):
        pytest.fail(f"Unexpected non-dict MCP response for `{command}`: {response!r}")
    return response


def _call_success(
    client: MCPClientWrapper,
    command: str,
    params: dict[str, Any],
    *,
    use_queue: bool | None = None,
) -> dict[str, Any]:
    response = _call(client, command, params, use_queue=use_queue)
    assert _ok(response), f"Command `{command}` failed. Response: {response}"
    return _data(response)


def _find_in_payload(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = _find_in_payload(value, key)
            if found is not None:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_in_payload(item, key)
            if found is not None:
                return found
    return None


def _extract_status(response: dict[str, Any]) -> str:
    status = _find_in_payload(response, "status")
    if isinstance(status, str) and status:
        return status.lower()
    return ""


def _poll_queue_job(
    client: MCPClientWrapper,
    job_id: str,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    status_response: dict[str, Any] = {}
    logs_response: dict[str, Any] = {}
    while time.time() < deadline:
        status_response = _call(client, "queue_get_job_status", {"job_id": job_id})
        status = _extract_status(status_response)
        if status in TERMINAL_OK:
            logs_response = _call(client, "queue_get_job_logs", {"job_id": job_id})
            return status, status_response, logs_response
        if status in TERMINAL_ERROR:
            logs_response = _call(client, "queue_get_job_logs", {"job_id": job_id})
            return status, status_response, logs_response
        time.sleep(2)

    pytest.fail(f"Queue job `{job_id}` did not finish in {timeout_seconds}s")


def _create_with_source(
    client: MCPClientWrapper,
    project_id: str,
    relative_path: str,
    source_code: str,
) -> str:
    create_data = _call_success(
        client,
        "cst_create_file",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "docstring": "Temporary pipeline step-06 file.",
        },
    )
    _call_success(
        client,
        "compose_cst_module",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "ops": [
                {
                    "selector": {"kind": "module"},
                    "new_code": source_code,
                    "file_docstring": "Temporary pipeline step-06 file.",
                }
            ],
            "apply": True,
            "create_backup": True,
        },
    )
    file_path = create_data.get("file_path")
    assert isinstance(file_path, str) and file_path
    return file_path


def _run_queue_command(
    client: MCPClientWrapper,
    command: str,
    params: dict[str, Any],
    timeout_seconds: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    queue_response = _call(client, command, params, use_queue=True)
    job_id = _find_in_payload(queue_response, "job_id")
    if not isinstance(job_id, str) or not job_id:
        pytest.fail(f"No `job_id` in {command} queue response: {queue_response}")
    queue_status = _extract_status(queue_response)
    if queue_status in (TERMINAL_OK | TERMINAL_ERROR):
        logs_response = _call(client, "queue_get_job_logs", {"job_id": job_id})
        return queue_status, queue_response, logs_response
    return _poll_queue_job(
        client=client,
        job_id=job_id,
        timeout_seconds=timeout_seconds,
    )


def _wait_for_tree_rows(
    db_path: Path,
    file_id: int,
    *,
    timeout_seconds: int = 20,
) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        has_ast = bool(
            query_db(
                db_path,
                "SELECT id FROM ast_trees WHERE file_id = ? LIMIT 1",
                (file_id,),
            )
        )
        has_cst = bool(
            query_db(
                db_path,
                "SELECT id FROM cst_trees WHERE file_id = ? LIMIT 1",
                (file_id,),
            )
        )
        if has_ast and has_cst:
            return True
        time.sleep(1)
    return False


@pytest.fixture(scope="module")
def pipeline_runtime() -> dict[str, Any]:
    if not is_available():
        pytest.skip("mcp-proxy-adapter direct client is unavailable")
    config = PipelineConfig()
    client = MCPClientWrapper(config=config)
    watch_dirs = _data(_call(client, "list_watch_dirs", {})).get("watch_dirs", [])
    if not isinstance(watch_dirs, list) or not watch_dirs:
        pytest.skip("No watch_dirs found on real server")
    return {
        "client": client,
        "watch_dirs": watch_dirs,
        "db_path": config.get_db_path(),
        "timeout": config.timeout,
    }


@pytest.fixture(scope="module")
def created_project(pipeline_runtime: dict[str, Any]) -> dict[str, Any]:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = pipeline_runtime["db_path"]
    watch_dirs: list[dict[str, Any]] = pipeline_runtime["watch_dirs"]
    watch_dir = next(
        (
            wd
            for wd in watch_dirs
            if wd.get("id")
            and wd.get("absolute_path")
            and Path(str(wd["absolute_path"])).exists()
        ),
        None,
    )
    if watch_dir is None:
        pytest.skip("No valid watch_dir with existing absolute_path")

    project_name = f"step06_proj_{uuid.uuid4().hex[:10]}"
    result = _call_success(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir["id"],
            "project_name": project_name,
            "description": "Step 06 pipeline DB verification project",
        },
    )
    project_id = result.get("project_id")
    assert isinstance(project_id, str) and project_id
    rows = query_db(
        db_path=db_path,
        sql="SELECT root_path FROM projects WHERE id = ? LIMIT 1",
        params=(project_id,),
    )
    assert rows, "Project row was not created in `projects` table"
    root_path = str(rows[0]["root_path"])
    assert Path(root_path).exists(), f"Project root does not exist: {root_path}"
    return {"project_id": project_id, "db_path": db_path, "root_path": root_path}


def test_delete_and_restore_deleted_files_update_db(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step06/delete_restore_{uuid.uuid4().hex[:8]}.py"
    absolute_path = _create_with_source(
        client,
        project_id,
        relative_path,
        '"""Delete/restore test."""\n\nVALUE = 1\n',
    )

    _call_success(
        client, "delete_file", {"project_id": project_id, "file_path": relative_path}
    )
    deleted_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT id, path, original_path, version_dir, deleted "
            "FROM files WHERE project_id = ? AND original_path = ? "
            "ORDER BY id DESC LIMIT 1"
        ),
        params=(project_id, absolute_path),
    )
    assert deleted_rows, "No deleted row found after `delete_file`"
    assert int(deleted_rows[0]["deleted"]) == 1
    assert str(deleted_rows[0]["path"]) != absolute_path
    assert deleted_rows[0]["version_dir"]

    _call_success(
        client,
        "restore_deleted_files",
        {"project_id": project_id, "file_paths": [absolute_path]},
    )
    restored_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT path, original_path, version_dir, deleted FROM files "
            "WHERE project_id = ? AND path = ? ORDER BY id DESC LIMIT 1"
        ),
        params=(project_id, absolute_path),
    )
    assert restored_rows, "No restored row found after `restore_deleted_files`"
    assert int(restored_rows[0]["deleted"]) == 0
    assert restored_rows[0]["original_path"] is None
    assert restored_rows[0]["version_dir"] is None


def test_cleanup_deleted_files_hard_delete_removes_row(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step06/cleanup_{uuid.uuid4().hex[:8]}.py"
    absolute_path = _create_with_source(
        client,
        project_id,
        relative_path,
        '"""Cleanup hard delete test."""\n\nFLAG = True\n',
    )
    _call_success(
        client, "delete_file", {"project_id": project_id, "file_path": relative_path}
    )
    rows = query_db(
        db_path=db_path,
        sql="SELECT id FROM files WHERE project_id = ? AND original_path = ? LIMIT 1",
        params=(project_id, absolute_path),
    )
    assert rows, "No deleted row found before cleanup"
    deleted_file_id = int(rows[0]["id"])

    _call_success(
        client,
        "cleanup_deleted_files",
        {"project_id": project_id, "hard_delete": True},
    )
    assert not query_db(
        db_path=db_path,
        sql="SELECT id FROM files WHERE id = ? LIMIT 1",
        params=(deleted_file_id,),
    ), "Deleted file row still exists after hard cleanup"


def test_update_indexes_queue_flow_and_db_checks(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    root_path = Path(created_project["root_path"])
    relative_path = f"pipeline_step06/queue_index_{uuid.uuid4().hex[:8]}.py"
    absolute_path = root_path / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_text(
        '"""Queue update_indexes test."""\n\nX = 7\n', encoding="utf-8"
    )

    status, status_payload, logs_payload = _run_queue_command(
        client=client,
        command="update_indexes",
        params={"project_id": project_id},
        timeout_seconds=int(pipeline_runtime["timeout"]),
    )
    assert status in TERMINAL_OK, (
        f"update_indexes queue job failed with status `{status}`. "
        f"Status payload: {status_payload}; logs payload: {logs_payload}"
    )

    file_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT id FROM files WHERE project_id = ? AND path = ? "
            "AND (deleted = 0 OR deleted IS NULL) LIMIT 1"
        ),
        params=(project_id, str(absolute_path)),
    )
    assert file_rows, "No files row found after queued update_indexes"
    file_id = int(file_rows[0]["id"])
    assert _wait_for_tree_rows(
        db_path=db_path,
        file_id=file_id,
        timeout_seconds=20,
    ), "No ast_trees/cst_trees rows found after queued update_indexes"


def test_comprehensive_analysis_queue_flow_and_db_checks(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step06/queue_analysis_{uuid.uuid4().hex[:8]}.py"
    absolute_path = _create_with_source(
        client,
        project_id,
        relative_path,
        '"""Queue comprehensive analysis test."""\n\nMESSAGE = "ok"\n',
    )

    status, status_payload, logs_payload = _run_queue_command(
        client=client,
        command="comprehensive_analysis",
        params={"project_id": project_id, "file_path": relative_path},
        timeout_seconds=int(pipeline_runtime["timeout"]),
    )
    assert status in TERMINAL_OK, (
        f"comprehensive_analysis queue job failed with status `{status}`. "
        f"Status payload: {status_payload}; logs payload: {logs_payload}"
    )

    file_rows = query_db(
        db_path=db_path,
        sql="SELECT id FROM files WHERE project_id = ? AND path = ? LIMIT 1",
        params=(project_id, absolute_path),
    )
    assert file_rows, "File row not found for comprehensive_analysis DB check"
    file_id = int(file_rows[0]["id"])
    analysis_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT id, project_id, file_id FROM comprehensive_analysis_results "
            "WHERE project_id = ? AND file_id = ? ORDER BY id DESC LIMIT 1"
        ),
        params=(project_id, file_id),
    )
    assert analysis_rows, "No comprehensive_analysis_results row found after queued run"
