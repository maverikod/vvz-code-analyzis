"""
Tests for project_pip_* MCP commands (sandbox pip via registered project).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Type

from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_pip_commands import (
    ProjectPipCheckCommand,
    ProjectPipInstallCommand,
    ProjectPipListCommand,
    ProjectPipSearchCommand,
    ProjectPipShowCommand,
    ProjectPipUninstallCommand,
)
from code_analysis.core.project_sandbox import (
    SandboxRunResult,
    run_pip_in_project_sandbox,
)

_PROJECT_PIP_COMMANDS: tuple[Type[BaseMCPCommand], ...] = (
    ProjectPipInstallCommand,
    ProjectPipListCommand,
    ProjectPipShowCommand,
    ProjectPipUninstallCommand,
    ProjectPipCheckCommand,
    ProjectPipSearchCommand,
)

_FAKE_PIP_LOG_FIELDS = {
    "pip_output_log_path": "/tmp/fake_pip.log",
    "pip_output_log_relative": "logs/project_pip/fake.log",
    "pip_logs_directory": "/tmp/logs",
    "pip_log_write_error": None,
}


def _assert_rich_metadata(cmd_cls: Type[BaseMCPCommand]) -> None:
    """Metadata matches the detailed paradigm used by run_project_* commands."""
    meta = cmd_cls.metadata()
    assert isinstance(meta.get("detailed_description", ""), str)
    assert len(meta["detailed_description"]) > 80
    params = meta.get("parameters")
    assert isinstance(params, dict) and params
    for pname, pinfo in params.items():
        assert isinstance(pinfo, dict), pname
        assert "description" in pinfo and pinfo["description"]
        assert "type" in pinfo
        assert "required" in pinfo
        assert "examples" in pinfo and pinfo["examples"], pname
    assert "usage_examples" in meta and len(meta["usage_examples"]) >= 1
    assert "error_cases" in meta and meta["error_cases"]
    assert "return_value" in meta and meta["return_value"]
    assert "best_practices" in meta and len(meta["best_practices"]) >= 1


def _assert_schema_examples(schema: Dict[str, Any]) -> None:
    """Return assert schema examples."""
    assert "examples" in schema and schema["examples"]
    props = schema.get("properties") or {}
    for key, prop in props.items():
        assert isinstance(prop, dict), key
        assert (
            "examples" in prop and prop["examples"]
        ), f"schema property {key!r} missing examples"


@pytest.mark.asyncio
async def test_project_pip_install_uses_asyncio_to_thread(tmp_path: Path) -> None:
    """Verify test project pip install uses asyncio to thread."""
    root = tmp_path / "proj"
    root.mkdir()
    fake = SandboxRunResult(stdout="ok", stderr="", returncode=0, timed_out=False)
    calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        calls.append((fn, args, kwargs))
        return fake

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                cmd = ProjectPipInstallCommand()
                result = await cmd.execute(
                    project_id="00000000-0000-0000-0000-000000000001",
                    packages=["requests"],
                )
    assert len(calls) == 1
    fn, args, kwargs = calls[0]
    assert fn is run_pip_in_project_sandbox
    assert args[0] == root
    assert args[1][0] == "install"
    assert "--no-input" in args[1]
    assert "requests" in args[1]
    assert isinstance(result, SuccessResult)
    assert result.data["stdout"] == "ok"
    assert result.data["pip_output_log_path"] == "/tmp/fake_pip.log"


@pytest.mark.asyncio
async def test_project_pip_install_rejects_empty_sources(tmp_path: Path) -> None:
    """Verify test project pip install rejects empty sources."""
    root = tmp_path / "proj"
    root.mkdir()
    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        cmd = ProjectPipInstallCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000001",
            packages=[],
            requirements_file=None,
        )
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_project_pip_list_freeze_uses_pip_freeze(tmp_path: Path) -> None:
    """Verify test project pip list freeze uses pip freeze."""
    root = tmp_path / "proj"
    root.mkdir()
    fake = SandboxRunResult(stdout="x==1", stderr="", returncode=0, timed_out=False)
    calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        calls.append((fn, args[1]))
        return fake

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                cmd = ProjectPipListCommand()
                result = await cmd.execute(
                    project_id="00000000-0000-0000-0000-000000000002",
                    list_format="freeze",
                )
    assert len(calls) == 1
    assert calls[0][1] == ["freeze"]
    assert isinstance(result, SuccessResult)
    assert result.data.get("pip_output_log_path") == "/tmp/fake_pip.log"


@pytest.mark.asyncio
async def test_project_pip_show_and_uninstall_delegate_to_run_pip(
    tmp_path: Path,
) -> None:
    """Verify test project pip show and uninstall delegate to run pip."""
    root = tmp_path / "proj"
    root.mkdir()
    fake = SandboxRunResult(stdout="", stderr="", returncode=0, timed_out=False)
    captured: list[list[str]] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        captured.append(list(args[1]))
        return fake

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                r_show = await ProjectPipShowCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000003",
                    packages=["pip"],
                )
                r_uni = await ProjectPipUninstallCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000003",
                    packages=["foo"],
                )
    assert captured[0][:2] == ["show", "pip"]
    assert captured[1][:3] == ["uninstall", "-y", "foo"]
    assert isinstance(r_show, SuccessResult)
    assert isinstance(r_uni, SuccessResult)
    assert r_show.data.get("pip_output_log_path") == "/tmp/fake_pip.log"
    assert r_uni.data.get("pip_output_log_path") == "/tmp/fake_pip.log"


def test_project_pip_install_uses_queue_other_pip_commands_do_not() -> None:
    """Install may run a long time and must always go through the job queue."""
    assert ProjectPipInstallCommand.use_queue is True
    assert ProjectPipListCommand.use_queue is False
    assert ProjectPipShowCommand.use_queue is False
    assert ProjectPipUninstallCommand.use_queue is False
    assert ProjectPipCheckCommand.use_queue is False
    assert ProjectPipSearchCommand.use_queue is False


@pytest.mark.parametrize(
    "cmd_cls",
    [
        ProjectPipInstallCommand,
        ProjectPipListCommand,
        ProjectPipShowCommand,
        ProjectPipUninstallCommand,
        ProjectPipCheckCommand,
        ProjectPipSearchCommand,
    ],
)
def test_project_pip_schemas_require_project_id(
    cmd_cls: Type[BaseMCPCommand],
) -> None:
    """Verify test project pip schemas require project id."""
    schema = cmd_cls.get_schema()
    required = schema.get("required") or []
    assert "project_id" in required, cmd_cls.name
    props = schema.get("properties") or {}
    assert "project_id" in props


def test_project_pip_command_names_stable() -> None:
    """Verify test project pip command names stable."""
    assert ProjectPipInstallCommand.name == "project_pip_install"
    assert ProjectPipListCommand.name == "project_pip_list"
    assert ProjectPipShowCommand.name == "project_pip_show"
    assert ProjectPipUninstallCommand.name == "project_pip_uninstall"
    assert ProjectPipCheckCommand.name == "project_pip_check"
    assert ProjectPipSearchCommand.name == "project_pip_search"


@pytest.mark.parametrize("cmd_cls", _PROJECT_PIP_COMMANDS)
def test_project_pip_metadata_matches_run_project_paradigm(
    cmd_cls: Type[BaseMCPCommand],
) -> None:
    """Verify test project pip metadata matches run project paradigm."""
    _assert_rich_metadata(cmd_cls)


@pytest.mark.parametrize("cmd_cls", _PROJECT_PIP_COMMANDS)
def test_project_pip_get_schema_has_examples(cmd_cls: Type[BaseMCPCommand]) -> None:
    """Verify test project pip get schema has examples."""
    _assert_schema_examples(cmd_cls.get_schema())


def test_run_pip_in_project_sandbox_delegates_to_run_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thin wrapper runs ``python -m pip`` via run_module_in_project_sandbox."""
    from code_analysis.core import project_sandbox as ps

    captured: dict[str, Any] = {}

    def fake_run_module(
        root_path: Path,
        module: str,
        args: list[str] | None,
        timeout_seconds: int | None,
    ) -> SandboxRunResult:
        """Return fake run module."""
        captured["root"] = root_path
        captured["module"] = module
        captured["args"] = args
        captured["timeout_seconds"] = timeout_seconds
        return SandboxRunResult("", "", 0, False)

    monkeypatch.setattr(ps, "run_module_in_project_sandbox", fake_run_module)
    ps.run_pip_in_project_sandbox(tmp_path, ["list", "--format=json"], 60)
    assert captured["module"] == "pip"
    assert captured["args"] == ["list", "--format=json"]
    assert captured["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_project_pip_check_uses_pip_list_json_and_structured_results(
    tmp_path: Path,
) -> None:
    """Verify test project pip check uses pip list json and structured results."""
    root = tmp_path / "proj"
    root.mkdir()
    pip_json = (
        '[{"name": "pip", "version": "24.0"}, {"name": "wheel", "version": "0.42.0"}]\n'
    )
    fake = SandboxRunResult(stdout=pip_json, stderr="", returncode=0, timed_out=False)
    captured: list[list[str]] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        captured.append(list(args[1]))
        return fake

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                result = await ProjectPipCheckCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000010",
                    packages=["pip", "not-installed-xyz", "Wheel"],
                )
    assert captured[0] == ["list", "--format=json"]
    assert isinstance(result, SuccessResult)
    assert result.data["parse_error"] is None
    assert result.data["all_requested_installed"] is False
    assert result.data["pip_args"] == ["list", "--format=json"]
    res = result.data["results"]
    assert len(res) == 3
    by_req = {r["requested"]: r for r in res}
    assert by_req["pip"]["installed"] is True
    assert by_req["pip"]["version"] == "24.0"
    assert by_req["not-installed-xyz"]["installed"] is False
    assert by_req["Wheel"]["installed"] is True
    assert result.data.get("pip_output_log_path") == "/tmp/fake_pip.log"


