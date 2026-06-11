"""Tests for mcp-proxy-adapter log directory bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def test_install_redirects_adapter_logs(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / "casmgr-logs"
    monkeypatch.setenv("CASMGR_LOG", str(log_dir))
    monkeypatch.delenv("CASMGR_CONFIG", raising=False)

    for name in list(sys.modules):
        if name == "mcp_proxy_adapter" or name.startswith("mcp_proxy_adapter."):
            del sys.modules[name]
    if "code_analysis.mcp_adapter_bootstrap" in sys.modules:
        del sys.modules["code_analysis.mcp_adapter_bootstrap"]

    import code_analysis.mcp_adapter_bootstrap as bootstrap

    bootstrap._PATCHED = False
    if hasattr(os, "_ca_log_dir_hooks"):
        delattr(os, "_ca_log_dir_hooks")
    bootstrap.install_mcp_adapter_log_dir()

    from mcp_proxy_adapter.commands.command_registry import registry  # noqa: F401

    assert log_dir.is_dir()
    assert (log_dir / "mcp_proxy_adapter.log").exists() or any(log_dir.iterdir())
