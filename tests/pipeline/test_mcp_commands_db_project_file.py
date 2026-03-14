"""
DB verification tests for MCP project/file/refactor write commands.

Lock-race regression: assertions in this module fail on 'database is locked',
'database is busy', or unexpected connection refused. Passing these tests
confirms the SQLite runtime path is configured for single SQL-executor behavior
(TZ universal_db_driver_chain_sqlite_process §2) in covered write flows.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.pipeline.config import PipelineConfig
from tests.pipeline.db_verification import query_db
from tests.pipeline.mcp_client import MCPClientWrapper, is_available


def _data(response: dict[str, Any]) -> dict[str, Any]:
    value = response.get("data")
    if isinstance(value, dict):
        return value
    result = response.get("result")
    if isinstance(result, dict):
        return result
    return response


def _is_lock_race_error(text: str) -> bool:
    """Return True if text indicates SQLite lock-race or steady-state connection refusal.

    Used for deterministic regression: fail on 'database is locked', 'database is busy',
    or unexpected socket refusal (steady-state path). Single SQL-executor for SQLite
    (TZ §2) must prevent lock races in covered write flows.
    """
    if not text:
        return False
    msg = text.lower()
    if "database is locked" in msg or "database is busy" in msg:
        return True
    if "connection refused" in msg or "refused" in msg and "connect" in msg:
        return True
    return False


def _get_error_message_from_response(response: dict[str, Any]) -> str:
    """Extract single error message string from MCP response for lock/race inspection."""
    err = response.get("error")
    if isinstance(err, dict):
        m = err.get("message")
        if isinstance(m, str) and m:
            return m
        data = err.get("data") or {}
        if isinstance(data, dict):
            e = data.get("error")
            if isinstance(e, str) and e:
                return e
    return ""


def _assert_no_lock_race_in_response(response: dict[str, Any], command: str) -> None:
    """Fail test if response contains lock-race or steady-state connection-refusal error.

    Regression: SQLite serialized path must not produce 'database is locked' or
    unexpected socket refusal in covered write flows.
    """
    msg = _get_error_message_from_response(response)
    if _is_lock_race_error(msg):
        pytest.fail(
            f"SQLite lock-race regression: command={command!r} "
            f"error_message={msg!r} full_response={response!r}"
        )


def _ok(response: dict[str, Any]) -> bool:
    if response.get("success") is True:
        return True
    data = response.get("data")
    if isinstance(data, dict) and data.get("success") is True:
        return True
    status = str(response.get("status", "")).lower()
    return status in {"ok", "success", "completed"}


def _call(
    client: MCPClientWrapper, command: str, params: dict[str, Any]
) -> dict[str, Any]:
    try:
        response = client.call_command(command=command, params=params)
    except Exception as exc:  # pragma: no cover
        err_msg = str(exc).lower()
        if _is_lock_race_error(err_msg):
            pytest.fail(
                f"SQLite lock-race regression (exception): command={command!r} exc={exc!r}"
            )
        if "connection" in err_msg and ("refused" in err_msg or "failed" in err_msg):
            pytest.skip(
                "Pipeline MCP server unavailable (connection failed); skip when server not running"
            )
        pytest.fail(f"Real server/direct client call failed for `{command}`: {exc}")
    if not isinstance(response, dict):
        pytest.fail(f"Unexpected non-dict MCP response for `{command}`: {response!r}")
    _assert_no_lock_race_in_response(response, command)
    return response


def _call_success(
    client: MCPClientWrapper, command: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = _call(client, command, params)
    assert _ok(response), f"Command `{command}` failed. Response: {response}"
    return _data(response)


def _latest_cst_source(db_path: Path, project_id: str, relative_path: str) -> str:
    rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT ct.cst_code AS cst_code "
            "FROM cst_trees ct "
            "JOIN files f ON f.id = ct.file_id "
            "WHERE f.project_id = ? AND f.relative_path = ? "
            "ORDER BY ct.id DESC LIMIT 1"
        ),
        params=(project_id, relative_path),
    )
    assert rows, f"No cst_trees rows found for {relative_path!r}"
    source = rows[0]["cst_code"]
    assert (
        isinstance(source, str) and source.strip()
    ), f"Empty cst_code for {relative_path!r}"
    return source


def _assert_parse_ok(db_path: Path, project_id: str, relative_paths: list[str]) -> None:
    for rel_path in relative_paths:
        ast.parse(_latest_cst_source(db_path, project_id, rel_path), filename=rel_path)


def _assert_format_lint_ok(
    client: MCPClientWrapper, project_id: str, relative_paths: list[str]
) -> None:
    for rel_path in relative_paths:
        _call_success(
            client,
            "format_code",
            {"project_id": project_id, "file_path": rel_path},
        )
        lint_data = _call_success(
            client,
            "lint_code",
            {"project_id": project_id, "file_path": rel_path},
        )
        assert (
            lint_data.get("error_count", 0) == 0
        ), f"lint_code reported errors for {rel_path}: {lint_data}"


def _create_with_source(
    client: MCPClientWrapper, project_id: str, relative_path: str, source_code: str
) -> None:
    _call_success(
        client,
        "cst_create_file",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "docstring": "Temporary pipeline test file.",
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
                    "file_docstring": "Temporary pipeline test file.",
                }
            ],
            "apply": True,
            "create_backup": True,
        },
    )


@pytest.fixture(scope="module")
def pipeline_runtime() -> dict[str, Any]:
    if not is_available():
        pytest.skip("mcp-proxy-adapter direct client is unavailable")
    config = PipelineConfig()
    client = MCPClientWrapper(config=config)
    try:
        response = client.call_command(command="list_watch_dirs", params={})
    except Exception as exc:
        err_msg = str(exc).lower()
        if _is_lock_race_error(err_msg):
            pytest.fail(
                f"SQLite lock-race regression (exception): command=list_watch_dirs exc={exc!r}"
            )
        if "connection" in err_msg and ("refused" in err_msg or "failed" in err_msg):
            pytest.skip("Real server not reachable")
        raise
    if not isinstance(response, dict):
        pytest.fail("Unexpected non-dict MCP response for list_watch_dirs")
    _assert_no_lock_race_in_response(response, "list_watch_dirs")
    watch_dirs = _data(response).get("watch_dirs", [])
    if not isinstance(watch_dirs, list) or not watch_dirs:
        pytest.skip("No watch_dirs found on real server")
    return {"client": client, "watch_dirs": watch_dirs, "db_path": config.get_db_path()}


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
            and Path(wd["absolute_path"]).exists()
        ),
        None,
    )
    if watch_dir is None:
        pytest.skip("No valid watch_dir with existing absolute_path")

    project_name = f"step05_proj_{uuid.uuid4().hex[:10]}"
    result = _call_success(
        client,
        "create_project",
        {
            "watch_dir_id": watch_dir["id"],
            "project_name": project_name,
            "description": "Step 05 pipeline DB verification project",
        },
    )
    project_id = result.get("project_id")
    assert isinstance(project_id, str) and project_id

    rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT id, root_path, name, watch_dir_id "
            "FROM projects WHERE id = ? LIMIT 1"
        ),
        params=(project_id,),
    )
    assert rows, "New project row not found in `projects` table"
    assert rows[0]["name"] == project_name
    assert rows[0]["watch_dir_id"] == watch_dir["id"]
    assert Path(rows[0]["root_path"]).name == project_name
    return {"project_id": project_id, "db_path": db_path}


def test_create_project_db_row_exists(created_project: dict[str, Any]) -> None:
    assert isinstance(created_project["project_id"], str)
    assert created_project["project_id"]


def test_cst_create_file_updates_files_and_trees(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step05/create_file_{uuid.uuid4().hex[:8]}.py"

    data = _call_success(
        client,
        "cst_create_file",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "docstring": "File generated by Step 05 test.",
        },
    )
    absolute_path = data.get("file_path")
    assert isinstance(absolute_path, str) and absolute_path

    file_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT id, relative_path FROM files "
            "WHERE project_id = ? AND path = ? "
            "AND (deleted = 0 OR deleted IS NULL) LIMIT 1"
        ),
        params=(project_id, absolute_path),
    )
    assert file_rows, "No files row found after cst_create_file"
    file_id = int(file_rows[0]["id"])

    assert query_db(db_path, "SELECT id FROM ast_trees WHERE file_id = ?", (file_id,))
    assert query_db(db_path, "SELECT id FROM cst_trees WHERE file_id = ?", (file_id,))


def test_split_class_integrity_and_db(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step05/split_class_{uuid.uuid4().hex[:8]}.py"

    _create_with_source(
        client,
        project_id,
        relative_path,
        (
            '"""Split class source."""\n\n\n'
            "class BigClass:\n"
            '    """Class that will be split."""\n\n'
            '    def __init__(self: "BigClass", a: int, b: int) -> None:\n'
            '        """Initialize counters.\n\n'
            "        Args:\n"
            "            self: Current instance.\n"
            "            a: Initial value for counter A.\n"
            "            b: Initial value for counter B.\n"
            '        """\n'
            "        self.a = a\n"
            "        self.b = b\n\n"
            '    def inc_a(self: "BigClass") -> int:\n'
            '        """Increment counter A.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Updated counter A value.\n"
            '        """\n'
            "        self.a += 1\n"
            "        return self.a\n\n"
            '    def inc_b(self: "BigClass") -> int:\n'
            '        """Increment counter B.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Updated counter B value.\n"
            '        """\n'
            "        self.b += 1\n"
            "        return self.b\n"
        ),
    )
    _call_success(
        client,
        "split_class",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "config": {
                "src_class": "BigClass",
                "dst_classes": {
                    "CounterA": {"props": ["a"], "methods": ["inc_a"]},
                    "CounterB": {"props": ["b"], "methods": ["inc_b"]},
                },
            },
        },
    )
    _assert_parse_ok(db_path, project_id, [relative_path])
    _assert_format_lint_ok(client, project_id, [relative_path])
    rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT f.id, ct.id AS cst_id, at.id AS ast_id "
            "FROM files f "
            "LEFT JOIN cst_trees ct ON ct.file_id = f.id "
            "LEFT JOIN ast_trees at ON at.file_id = f.id "
            "WHERE f.project_id = ? AND f.relative_path = ? "
            "AND (f.deleted = 0 OR f.deleted IS NULL)"
        ),
        params=(project_id, relative_path),
    )
    assert rows and any(r["cst_id"] is not None for r in rows)
    assert any(r["ast_id"] is not None for r in rows)


