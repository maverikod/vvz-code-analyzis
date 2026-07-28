"""
Pytest fixtures for MCP commands testing.

Provides common fixtures for testing MCP commands with DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

TEST_SERVER_INSTANCE_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _partition_tests_by_server_instance_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """All DB queries in tests use a fixed server instance partition key."""

    def _sid(**_kwargs: object) -> str:
        """Return sid."""
        return TEST_SERVER_INSTANCE_ID

    monkeypatch.setattr(
        "code_analysis.core.server_instance.get_server_instance_id",
        _sid,
    )
    monkeypatch.setattr(
        "code_analysis.core.database.watch_dirs_partition.current_server_instance_id",
        _sid,
    )


@pytest.fixture(autouse=True)
def _isolate_git_xdg_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Keep subprocess git tests independent from inaccessible user config."""

    xdg_root = Path(tmp_path_factory.mktemp("git-xdg"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_root))


def pytest_configure(config) -> None:
    """Register custom marks."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration (slower, real DB/driver).",
    )
    config.addinivalue_line(
        "markers",
        "postgres: optional live PostgreSQL (e.g. CODE_ANALYSIS_POSTGRES_TEST_DSN).",
    )
