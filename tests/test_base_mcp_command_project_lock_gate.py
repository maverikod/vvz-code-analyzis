"""
Tests for BaseMCPCommand's project-exclusive-lock gate (bugs 88f06abc, 5da73265):
the fast-fail check in ``run()`` and the defense-in-depth checks in
``_resolve_project_root`` / ``_validate_project_id_exists``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core import command_offload
from code_analysis.core.exceptions import ProjectLockedError

_PID = "550e8400-e29b-41d4-a716-446655440000"
_LOCK_ROW = {
    "project_id": _PID,
    "locked_at": 1.0,
    "owner": "rename_project:abc",
    "reason": "renaming",
}


class _DummyLockedAwareCommand(BaseMCPCommand):
    """Minimal concrete command used to drive BaseMCPCommand.run() in isolation."""

    name = "dummy_lock_gate_command"
    version = "1.0.0"
    descr = "test double"
    category = "test"
    author = "test"
    email = "test@example.com"
    use_queue = True  # take the inline super().run() branch, skip offload entirely

    executed = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return a permissive schema accepting an optional project_id."""
        return {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs):
        """Record that execute was reached and return a trivial success."""
        type(self).executed = True
        return SuccessResult(data={}, message="ok")


class _DummyEmergencyUnlockCommand(_DummyLockedAwareCommand):
    """Same as above but named as the one gate-exempt command."""

    name = "emergency_unlock_project"
    executed = False


class _DummyOffloadCommand(BaseMCPCommand):
    """Minimal concrete command that takes the DEFAULT (offloaded) run() path.

    ``use_queue`` is left at the adapter default (``False``), so ``run()``
    dispatches through ``offload_command_run`` instead of the inline branch
    the other dummies above force via ``use_queue = True``.
    """

    name = "dummy_offload_lock_gate_command"
    version = "1.0.0"
    descr = "test double"
    category = "test"
    author = "test"
    email = "test@example.com"

    executed = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return a permissive schema accepting an optional project_id."""
        return {
            "type": "object",
            "properties": {"project_id": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, **kwargs):
        """Record that execute was reached and return a trivial success."""
        type(self).executed = True
        return SuccessResult(data={}, message="ok")


def _run(cls: "type[BaseMCPCommand]", **kwargs: Any) -> Any:
    """Run a command class's classmethod ``run`` synchronously for a test."""
    return asyncio.run(cls.run(**kwargs))


class TestRunGate:
    """BaseMCPCommand.run()'s fast-fail project-lock gate."""

    def test_locked_project_blocks_before_execute(self) -> None:
        """A command with project_id + an existing lock never reaches execute()."""
        _DummyLockedAwareCommand.executed = False
        fake_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand, "_open_database_from_config", return_value=fake_db
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                return_value=_LOCK_ROW,
            ) as mock_get_lock,
        ):
            result = _run(_DummyLockedAwareCommand, project_id=_PID)

        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_LOCKED"
        assert _DummyLockedAwareCommand.executed is False
        mock_get_lock.assert_called_once_with(fake_db, _PID)
        fake_db.disconnect.assert_called_once()

    def test_emergency_unlock_project_is_exempt_and_reaches_execute(self) -> None:
        """emergency_unlock_project bypasses the gate even when the project is locked.

        ``super().run()`` (``mcp_proxy_adapter.commands.base.Command.run``) is
        mocked so this test targets only the gate added in
        ``BaseMCPCommand.run()``, not the adapter's global command registry
        (the dummy classes below are never registered there).
        """
        sentinel = SuccessResult(data={}, message="reached super().run()")
        with (
            patch.object(Command, "run", new=AsyncMock(return_value=sentinel)) as mock_super_run,
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            ) as mock_get_lock,
        ):
            result = _run(_DummyEmergencyUnlockCommand, project_id=_PID)

        assert result is sentinel
        mock_super_run.assert_awaited_once()
        mock_get_lock.assert_not_called()

    def test_no_project_id_is_a_gate_noop(self) -> None:
        """A command called without project_id never consults the lock table."""
        sentinel = SuccessResult(data={}, message="reached super().run()")
        with (
            patch.object(Command, "run", new=AsyncMock(return_value=sentinel)) as mock_super_run,
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            ) as mock_get_lock,
        ):
            result = _run(_DummyLockedAwareCommand)

        assert result is sentinel
        mock_super_run.assert_awaited_once()
        mock_get_lock.assert_not_called()


