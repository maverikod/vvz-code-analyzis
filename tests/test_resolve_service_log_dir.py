"""Tests for server.log_dir resolution (production vs config_dir/logs)."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.storage_paths import (
    resolve_service_log_dir,
    resolve_storage_paths,
)


def test_resolve_service_log_dir_absolute(tmp_path: Path) -> None:
    cfg = {"server": {"log_dir": "/var/log/casmgr"}}
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    assert resolve_service_log_dir(config_data=cfg, config_path=config_path) == Path(
        "/var/log/casmgr"
    )


def test_storage_paths_uses_server_log_dir_not_config_dir(tmp_path: Path) -> None:
    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    config_path = etc / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = {
        "server": {"log_dir": "/var/log/casmgr"},
        "code_analysis": {"storage": {"db_path": "/var/casmgr/data/code_analysis.db"}},
    }
    paths = resolve_storage_paths(config_data=cfg, config_path=config_path)
    assert paths.log_dir == Path("/var/log/casmgr")
    assert paths.config_dir == etc.resolve()
