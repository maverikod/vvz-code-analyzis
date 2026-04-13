"""
Tests for daemon PID discovery in `code_analysis.cli.server_manager_cli`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from code_analysis.cli import server_manager_cli


@pytest.mark.skipif(
    sys.platform == "win32", reason="chmod +x not used for venv layout test"
)
def test_python_executable_for_daemon_prefers_dot_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    venv_py = tmp_path / ".venv" / "bin" / "python"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_bytes(b"#!/bin/sh\nexec true\n")
    os.chmod(venv_py, 0o755)
    monkeypatch.delenv(server_manager_cli._ENV_DAEMON_PYTHON, raising=False)

    got = server_manager_cli._python_executable_for_daemon(str(cfg))
    assert got == str(venv_py.resolve())


def test_spawn_daemon_sets_cwd_to_config_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    pidfile = tmp_path / "x.pid"
    captured: dict[str, str] = {}

    class _Proc:
        pid = 99999

    def fake_popen(_a: object, **kwargs: object) -> _Proc:
        captured["cwd"] = str(kwargs.get("cwd", ""))
        assert kwargs.get("env") is not None
        return _Proc()

    monkeypatch.setattr(server_manager_cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        server_manager_cli,
        "_python_executable_for_daemon",
        lambda _c: sys.executable,
    )

    pid = server_manager_cli._spawn_daemon(str(cfg), pidfile)
    assert pid == 99999
    assert captured["cwd"] == str(tmp_path.resolve())


def test_wait_until_daemon_stable_or_dead_false_when_exits_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda _pid: False)
    assert not server_manager_cli._wait_until_daemon_stable_or_dead(
        1, stable_seconds=0.2, max_wait_seconds=1.0
    )


def test_wait_until_daemon_stable_or_dead_true_when_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda _pid: True)
    assert server_manager_cli._wait_until_daemon_stable_or_dead(
        1, stable_seconds=0.15, max_wait_seconds=1.0
    )


@pytest.mark.skipif(sys.platform != "linux", reason="/proc/<pid>/cwd is Linux-specific")
def test_resolved_config_path_relative_uses_proc_cwd(tmp_path: Path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        got = server_manager_cli._resolved_config_path_for_daemon_pid(
            os.getpid(), "config.json"
        )
    finally:
        os.chdir(old)
    assert got == str(cfg.resolve())


def test_resolved_config_path_absolute(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text("{}", encoding="utf-8")
    got = server_manager_cli._resolved_config_path_for_daemon_pid(os.getpid(), str(cfg))
    assert got == str(cfg.resolve())


def test_find_daemon_pids_matches_via_resolved_relative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text("{}", encoding="utf-8")
    cfg_res = str(cfg.resolve())

    ps_line = (
        "5000 python -m code_analysis.main --config config.json --daemon\n"
        "6000 python -m code_analysis.main --config other.json --daemon\n"
    )
    monkeypatch.setattr(
        server_manager_cli.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )

    def fake_resolve(pid: int, cfg_argv: str) -> str | None:
        if pid == 5000 and cfg_argv == "config.json":
            return cfg_res
        return None

    monkeypatch.setattr(
        server_manager_cli,
        "_resolved_config_path_for_daemon_pid",
        fake_resolve,
    )

    assert server_manager_cli._find_daemon_pids(cfg_res) == [5000]


def test_root_daemon_pids_only_drops_fork_children_with_same_cmdline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Children keep parent's argv until exec; only session roots must count."""

    def ppid_of(pid: int) -> str | None:
        return {100: 1, 101: 100, 102: 100}.get(pid)

    monkeypatch.setattr(server_manager_cli, "_read_ppid", ppid_of)

    assert server_manager_cli._root_daemon_pids_only([100, 101, 102]) == [100]


def test_find_daemon_pids_does_not_match_other_basename_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: basename-only match used to kill unrelated ``config.json`` daemons."""

    mine = tmp_path / "mine" / "config.json"
    mine.parent.mkdir(parents=True)
    mine.write_text("{}", encoding="utf-8")

    ps_line = "7000 python -m code_analysis.main --config config.json --daemon\n"
    monkeypatch.setattr(
        server_manager_cli.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )
    monkeypatch.setattr(
        server_manager_cli,
        "_resolved_config_path_for_daemon_pid",
        lambda _pid, _argv: None,
    )

    assert server_manager_cli._find_daemon_pids(str(mine.resolve())) == []
