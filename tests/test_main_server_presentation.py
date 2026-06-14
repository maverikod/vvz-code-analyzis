"""Tests for server title/description/version resolution from config."""

from __future__ import annotations

from code_analysis.main_server_presentation import (
    resolve_server_presentation,
    sync_registration_presentation,
)


def test_resolve_from_server_presentation() -> None:
    app_config = {
        "server_presentation": {
            "title": "My Server",
            "description": "Custom description",
            "version": "2.3.4",
        },
        "registration": {"server_id": "code-analysis-server"},
    }
    title, description, version = resolve_server_presentation(app_config)
    assert title == "My Server"
    assert description == "Custom description"
    assert version == "2.3.4"


def test_sync_registration_for_proxy() -> None:
    app_config = {
        "server_presentation": {
            "title": "My Server",
            "description": "For proxy",
            "version": "9.9.9",
        },
        "registration": {"server_id": "code-analysis-server", "enabled": True},
    }
    sync_registration_presentation(app_config)
    reg = app_config["registration"]
    assert reg["metadata"]["description"] == "For proxy"
    assert reg["metadata"]["version"] == "9.9.9"
    assert reg["metadata"]["server_name"] == "My Server"
    assert reg["description"] == "For proxy"
    assert reg["server_name"] == "My Server"


def test_sync_registration_reachable_host_overrides_wildcard_bind() -> None:
    app_config = {
        "server": {
            "host": "0.0.0.0",
            "port": 15010,
            "advertised_host": "192.168.254.28",
        },
        "registration": {"server_id": "code-analysis-server", "metadata": {}},
    }
    sync_registration_presentation(app_config)
    meta = app_config["registration"]["metadata"]
    assert meta["host"] == "192.168.254.28"
    assert meta["port"] == 15010
