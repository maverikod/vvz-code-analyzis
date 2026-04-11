"""
Tests for `code_analysis.cli.server_manager_cli`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.cli import server_manager_cli


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    return path


@pytest.fixture
def pidfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".code-analysis-server.pid"
    monkeypatch.setattr(
        server_manager_cli,
        "_default_pidfile_path",
        lambda _config_path: path,
    )
    return path


def test_start_adopts_single_live_daemon_without_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [321])

    def fail_spawn(_config_path: str, _pidfile: Path) -> int:
        raise AssertionError("start must not spawn when a live daemon already exists")

    monkeypatch.setattr(server_manager_cli, "_spawn_daemon", fail_spawn)

    rc = server_manager_cli._cmd_start(str(config_path))

    assert rc == 0
    assert pidfile.read_text(encoding="utf-8").strip() == "321"
    assert "already running pid=321" in capsys.readouterr().out


def test_start_refuses_when_multiple_matching_daemons_exist(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        server_manager_cli, "_find_daemon_pids", lambda _cfg: [101, 202]
    )

    def fail_spawn(_config_path: str, _pidfile: Path) -> int:
        raise AssertionError("start must not spawn when multiple daemons exist")

    monkeypatch.setattr(server_manager_cli, "_spawn_daemon", fail_spawn)

    rc = server_manager_cli._cmd_start(str(config_path))

    assert rc == 1
    assert not pidfile.exists()
    assert (
        "multiple running daemons found pids=101,202; stop first"
        in capsys.readouterr().out
    )


def test_stop_ignores_unrelated_live_pidfile_process(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pidfile.write_text("999", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda pid: pid in {999, 123})
    monkeypatch.setattr(
        server_manager_cli,
        "_pid_matches_daemon_for_config",
        lambda pid, _cfg: pid == 123,
    )
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [123])

    killed: list[int] = []
    monkeypatch.setattr(
        server_manager_cli,
        "_kill_process_group",
        lambda pid, timeout_s: killed.append(pid),
    )

    rc = server_manager_cli._cmd_stop(str(config_path))

    assert rc == 0
    assert killed == [123]
    assert not pidfile.exists()


def test_status_reports_multiple_matching_daemons(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [7, 8])

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 1
    assert "running (multiple daemons pids=7,8)" in capsys.readouterr().out
    assert not pidfile.exists()


def test_top_level_managed_daemon_pids_excludes_fork_children_with_same_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fork/mp children inherit cmdline; only the root managed PID must remain."""

    def ppid_map(pid: int):
        return {100: 1, 101: 100, 102: 100}.get(pid)

    monkeypatch.setattr(server_manager_cli, "_read_ppid", ppid_map)

    assert server_manager_cli._top_level_managed_daemon_pids([100, 101, 102]) == [100]


def test_top_level_managed_daemon_pids_keeps_multiple_independent_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_manager_cli, "_read_ppid", lambda pid: 1 if pid in (10, 20) else None
    )

    assert server_manager_cli._top_level_managed_daemon_pids([10, 20]) == [10, 20]


def test_find_daemon_pids_applies_top_level_filter(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ps_line = (
        "100 python -m code_analysis.main --config "
        f"{config_path} --daemon\n"
        "101 python -m code_analysis.main --config "
        f"{config_path} --daemon\n"
    )
    monkeypatch.setattr(
        server_manager_cli.subprocess,
        "check_output",
        lambda *_a, **_kw: ps_line,
    )
    monkeypatch.setattr(
        server_manager_cli,
        "_read_ppid",
        lambda pid: 1 if pid == 100 else (100 if pid == 101 else None),
    )

    assert server_manager_cli._find_daemon_pids(str(config_path)) == [100]