def test_extract_superclass_integrity_and_db(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    relative_path = f"pipeline_step05/extract_super_{uuid.uuid4().hex[:8]}.py"

    _create_with_source(
        client,
        project_id,
        relative_path,
        (
            '"""Extract superclass source."""\n\n\n'
            "class Dog:\n"
            '    """Dog class for extraction."""\n\n'
            '    def __init__(self: "Dog", name: str, legs: int) -> None:\n'
            '        """Initialize Dog.\n\n'
            "        Args:\n"
            "            self: Current instance.\n"
            "            name: Animal name.\n"
            "            legs: Number of legs.\n"
            '        """\n'
            "        self.name = name\n"
            "        self.legs = legs\n\n"
            '    def move(self: "Dog") -> str:\n'
            '        """Return move phrase.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Movement message.\n"
            '        """\n'
            '        return f"{self.name} moves"\n\n'
            '    def eat(self: "Dog") -> str:\n'
            '        """Return eat phrase.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Eating message.\n"
            '        """\n'
            '        return f"{self.name} eats"\n\n\n'
            "class Cat:\n"
            '    """Cat class for extraction."""\n\n'
            '    def __init__(self: "Cat", name: str, legs: int) -> None:\n'
            '        """Initialize Cat.\n\n'
            "        Args:\n"
            "            self: Current instance.\n"
            "            name: Animal name.\n"
            "            legs: Number of legs.\n"
            '        """\n'
            "        self.name = name\n"
            "        self.legs = legs\n\n"
            '    def move(self: "Cat") -> str:\n'
            '        """Return move phrase.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Movement message.\n"
            '        """\n'
            '        return f"{self.name} moves"\n\n'
            '    def eat(self: "Cat") -> str:\n'
            '        """Return eat phrase.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Eating message.\n"
            '        """\n'
            '        return f"{self.name} eats"\n'
        ),
    )
    _call_success(
        client,
        "extract_superclass",
        {
            "project_id": project_id,
            "file_path": relative_path,
            "config": {
                "base_class": "Animal",
                "child_classes": ["Dog", "Cat"],
                "extract_from": {
                    "Dog": {"properties": ["name", "legs"], "methods": ["move", "eat"]},
                    "Cat": {"properties": ["name", "legs"], "methods": ["move", "eat"]},
                },
            },
        },
    )
    _assert_parse_ok(db_path, project_id, [relative_path])
    _assert_format_lint_ok(client, project_id, [relative_path])
    rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT COUNT(*) AS cnt FROM cst_trees ct "
            "JOIN files f ON f.id = ct.file_id "
            "WHERE f.project_id = ? AND f.relative_path = ?"
        ),
        params=(project_id, relative_path),
    )
    assert rows and int(rows[0]["cnt"]) > 0