class TestRunGateOffloadedPath:
    """Bug 4d1a2895 / mechanism card 8e6acb34: the lock gate must be fused into
    the SAME offloaded unit as the command body, so the (DB-serialized, PG)
    lock lookup never runs on the main event loop ahead of dispatch. These
    tests exercise the DEFAULT (non-``use_queue``) path, which now goes
    through ``offload_command_run`` for real (the pool is not mocked), and
    assert the lock check itself executes on a worker thread.
    """

    def test_locked_project_blocks_before_execute_and_runs_off_caller_thread(
        self,
    ) -> None:
        """The lock check runs on the offload worker thread, not the caller's."""
        _DummyOffloadCommand.executed = False
        fake_db = MagicMock()
        caller_thread = threading.current_thread().name
        lock_thread_names: list[str] = []

        def _get_lock(db: Any, pid: Any) -> Dict[str, Any]:
            lock_thread_names.append(threading.current_thread().name)
            return _LOCK_ROW

        mock_super_run = AsyncMock()
        try:
            with (
                patch.object(
                    BaseMCPCommand, "_open_database_from_config", return_value=fake_db
                ),
                patch(
                    "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                    side_effect=_get_lock,
                ) as mock_get_lock,
                patch.object(Command, "run", new=mock_super_run),
            ):
                result = _run(_DummyOffloadCommand, project_id=_PID)
        finally:
            command_offload.shutdown()

        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_LOCKED"
        assert _DummyOffloadCommand.executed is False
        mock_get_lock.assert_called_once_with(fake_db, _PID)
        mock_super_run.assert_not_awaited()
        fake_db.disconnect.assert_called_once()
        assert lock_thread_names, "the lock check never ran"
        assert lock_thread_names[0] != caller_thread
        assert lock_thread_names[0].startswith("cmd-worker")

    def test_unlocked_project_reaches_body_via_offload_pool(self) -> None:
        """No lock -> parent_run executes, also dispatched onto the worker pool."""
        fake_db = MagicMock()
        body_thread_names: list[str] = []

        async def _fake_parent_run(**kwargs: Any) -> Any:
            body_thread_names.append(threading.current_thread().name)
            return SuccessResult(data={}, message="ok")

        try:
            with (
                patch.object(
                    BaseMCPCommand, "_open_database_from_config", return_value=fake_db
                ),
                patch(
                    "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                    return_value=None,
                ) as mock_get_lock,
                patch.object(
                    Command, "run", new=AsyncMock(side_effect=_fake_parent_run)
                ),
            ):
                result = _run(_DummyOffloadCommand, project_id=_PID)
        finally:
            command_offload.shutdown()

        assert isinstance(result, SuccessResult)
        mock_get_lock.assert_called_once_with(fake_db, _PID)
        fake_db.disconnect.assert_called_once()
        assert body_thread_names
        assert body_thread_names[0].startswith("cmd-worker")


class TestStaticHelperDefenseInDepth:
    """_resolve_project_root / _validate_project_id_exists raise ProjectLockedError."""

    def test_validate_project_id_exists_raises_when_locked(self) -> None:
        """A found-but-locked project raises ProjectLockedError, not a plain pass."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with (
            patch.object(
                BaseMCPCommand, "_open_database_from_config", return_value=mock_db
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                return_value=MagicMock(),
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.is_project_exclusively_locked",
                return_value=True,
            ),
        ):
            with pytest.raises(ProjectLockedError):
                BaseMCPCommand._validate_project_id_exists(_PID)
        mock_db.disconnect.assert_called_once()

    def test_resolve_project_root_raises_when_locked(self) -> None:
        """A found-but-locked project raises ProjectLockedError before path resolution."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.select.return_value = [
            {
                "id": _PID,
                "root_path": "some_project",
                "name": "some_project",
                "watch_dir_id": "wd-1",
            }
        ]
        with (
            patch.object(
                BaseMCPCommand, "_open_database_from_config", return_value=mock_db
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.is_project_exclusively_locked",
                return_value=True,
            ),
        ):
            with pytest.raises(ProjectLockedError):
                BaseMCPCommand._resolve_project_root(_PID)
        mock_db.disconnect.assert_called_once()
