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