def test_split_file_to_package_integrity_and_db(
    pipeline_runtime: dict[str, Any], created_project: dict[str, Any]
) -> None:
    client: MCPClientWrapper = pipeline_runtime["client"]
    db_path: Path = created_project["db_path"]
    project_id: str = created_project["project_id"]
    source_rel = f"pipeline_step05/split_pkg_{uuid.uuid4().hex[:8]}.py"
    package_prefix = source_rel[:-3]

    _create_with_source(
        client,
        project_id,
        source_rel,
        (
            '"""Split file to package source."""\n\n\n'
            "class FTPExecutor:\n"
            '    """Executor for FTP tasks."""\n\n'
            '    def run(self: "FTPExecutor") -> str:\n'
            '        """Run FTP operation.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            FTP operation result.\n"
            '        """\n'
            '        return "ftp"\n\n\n'
            "class DockerExecutor:\n"
            '    """Executor for Docker tasks."""\n\n'
            '    def run(self: "DockerExecutor") -> str:\n'
            '        """Run Docker operation.\n\n'
            "        Args:\n"
            "            self: Current instance.\n\n"
            "        Returns:\n"
            "            Docker operation result.\n"
            '        """\n'
            '        return "docker"\n\n\n'
            "def create_ftp_connection() -> str:\n"
            '    """Create FTP connection marker.\n\n'
            "    Returns:\n"
            "        Connection marker string.\n"
            '    """\n'
            '    return "conn"\n'
        ),
    )
    _call_success(
        client,
        "split_file_to_package",
        {
            "project_id": project_id,
            "file_path": source_rel,
            "config": {
                "modules": {
                    "ftp_executor": {
                        "classes": ["FTPExecutor"],
                        "functions": ["create_ftp_connection"],
                    },
                    "docker_executor": {"classes": ["DockerExecutor"], "functions": []},
                }
            },
        },
    )
    file_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT relative_path FROM files "
            "WHERE project_id = ? AND relative_path LIKE ? "
            "AND (deleted = 0 OR deleted IS NULL) ORDER BY relative_path"
        ),
        params=(project_id, f"{package_prefix}/%.py"),
    )
    affected = [str(row["relative_path"]) for row in file_rows]
    assert affected and any(path.endswith("__init__.py") for path in affected)
    _assert_parse_ok(db_path, project_id, affected)
    _assert_format_lint_ok(client, project_id, affected)
    cst_rows = query_db(
        db_path=db_path,
        sql=(
            "SELECT COUNT(*) AS cnt FROM cst_trees ct "
            "JOIN files f ON f.id = ct.file_id "
            "WHERE f.project_id = ? AND f.relative_path LIKE ?"
        ),
        params=(project_id, f"{package_prefix}/%.py"),
    )
    assert cst_rows and int(cst_rows[0]["cnt"]) >= len(affected)
