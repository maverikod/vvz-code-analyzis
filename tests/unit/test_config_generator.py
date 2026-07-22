"""Unit tests for CodeAnalysisConfigGenerator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_analysis.core.config_generator import CodeAnalysisConfigGenerator
from code_analysis.core.constants import DEFAULT_SERVER_PORT
from code_analysis.core.search_session.policy import (
    SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    SEARCH_SESSION_TTL_SECONDS_DEFAULT,
)


@pytest.fixture()
def generator() -> CodeAnalysisConfigGenerator:
    """Return generator."""
    return CodeAnalysisConfigGenerator()


def test_generate_default_port_and_code_analysis_sections(
    generator: CodeAnalysisConfigGenerator, tmp_path: Path
) -> None:
    """Verify test generate default port and code analysis sections."""
    out = tmp_path / "config.json"
    path = generator.generate(protocol="https", out_path=str(out))
    assert path == str(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["server"]["port"] == DEFAULT_SERVER_PORT
    assert data["code_analysis"]["port"] == DEFAULT_SERVER_PORT
    assert data["code_analysis"]["search_session"] == {
        "ttl_seconds": SEARCH_SESSION_TTL_SECONDS_DEFAULT,
        "max_block_size_bytes": SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    }
    assert data["code_analysis"]["docs_indexing"]["enabled"] is False
    assert data["client"]["protocol"] == "https"
    assert data["server_validation"]["protocol"] == "https"


def test_generate_with_proxy_defaults_registration(
    generator: CodeAnalysisConfigGenerator, tmp_path: Path
) -> None:
    """Verify test generate with proxy defaults registration."""
    out = tmp_path / "config.json"
    generator.generate(
        protocol="https",
        with_proxy=True,
        out_path=str(out),
        registration_server_id="my-server",
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    reg = data["registration"]
    assert reg["enabled"] is True
    assert reg["server_id"] == "my-server"
    assert reg["protocol"] == "https"
    assert reg["instance_uuid"]


def test_generate_postgres_driver_and_queue_overrides(
    generator: CodeAnalysisConfigGenerator, tmp_path: Path
) -> None:
    """Verify test generate postgres driver and queue overrides."""
    out = tmp_path / "config.json"
    generator.generate(
        protocol="https",
        out_path=str(out),
        code_analysis_driver_type="postgres",
        code_analysis_pg_user="code_analysis",
        code_analysis_pg_password_env="CODE_ANALYSIS_POSTGRES_PASSWORD",
        queue_max_concurrent=3,
        queue_retention_seconds=3600,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    driver = data["code_analysis"]["database"]["driver"]
    assert driver["type"] == "postgres"
    assert driver["config"]["user"] == "code_analysis"
    assert driver["config"]["password_env"] == "CODE_ANALYSIS_POSTGRES_PASSWORD"
    assert data["queue_manager"]["max_concurrent_jobs"] == 3
    assert data["queue_manager"]["completed_job_retention_seconds"] == 3600
