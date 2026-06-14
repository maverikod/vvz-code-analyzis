"""Tests for server log directory resolution and startup log."""

from __future__ import annotations

import json
from pathlib import Path

from code_analysis.core.server_log_dir import (
    append_server_startup_log,
    resolve_server_log_dir,
    server_log_dir_from_config_data,
)


def test_server_log_dir_from_config_data_absolute(tmp_path: Path) -> None:
    cfg = {"server": {"log_dir": "/var/log/casmgr"}}
    assert server_log_dir_from_config_data(cfg, tmp_path / "config.json") == Path(
        "/var/log/casmgr"
    )


def test_server_log_dir_from_config_data_relative(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config-prod.json"
    cfg_path.write_text(
        json.dumps({"server": {"log_dir": "./logs-prod"}}), encoding="utf-8"
    )
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert (
        server_log_dir_from_config_data(cfg, cfg_path)
        == (tmp_path / "logs-prod").resolve()
    )


def test_resolve_server_log_dir_from_config_argv(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "prod-logs"
    cfg_path = tmp_path / "config-prod.json"
    cfg_path.write_text(
        json.dumps({"server": {"log_dir": str(log_dir)}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("CASMGR_LOG", raising=False)
    monkeypatch.delenv("MCP_ADAPTER_LOG_DIR", raising=False)
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)
    monkeypatch.setattr(
        "code_analysis.core.server_log_dir.discover_config_path_from_argv",
        lambda _argv=None: cfg_path,
    )
    assert resolve_server_log_dir() == log_dir.resolve()


def test_append_server_startup_log_writes_file(tmp_path: Path) -> None:
    append_server_startup_log(tmp_path, "hello prod")
    log_path = tmp_path / "server_startup.log"
    assert log_path.is_file()
    assert "hello prod" in log_path.read_text(encoding="utf-8")
