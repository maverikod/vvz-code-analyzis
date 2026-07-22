"""
Ensure run_project_script / run_project_module offload blocking sandbox work.

Subprocess execution must not block the asyncio event loop (asyncio.to_thread).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.run_project_module_command import RunProjectModuleCommand
from code_analysis.commands.run_project_script_command import RunProjectScriptCommand
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.project_sandbox import (
    SandboxRunResult,
    run_in_project_sandbox,
    run_module_in_project_sandbox,
)

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_run_project_script_uses_asyncio_to_thread_for_sandbox(
    tmp_path: Path,
) -> None:
    """Verify test run project script uses asyncio to thread for sandbox."""
    root = tmp_path / "proj"
    root.mkdir()
    fake = SandboxRunResult(stdout="ok", stderr="", returncode=0, timed_out=False)
    calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        calls.append((fn, args, kwargs))
        return fake

    with patch(
        "code_analysis.commands.run_project_script_command.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.run_project_script_command.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            cmd = RunProjectScriptCommand()
            result = await cmd.execute(
                project_id="00000000-0000-0000-0000-000000000001",
                file_path="main.py",
            )
    assert len(calls) == 1
    fn, args, kwargs = calls[0]
    assert fn is run_in_project_sandbox
    assert args[0] == root
    assert args[1] == "main.py"
    assert isinstance(result, SuccessResult)
    assert result.data["stdout"] == "ok"


@pytest.mark.asyncio
async def test_run_project_module_uses_asyncio_to_thread_for_sandbox(
    tmp_path: Path,
) -> None:
    """Verify test run project module uses asyncio to thread for sandbox."""
    root = tmp_path / "proj"
    root.mkdir()
    fake = SandboxRunResult(stdout="help", stderr="", returncode=0, timed_out=False)
    calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        calls.append((fn, args, kwargs))
        return fake

    with patch(
        "code_analysis.commands.run_project_module_command.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.run_project_module_command.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            cmd = RunProjectModuleCommand()
            result = await cmd.execute(
                project_id="00000000-0000-0000-0000-000000000002",
                module="mymod",
                args=["--help"],
            )
    assert len(calls) == 1
    fn, args, kwargs = calls[0]
    assert fn is run_module_in_project_sandbox
    assert args[0] == root
    assert args[1] == "mymod"
    assert args[2] == ["--help"]
    assert isinstance(result, SuccessResult)
    assert result.data["stdout"] == "help"


def test_run_project_script_uses_queue_run_project_module_inline() -> None:
    """run_project_script defaults to the job queue; run_project_module stays inline.

    Sandbox subprocess work is still offloaded with asyncio.to_thread so the event
    loop is not blocked. Long-lived module runs (e.g. servers) remain inline-only.
    """
    assert RunProjectScriptCommand.use_queue is True
    assert RunProjectModuleCommand.use_queue is False


def test_run_project_script_validate_params_accepts_params_without_db() -> None:
    """validate_params checks schema only; project existence is deferred to execute."""
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
    ) as mock_open_db:
        result = RunProjectScriptCommand().validate_params(
            {"project_id": f"  {_VALID_UUID}  ", "file_path": "main.py"}
        )
    mock_open_db.assert_not_called()
    assert result["project_id"] == _VALID_UUID
    assert result["file_path"] == "main.py"


def test_run_project_script_validate_params_rejects_unknown_param() -> None:
    """Verify test run project script validate params rejects unknown param."""
    with pytest.raises(ValidationError, match="unknown parameter"):
        RunProjectScriptCommand().validate_params(
            {
                "project_id": _VALID_UUID,
                "file_path": "main.py",
                "unexpected": True,
            }
        )


def test_run_project_module_validate_params_rejects_unknown_project() -> None:
    """Verify test run project module validate params rejects unknown project."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.base_mcp_command.get_project",
            return_value=None,
        ),
    ):
        with pytest.raises(ValidationError, match="not found"):
            RunProjectModuleCommand().validate_params(
                {"project_id": _VALID_UUID, "module": "mymod"}
            )
