"""Tests for server.log_dir resolution (production vs config_dir/logs)."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.storage_paths import (
    resolve_search_sessions_root,
    resolve_service_log_dir,
    resolve_storage_paths,
)


def test_resolve_service_log_dir_absolute(tmp_path: Path) -> None:
    """Verify test resolve service log dir absolute."""
    cfg = {"server": {"log_dir": "/var/log/casmgr"}}
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    assert resolve_service_log_dir(config_data=cfg, config_path=config_path) == Path(
        "/var/log/casmgr"
    )


def test_storage_paths_uses_server_log_dir_not_config_dir(tmp_path: Path) -> None:
    """Verify test storage paths uses server log dir not config dir."""
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


def test_resolve_search_sessions_root_uses_db_parent_not_config_dir(
    tmp_path: Path,
) -> None:
    """Verify test resolve search sessions root uses db parent not config dir."""
    etc = tmp_path / "etc" / "casmgr"
    etc.mkdir(parents=True)
    config_path = etc / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    cfg = {
        "code_analysis": {"storage": {"db_path": "/var/casmgr/data/code_analysis.db"}},
    }
    root = resolve_search_sessions_root(config_data=cfg, config_path=config_path)
    assert root == Path("/var/casmgr/data/search_sessions")
    assert not str(root).startswith(str(etc))
