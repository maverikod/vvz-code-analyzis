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


def test_start_spawns_when_no_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_spawn(_config_path: str, pf: Path) -> int:
        pf.write_text("4242", encoding="utf-8")
        return 4242

    monkeypatch.setattr(server_manager_cli, "_spawn_daemon", fake_spawn)
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(
        server_manager_cli,
        "_wait_until_daemon_stable_or_dead",
        lambda *_a, **_kw: True,
    )

    rc = server_manager_cli._cmd_start(str(config_path))

    assert rc == 0
    assert pidfile.read_text(encoding="utf-8").strip() == "4242"
    assert "started pid=4242" in capsys.readouterr().out


def test_start_already_running_when_pidfile_alive(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("777", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda _pid: True)

    def fail_spawn(_cp: str, _pf: Path) -> int:
        raise AssertionError("must not spawn when pidfile process is alive")

    monkeypatch.setattr(server_manager_cli, "_spawn_daemon", fail_spawn)

    rc = server_manager_cli._cmd_start(str(config_path))

    assert rc == 0
    assert "already running pid=777" in capsys.readouterr().out


def test_stop_kills_pidfile_and_matching_find_daemon_pids(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pidfile.write_text("10", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [20])

    killed: list[int] = []
    monkeypatch.setattr(
        server_manager_cli,
        "_kill_process_group",
        lambda pid, timeout_s: killed.append(pid),
    )

    rc = server_manager_cli._cmd_stop(str(config_path))

    assert rc == 0
    assert sorted(killed) == [10, 20]
    assert not pidfile.exists()


def test_status_stopped_no_pidfile(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [])

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "stopped"


def test_status_running_matches_find_daemon_pids(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("55", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [55])

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "running pid=55"


def test_status_running_daemon_without_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not pidfile.exists()
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [42])

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 0
    assert capsys.readouterr().out.strip() == "running pid=42 (pidfile missing)"


def test_status_removes_stale_pidfile(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("999999", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda _pid: False)

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 0
    assert "stale pidfile" in capsys.readouterr().out
    assert not pidfile.exists()


def test_status_pidfile_alive_but_not_our_daemon(
    config_path: Path,
    pidfile: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pidfile.write_text("88", encoding="utf-8")
    monkeypatch.setattr(server_manager_cli, "_find_daemon_pids", lambda _cfg: [])
    monkeypatch.setattr(server_manager_cli, "_is_alive", lambda _pid: True)

    rc = server_manager_cli._cmd_status(str(config_path))

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("stopped (pidfile pid=88 alive")
    assert "pidfile likely stale" in out
