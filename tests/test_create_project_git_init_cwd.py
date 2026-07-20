"""Guard test: create_project's git-init bootstrap step uses the project root as cwd.

Regression test for the bug where the bootstrap ``git init`` subprocess ran with
``cwd=pathlib.Path.cwd()`` (the *process's* working directory) instead of the
newly created project directory. ``git init <path>`` mostly targets ``<path>``
regardless of cwd, but running it with an unrelated/arbitrary process cwd is a
cwd-hygiene bug (e.g. relative-path resolution, nested-repo confusion, or any
future git_remote_ops change that starts trusting cwd). The fix anchors both the
argument and the subprocess cwd to the resolved project root.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.project_management_mcp_commands.create_project import (
    CreateProjectMCPCommand,
)

from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


@pytest.fixture(autouse=True)
def _patch_insert_project_row_partition(
    _partition_tests_by_server_instance_id: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Align client_api_projects' eagerly-bound sid helper with the test partition.

    Same rationale as tests/test_git_clone_command.py's fixture of the same name:
    ``client_api_projects.py`` binds ``current_server_instance_id`` at import time,
    before conftest's autouse patch runs, so it must be repatched per-test.
    """
    from code_analysis.core.server_instance import get_server_instance_id

    monkeypatch.setattr(
        "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
        get_server_instance_id,
    )


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    d = tmp_path / "watch"
    d.mkdir()
    return d


@pytest.fixture
def sqlite_db(tmp_path: Path):
    """Real in-process sqlite-backed DatabaseClient (same helper as test_git_clone_command.py)."""
    client = sqlite_inprocess_database_client(
        tmp_path / "create_project_git_init_cwd_test.db",
        backup_dir=tmp_path / "backups",
    )
    try:
        yield client
    finally:
        client.disconnect()


def _insert_watch_dir(client: Any, watch_dir_id: str, absolute_path: str) -> None:
    """Insert a watch_dirs + watch_dir_paths row for the current test server instance.

    Mirrors tests/test_git_clone_command.py's _insert_watch_dir helper.
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
async def test_create_project_git_init_uses_project_root_as_cwd(
    watch_dir: Path,
    sqlite_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bootstrap git-init subprocess must run with cwd == the project root, not process cwd."""
    watch_dir_id = str(uuid.uuid4())
    _insert_watch_dir(sqlite_db, watch_dir_id, str(watch_dir))

    monkeypatch.setattr(
        CreateProjectMCPCommand,
        "_open_database_from_config",
        staticmethod(lambda auto_analyze=False: sqlite_db),
    )

    calls: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []

    def _fake_run_git_subprocess(
        *args: Any, **kwargs: Any
    ) -> Tuple[int, str, str, bool]:
        calls.append((args, kwargs))
        return 0, "Initialized empty Git repository", "", False

    monkeypatch.setattr(
        "code_analysis.core.git_remote_ops.run_git_subprocess",
        _fake_run_git_subprocess,
    )
    monkeypatch.setattr(
        "code_analysis.core.git_integration.is_git_available",
        lambda: True,
    )

    command = CreateProjectMCPCommand()
    result = await command.execute(
        watch_dir_id=watch_dir_id,
        project_name="myproj",
        description="test project",
        create_venv=False,
        apply_template=False,
    )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)

    assert (
        len(calls) == 1
    ), f"expected exactly one git-init subprocess call, got {calls}"
    call_args, call_kwargs = calls[0]

    project_root = (watch_dir / "myproj").resolve()
    assert call_args[0] == ["git", "init", str(project_root)]
    assert call_kwargs["cwd"] == project_root, (
        f"git init cwd must be the project root, not the process cwd; "
        f"got {call_kwargs['cwd']!r}"
    )