@pytest.mark.asyncio
async def test_project_pip_search_lists_and_filters_installed(tmp_path: Path) -> None:
    """Verify test project pip search lists and filters installed."""
    root = tmp_path / "proj"
    root.mkdir()
    pip_json = '[{"name": "alpha", "version": "1.0"}, {"name": "beta-test", "version": "2.0"}]\n'
    fake = SandboxRunResult(stdout=pip_json, stderr="", returncode=0, timed_out=False)

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        return fake

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                r_all = await ProjectPipSearchCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000011",
                )
                r_sub = await ProjectPipSearchCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000011",
                    query="test",
                    match_mode="substring",
                )
                r_exact = await ProjectPipSearchCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000011",
                    query="alpha",
                    match_mode="exact",
                )
    assert isinstance(r_all, SuccessResult)
    assert r_all.data["match_count"] == 2
    assert r_all.data["query"] is None
    assert isinstance(r_sub, SuccessResult)
    assert r_sub.data["match_count"] == 1
    assert r_sub.data["matches"][0]["name"] == "beta-test"
    assert isinstance(r_exact, SuccessResult)
    assert r_exact.data["match_count"] == 1
    assert r_exact.data["matches"][0]["name"] == "alpha"


@pytest.mark.asyncio
async def test_project_pip_search_rejects_bad_match_mode(tmp_path: Path) -> None:
    """Verify test project pip search rejects bad match mode."""
    root = tmp_path / "proj"
    root.mkdir()
    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        result = await ProjectPipSearchCommand().execute(
            project_id="00000000-0000-0000-0000-000000000012",
            match_mode="nope",
        )
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_PARAMS"


