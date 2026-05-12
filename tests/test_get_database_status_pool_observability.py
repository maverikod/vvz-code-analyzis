"""Postgres in-process pool fields on get_database_status result."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from code_analysis.commands.worker_status_mcp_commands.get_database_status_build import (
    build_database_status_result,
)
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver


def _minimal_status_batch_results() -> List[Dict[str, Any]]:
    row0: Dict[str, Any] = {"data": [{"count": 0}]}
    empty_samples: Dict[str, Any] = {"data": []}
    # 0=count, 1=project rows, 2..13=counts, 14..16=file/chunk samples (must be [])
    return [row0, {"data": []}] + [row0] * 12 + [empty_samples] * 3


def test_postgres_in_process_adds_pool_in_use_when_enabled() -> None:
    driver = PostgreSQLDriver()

    def _pool_status() -> dict:
        return {
            "enabled": True,
            "write": {"capacity": 3, "in_use": 2, "idle": 1, "waiters": 0},
            "read": {"capacity": 2, "in_use": 1, "idle": 1, "waiters": 1},
        }

    driver.pool_status = _pool_status  # type: ignore[method-assign]

    rpc = SimpleNamespace(handlers=SimpleNamespace(driver=driver))

    class _FakeDB:
        rpc_client = rpc
        _driver_type = "postgres"
        driver_config = {"type": "postgres", "config": {}}

        def execute_batch(self, ops):  # noqa: ANN001, ANN201
            return _minimal_status_batch_results()

    result = build_database_status_result(
        _FakeDB(), Path("/nonexistent/pg"), driver_type="postgres"
    )
    assert result["vector_ann_backend"] == "pgvector"
    assert result["pg_write_pool_in_use"] == 2
    assert result["pg_write_pool_idle"] == 1
    assert result["pg_write_pool_waiters"] == 0
    assert result["pg_read_pool_in_use"] == 1
    assert result["pg_read_pool_idle"] == 1
    assert result["pg_read_pool_waiters"] == 1


def test_sqlite_driver_does_not_add_pg_pool_fields(tmp_path: Path) -> None:
    class _FakeDB:
        rpc_client = SimpleNamespace(handlers=None)

        def execute_batch(self, ops):  # noqa: ANN001, ANN201
            return _minimal_status_batch_results()

    result = build_database_status_result(
        _FakeDB(), tmp_path / "x.db", driver_type="sqlite_proxy"
    )
    assert "pg_write_pool_in_use" not in result
    assert "pg_read_pool_in_use" not in result


def test_postgres_pool_disabled_omits_in_use_fields() -> None:
    driver = PostgreSQLDriver()
    driver.pool_status = lambda: {"enabled": False}  # type: ignore[method-assign]
    rpc = SimpleNamespace(handlers=SimpleNamespace(driver=driver))

    class _FakeDB:
        rpc_client = rpc

        def execute_batch(self, ops):  # noqa: ANN001, ANN201
            return _minimal_status_batch_results()

    result = build_database_status_result(_FakeDB(), Path("/x"), driver_type="postgres")
    assert "pg_write_pool_in_use" not in result
    assert "pg_read_pool_in_use" not in result
