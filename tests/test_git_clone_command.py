"""Tests for the git_clone MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_clone_command import GitCloneCommand

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture(autouse=True)
def _patch_insert_project_row_partition(
    _partition_tests_by_server_instance_id: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Align client_api_projects' eagerly-bound sid helper with the test partition.

    conftest.py's autouse fixture monkeypatches
    ``code_analysis.core.server_instance.get_server_instance_id`` and
    ``code_analysis.core.database.watch_dirs_partition.current_server_instance_id``,
    which covers callers that resolve the name dynamically at call time (e.g.
    ``fetch_watch_dir_absolute_path``'s function-local import). However,
    ``code_analysis/core/database_client/client_api_projects.py`` imports
    ``current_server_instance_id`` via a module-level ``from ... import`` (bound once
    at import time, before this fixture ever runs), so ``insert_project_row`` and
    ``get_project`` would otherwise resolve the real production
    ``server_instance_id`` instead of the test partition — causing a
    ``projects.(server_instance_id, watch_dir_id)`` foreign-key mismatch against a
    ``watch_dirs`` row inserted under the test partition. Patch this specific eager
    binding to match. The explicit dependency on
    ``_partition_tests_by_server_instance_id`` guarantees conftest's patch of
    ``get_server_instance_id`` is already active before this fixture reads it.
    """
    from code_analysis.core.server_instance import get_server_instance_id

    monkeypatch.setattr(
        "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
        get_server_instance_id,
    )


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )
    return result.stdout


def _remote_config() -> Dict[str, Any]:
    return {
        "code_analysis": {
            "git": {
                "remote_enabled": True,
                "protected_branches": [],
                "allow_force_push": False,
                "remote_timeout_seconds": 30,
            }
        }
    }


def _assert_schema() -> None:
    schema = GitCloneCommand.get_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"url", "watch_dir_id", "target_name"}
    for prop_name, prop in schema["properties"].items():
        assert prop.get("description"), f"{prop_name} missing description"


def _assert_metadata() -> None:
    metadata = GitCloneCommand.metadata()
    assert metadata["name"] == GitCloneCommand.get_name()
    assert metadata["description"]
    assert metadata["detailed_description"]
    for param_name in ("url", "watch_dir_id", "target_name", "branch", "depth"):
        assert metadata["parameters"][param_name]["description"]
    assert metadata["return_value"]["success"]["description"]
    assert metadata["return_value"]["error"]["description"]
    assert metadata["usage_examples"]
    assert metadata["error_cases"]
    assert metadata["best_practices"]


def test_git_clone_publishes_strict_schema() -> None:
    _assert_schema()


def test_git_clone_publishes_man_page_metadata() -> None:
    _assert_metadata()