@pytest.mark.asyncio
async def test_project_pip_install_bootstraps_missing_venv_and_retries(
    tmp_path: Path,
) -> None:
    """Missing venv + bootstrap_venv default (true): VenvCreator runs, pip retries, succeeds."""
    from code_analysis.core.project_bootstrap.venv_creator import VenvResult
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()
    fake_result = SandboxRunResult(
        stdout="ok", stderr="", returncode=0, timed_out=False
    )
    pip_calls: list[tuple] = []
    venv_calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        if fn is run_pip_in_project_sandbox:
            pip_calls.append((args, kwargs))
            if len(pip_calls) == 1:
                raise VenvNotFoundError("no venv found")
            return fake_result
        venv_calls.append((args, kwargs))
        return fn(*args, **kwargs)

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                with patch(
                    "code_analysis.commands.project_pip_commands.VenvCreator"
                ) as mock_venv_creator_cls:
                    mock_venv_creator_cls.return_value.create.return_value = VenvResult(
                        success=True,
                        venv_path=root / ".venv",
                        message="Created .venv",
                    )
                    cmd = ProjectPipInstallCommand()
                    result = await cmd.execute(
                        project_id="00000000-0000-0000-0000-000000000020",
                        packages=["requests"],
                    )
    assert mock_venv_creator_cls.call_args.args[0] == root
    assert mock_venv_creator_cls.call_args.kwargs["python_executable"] == "python3"
    assert len(pip_calls) == 2
    assert len(venv_calls) == 1
    assert isinstance(result, SuccessResult)
    assert result.data["stdout"] == "ok"


@pytest.mark.asyncio
async def test_project_pip_install_bootstrap_disabled_keeps_venv_not_found(
    tmp_path: Path,
) -> None:
    """bootstrap_venv=false: missing venv fails immediately, VenvCreator never called."""
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        raise VenvNotFoundError("no venv found")

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.VenvCreator"
            ) as mock_venv_creator_cls:
                cmd = ProjectPipInstallCommand()
                result = await cmd.execute(
                    project_id="00000000-0000-0000-0000-000000000021",
                    packages=["requests"],
                    bootstrap_venv=False,
                )
    mock_venv_creator_cls.assert_not_called()
    assert isinstance(result, ErrorResult)
    assert result.code == "VENV_NOT_FOUND"


