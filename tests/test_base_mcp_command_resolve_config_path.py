"""
Tests for BaseMCPCommand._resolve_config_path()'s fallback priority chain
(recovered from casmgr:1.6.87 image, built from an uncommitted tree).

Priority order under test:
    1. mcp_proxy_adapter global config (cfg.config_path), only when that file
       actually exists on disk.
    2. process argv --config.
    3. CASMGR_CONFIG env var.
    4. /etc/casmgr/config.json when present.
    5. cwd/config.json (final fallback, always returned).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand


def _no_adapter_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the mcp_proxy_adapter branch raise, as it does outside a live server."""

    def _raise() -> None:
        raise RuntimeError("no adapter config in this test process")

    monkeypatch.setattr("mcp_proxy_adapter.config.get_config", _raise)


def _no_argv_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the argv --config lookup report nothing found."""
    monkeypatch.setattr(
        "code_analysis.core.server_log_dir.discover_config_path_from_argv",
        lambda _argv=None: None,
    )


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)


def test_prefers_adapter_config_when_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adapter's cfg.config_path wins when it points at a real file."""
    cfg_path = tmp_path / "adapter-config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "mcp_proxy_adapter.config.get_config",
        lambda: SimpleNamespace(config_path=str(cfg_path)),
    )
    # Lower-priority sources must not even matter here.
    _no_argv_config(monkeypatch)
    _clear_env(monkeypatch)

    assert BaseMCPCommand._resolve_config_path() == cfg_path.resolve()


def test_adapter_config_path_ignored_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale/nonexistent cfg.config_path falls through to the next source."""
    missing = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(
        "mcp_proxy_adapter.config.get_config",
        lambda: SimpleNamespace(config_path=str(missing)),
    )
    argv_cfg = tmp_path / "argv-config.json"
    monkeypatch.setattr(
        "code_analysis.core.server_log_dir.discover_config_path_from_argv",
        lambda _argv=None: argv_cfg,
    )
    _clear_env(monkeypatch)

    assert BaseMCPCommand._resolve_config_path() == argv_cfg.resolve()


def test_argv_config_used_when_adapter_config_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--config from argv is used when there is no live adapter config."""
    _no_adapter_config(monkeypatch)
    argv_cfg = tmp_path / "from-argv.json"
    monkeypatch.setattr(
        "code_analysis.core.server_log_dir.discover_config_path_from_argv",
        lambda _argv=None: argv_cfg,
    )
    _clear_env(monkeypatch)

    assert BaseMCPCommand._resolve_config_path() == argv_cfg.resolve()


def test_env_var_used_when_no_adapter_or_argv_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CASMGR_CONFIG is honored (even pointing at a not-yet-created file)."""
    _no_adapter_config(monkeypatch)
    _no_argv_config(monkeypatch)
    env_cfg = tmp_path / "env-config.json"
    monkeypatch.setenv("CASMGR_CONFIG", str(env_cfg))

    assert BaseMCPCommand._resolve_config_path() == env_cfg.resolve()


def test_env_var_relative_path_resolved_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative CASMGR_CONFIG value resolves against the current directory."""
    _no_adapter_config(monkeypatch)
    _no_argv_config(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CASMGR_CONFIG", "relative-config.json")

    assert (
        BaseMCPCommand._resolve_config_path()
        == (tmp_path / "relative-config.json").resolve()
    )


def test_system_default_used_when_present_and_nothing_higher_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/etc/casmgr/config.json is used when it exists and nothing else matched."""
    _no_adapter_config(monkeypatch)
    _no_argv_config(monkeypatch)
    _clear_env(monkeypatch)
    system_cfg = tmp_path / "etc-casmgr-config.json"
    system_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command._SYSTEM_DEFAULT_CONFIG",
        system_cfg,
    )

    assert BaseMCPCommand._resolve_config_path() == system_cfg.resolve()


def test_cwd_config_json_is_the_final_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When nothing else resolves, cwd/config.json is returned unconditionally."""
    _no_adapter_config(monkeypatch)
    _no_argv_config(monkeypatch)
    _clear_env(monkeypatch)
    monkeypatch.setattr(
        "code_analysis.commands.base_mcp_command._SYSTEM_DEFAULT_CONFIG",
        tmp_path / "no-such-system-config.json",
    )
    monkeypatch.chdir(tmp_path)

    assert BaseMCPCommand._resolve_config_path() == (tmp_path / "config.json").resolve()