@pytest.fixture
def bare_source_repo(tmp_path: Path) -> Path:
    """Create a local bare repo with one commit, clonable via file://."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test User")
    (seed / "README.md").write_text("hello\n", encoding="utf-8")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "initial")
    _git(seed, "branch", "-M", "main")

    bare = tmp_path / "source.git"
    _git(tmp_path, "clone", "--bare", str(seed), str(bare))
    return bare


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "watch"
    d.mkdir()
    return d


@pytest.fixture
def sqlite_db(tmp_path: Path):
    """Real DatabaseClient over an in-process RPC handler on a throwaway sqlite file.

    Reuses the shared tests/sqlite_inprocess_database.py helper (same helper used
    by tests/test_add_file_cross_project_path.py and friends) so the full
    production schema (watch_dirs, watch_dir_paths, projects, ...) is available
    and the real call chain (get_watch_dir_absolute_path, insert_project_row,
    persist_projects_root_path_stored_value, find_project_id_by_resolved_absolute_root)
    runs against real SQL instead of a hand-rolled mock.
    """
    client = sqlite_inprocess_database_client(
        tmp_path / "git_clone_test.db", backup_dir=tmp_path / "backups"
    )
    try:
        yield client
    finally:
        client.disconnect()


def _insert_watch_dir(client: Any, watch_dir_id: str, absolute_path: str) -> None:
    """Insert a watch_dirs + watch_dir_paths row for the current test server instance.

    Mirrors tests/test_watch_dirs_mount_sync.py's _insert_watch_dir helper.
    """
    from code_analysis.core.server_instance import get_server_instance_id

    sid = get_server_instance_id()
    client.execute(
        """
        INSERT INTO watch_dirs (server_instance_id, id, name, deleted, updated_at)
        VALUES (?, ?, ?, ?, julianday('now'))
        """,
        (sid, watch_dir_id, watch_dir_id, 0),
    )
    client.execute(
        """
        INSERT INTO watch_dir_paths (server_instance_id, watch_dir_id, absolute_path, updated_at)
        VALUES (?, ?, ?, julianday('now'))
        """,
        (sid, watch_dir_id, absolute_path),
    )


@pytest.mark.asyncio
async def test_git_clone_clones_and_registers_project(
    bare_source_repo: Path,
    watch_dir: Path,
    sqlite_db: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clone from a local bare repo via file:// and verify registration."""
    watch_dir_id = str(uuid.uuid4())
    _insert_watch_dir(sqlite_db, watch_dir_id, str(watch_dir))

    monkeypatch.setattr(
        GitCloneCommand,
        "_open_database_from_config",
        staticmethod(lambda auto_analyze=False: sqlite_db),
    )
    monkeypatch.setattr(
        GitCloneCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )

    url = f"file://{bare_source_repo}"
    command = GitCloneCommand()
    result = await command.execute(
        url=url,
        watch_dir_id=watch_dir_id,
        target_name="myrepo",
    )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    data = result.data
    dest = watch_dir / "myrepo"
    assert dest.is_dir()
    assert (dest / "projectid").is_file()
    assert (dest / "README.md").is_file()
    assert isinstance(data["project_id"], str) and data["project_id"]
    assert data["path"] == str(dest)
    assert data["url"] == url
    assert data["head_sha"]

    # GitCloneCommand.execute() disconnects the (shared, in production)
    # database client in its finally block, same as create_project's MCP
    # command. Reopen a fresh client against the same on-disk sqlite file to
    # verify the project was actually registered, rather than reusing the
    # now-closed sqlite_db handle.
    verify_client = sqlite_inprocess_database_client(
        tmp_path / "git_clone_test.db", backup_dir=tmp_path / "backups"
    )
    try:
        registered = verify_client.get_project(data["project_id"])
        assert registered is not None
    finally:
        verify_client.disconnect()


@pytest.mark.asyncio
async def test_git_clone_rejects_traversal_target_name(
    watch_dir: Path,
    sqlite_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target_name path traversal must fail validation before touching the DB."""
    monkeypatch.setattr(
        GitCloneCommand,
        "_open_database_from_config",
        staticmethod(lambda auto_analyze=False: sqlite_db),
    )
    monkeypatch.setattr(
        GitCloneCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )

    command = GitCloneCommand()
    result = await command.execute(
        url="file:///nonexistent",
        watch_dir_id=str(uuid.uuid4()),
        target_name="../escape",
    )
    assert isinstance(result, ErrorResult)


@pytest.mark.asyncio
async def test_git_clone_unknown_watch_dir_fails(
    sqlite_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown watch_dir_id must fail with GIT_CLONE_WATCH_DIR_NOT_FOUND."""
    monkeypatch.setattr(
        GitCloneCommand,
        "_open_database_from_config",
        staticmethod(lambda auto_analyze=False: sqlite_db),
    )
    monkeypatch.setattr(
        GitCloneCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )

    command = GitCloneCommand()
    result = await command.execute(
        url="file:///nonexistent",
        watch_dir_id=str(uuid.uuid4()),
        target_name="myrepo",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "GIT_CLONE_WATCH_DIR_NOT_FOUND"