@pytest.mark.asyncio
async def test_project_pip_install_bootstrap_failure_is_distinguishable(
    tmp_path: Path,
) -> None:
    """VenvCreator failure surfaces as VENV_BOOTSTRAP_FAILED, distinct from VENV_NOT_FOUND."""
    from code_analysis.core.project_bootstrap.venv_creator import VenvResult
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()
    pip_calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        if fn is run_pip_in_project_sandbox:
            pip_calls.append((args, kwargs))
            raise VenvNotFoundError("no venv found")
        return fn(*args, **kwargs)

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.VenvCreator"
            ) as mock_venv_creator_cls:
                mock_venv_creator_cls.return_value.create.return_value = VenvResult(
                    success=False,
                    message="Python executable not found: 'python3.99'",
                    errors=["Python executable not found: 'python3.99'"],
                )
                cmd = ProjectPipInstallCommand()
                result = await cmd.execute(
                    project_id="00000000-0000-0000-0000-000000000022",
                    packages=["requests"],
                    python_executable="python3.99",
                )
    assert len(pip_calls) == 1
    assert isinstance(result, ErrorResult)
    assert result.code == "VENV_BOOTSTRAP_FAILED"
    assert result.code != "VENV_NOT_FOUND"
    assert "python3.99" in result.details["bootstrap_message"]
    assert result.details["bootstrap_errors"] == [
        "Python executable not found: 'python3.99'"
    ]


@pytest.mark.asyncio
async def test_project_pip_list_missing_venv_has_no_bootstrap(tmp_path: Path) -> None:
    """Read-only commands (e.g. project_pip_list) never attempt venv bootstrap."""
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        raise VenvNotFoundError("no venv found")

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.VenvCreator"
            ) as mock_venv_creator_cls:
                result = await ProjectPipListCommand().execute(
                    project_id="00000000-0000-0000-0000-000000000023",
                )
    mock_venv_creator_cls.assert_not_called()
    assert isinstance(result, ErrorResult)
    assert result.code == "VENV_NOT_FOUND"


@pytest.mark.asyncio
async def test_project_pip_install_retry_venv_not_found_after_bootstrap_is_distinguishable(
    tmp_path: Path,
) -> None:
    """After bootstrap succeeds, retried pip still fails with VenvNotFoundError — message shows bootstrap happened."""
    from code_analysis.core.project_bootstrap.venv_creator import VenvResult
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()
    pip_calls: list[tuple] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        if fn is run_pip_in_project_sandbox:
            pip_calls.append((args, kwargs))
            raise VenvNotFoundError("no venv found")
        return fn(*args, **kwargs)

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                with patch(
                    "code_analysis.commands.project_pip_commands.VenvCreator"
                ) as mock_venv_creator_cls:
                    mock_venv_creator_cls.return_value.create.return_value = VenvResult(
                        success=True,
                        venv_path=root / ".venv",
                        message="Created .venv",
                    )
                    cmd = ProjectPipInstallCommand()
                    result = await cmd.execute(
                        project_id="00000000-0000-0000-0000-000000000024",
                        packages=["requests"],
                    )
    assert len(pip_calls) == 2
    assert isinstance(result, ErrorResult)
    assert result.code == "VENV_NOT_FOUND"
    assert "bootstrap" in result.message.lower()


@pytest.mark.asyncio
async def test_project_pip_install_retry_value_error_after_bootstrap_is_distinguishable(
    tmp_path: Path,
) -> None:
    """After bootstrap succeeds, retried pip fails with ValueError — message shows bootstrap happened."""
    from code_analysis.core.project_bootstrap.venv_creator import VenvResult
    from code_analysis.core.project_sandbox import VenvNotFoundError

    root = tmp_path / "proj"
    root.mkdir()
    pip_calls: list[str] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        """Return fake to thread."""
        if fn is run_pip_in_project_sandbox:
            pip_calls.append("pip_call")
            if len(pip_calls) == 1:
                raise VenvNotFoundError("no venv found")
            raise ValueError(
                "requirements file not found or not a file: /tmp/missing.txt"
            )
        return fn(*args, **kwargs)

    with patch(
        "code_analysis.commands.project_pip_commands.BaseMCPCommand._resolve_project_root",
        return_value=root,
    ):
        with patch(
            "code_analysis.commands.project_pip_commands.asyncio.to_thread",
            side_effect=fake_to_thread,
        ):
            with patch(
                "code_analysis.commands.project_pip_commands.write_project_pip_session_log",
                return_value=_FAKE_PIP_LOG_FIELDS,
            ):
                with patch(
                    "code_analysis.commands.project_pip_commands.VenvCreator"
                ) as mock_venv_creator_cls:
                    mock_venv_creator_cls.return_value.create.return_value = VenvResult(
                        success=True,
                        venv_path=root / ".venv",
                        message="Created .venv",
                    )
                    cmd = ProjectPipInstallCommand()
                    result = await cmd.execute(
                        project_id="00000000-0000-0000-0000-000000000025",
                        packages=["requests"],
                    )
    assert len(pip_calls) == 2
    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_PATH"
    assert "bootstrap" in result.message.lower()
