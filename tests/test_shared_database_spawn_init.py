"""
Tests for shared database spawn initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from code_analysis.core.database_client.client import DatabaseClient


class _DummyClient:
    """Small fake DB client for shared database tests."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.disconnected = False

    def disconnect(self) -> None:
        """Record disconnect calls."""
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset_shared_database_state():
    """Keep global shared DB state isolated between tests."""
    from code_analysis.core.shared_database import close_shared_database

    close_shared_database()
    try:
        yield
    finally:
        close_shared_database()


def test_get_shared_database_rejects_other_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared DB proxy must not be reused from a different process."""
    from code_analysis.core import shared_database as shared_database

    shared_database.set_shared_database(cast(DatabaseClient, _DummyClient("parent")))
    monkeypatch.setattr(shared_database, "_owner_pid", -1)

    with pytest.raises(
        shared_database.SharedDatabaseNotInitializedError,
        match="different process",
    ):
        shared_database.get_shared_database()


def test_spawn_init_reopens_shared_database_for_child_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Spawn init must replace inherited DB client with a process-local one."""
    from code_analysis.commands import base_mcp_command as bcm
    from code_analysis.core import shared_database as shared_database
    import code_analysis.commands.base_mcp_command_open_db as open_db_module

    # Module import runs ensure_shared_database only when driver socket path exists.
    fake_sock = tmp_path / "present_driver.sock"
    fake_sock.write_bytes(b"")

    class _FakeStorage:
        db_path = tmp_path / "dummy.sqlite"

    monkeypatch.setattr(
        bcm.BaseMCPCommand,
        "_get_shared_storage",
        staticmethod(lambda: _FakeStorage()),
    )
    monkeypatch.setattr(
        bcm,
        "_get_socket_path_from_db_path",
        lambda _db_path: str(fake_sock),
    )

    parent_client = _DummyClient("parent")
    child_client = _DummyClient("child")
    shared_database.set_shared_database(cast(DatabaseClient, parent_client))
    monkeypatch.setattr(shared_database, "_owner_pid", -1)
    monkeypatch.setattr(
        open_db_module,
        "open_database_from_config_impl",
        lambda *args, **kwargs: child_client,
    )

    sys.modules.pop("code_analysis.core.shared_database_spawn_init", None)
    importlib.import_module("code_analysis.core.shared_database_spawn_init")

    assert parent_client.disconnected is True
    assert shared_database.is_shared_database_current_process() is True
    proxy = shared_database.get_shared_database()
    assert cast(Any, proxy).marker == "child"


def test_command_execution_job_patch_ensures_process_local_shared_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Queued command execution must reinitialize shared DB for the current PID."""
    from mcp_proxy_adapter.commands.command_registry import registry
    from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob

    from code_analysis.core import command_execution_job_patch as patch_module

    patch_module.patch_command_execution_job()

    ensured_calls: list[str] = []
    captured_context: dict[str, Any] = {}

    class _FakeCommand:
        """Simple async command for queue patch verification."""

        @classmethod
        async def run(cls, **kwargs):
            captured_context.update(kwargs.get("context") or {})
            return {"ok": True}

    monkeypatch.setattr(
        patch_module,
        "ensure_shared_database_for_current_process",
        lambda: ensured_calls.append("called"),
    )
    monkeypatch.setattr(
        registry,
        "get_command",
        lambda command_name: _FakeCommand if command_name == "fake_command" else None,
    )

    job = CommandExecutionJob(
        "job-test",
        {"command": "fake_command", "params": {}, "context": {}},
    )
    job.run()

    assert ensured_calls == ["called"]
    assert "progress_tracker" in captured_context
