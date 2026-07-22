"""
Pytest fixtures for MCP commands testing.

Provides common fixtures for testing MCP commands with DatabaseClient.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

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
