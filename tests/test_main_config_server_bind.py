"""Tests for Hypercorn bind resolution in main_config."""

from __future__ import annotations

from argparse import Namespace

from code_analysis.core.settings_manager import SettingsManager
from code_analysis.main_config import resolve_server_bind


def test_resolve_server_bind_uses_config_port_not_settings_default() -> None:
    settings = SettingsManager()
    settings._cli_overrides = {}

    host, port = resolve_server_bind(
        args=Namespace(host=None, port=None),
        settings=settings,
        config_host="0.0.0.0",
        config_port=15010,
    )

    assert host == "0.0.0.0"
    assert port == 15010


def test_resolve_server_bind_cli_overrides_config() -> None:
    settings = SettingsManager()
    settings._cli_overrides = {}

    host, port = resolve_server_bind(
        args=Namespace(host="127.0.0.1", port=16000),
        settings=settings,
        config_host="0.0.0.0",
        config_port=15010,
    )

    assert host == "127.0.0.1"
    assert port == 16000


def test_resolve_server_bind_env_overrides_config() -> None:
    settings = SettingsManager()
    settings._cli_overrides = {"server_port": 17000, "server_host": "10.0.0.5"}

    host, port = resolve_server_bind(
        args=Namespace(host=None, port=None),
        settings=settings,
        config_host="0.0.0.0",
        config_port=15010,
    )

    assert host == "10.0.0.5"
    assert port == 17000
