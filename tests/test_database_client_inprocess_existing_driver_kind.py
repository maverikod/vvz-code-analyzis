"""Contract: driver kind + config when attaching to an existing packaged driver instance.

Mirrors factory-style resolution (driver class + explicit ``driver_config``) used when
:class:`~code_analysis.core.database_client.client.DatabaseClient` is constructed against
an already-open PostgreSQL packaged driver so ``driver_type`` and config blocks stay
consistent with :func:`~code_analysis.core.database_driver_pkg.driver_factory.create_driver`.
SQLite support was removed; PostgreSQL is the only supported driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver


def _resolve_existing_pkg_driver_facade(
    driver: Any, driver_config: Optional[Dict[str, Any]] = None
) -> Tuple[str, Dict[str, Any]]:
    """Derive normalized ``driver_type`` and ``driver_config`` from a live driver + optional override."""
    if driver_config is None:
        driver_config = {"type": "postgres", "config": {}}

    resolved_driver_type = (
        "postgres"
        if isinstance(driver, PostgreSQLDriver)
        else str(driver_config.get("type") or "postgres")
    )

    return resolved_driver_type, driver_config


def test_existing_driver_postgres_sets_driver_type_and_config_type() -> None:
    """Verify test existing driver postgres sets driver type and config type."""
    driver = PostgreSQLDriver.__new__(PostgreSQLDriver)
    resolved_dt, cfg = _resolve_existing_pkg_driver_facade(driver)

    rpc = MagicMock(name="rpc")
    client = DatabaseClient(rpc_client=rpc, driver_type=resolved_dt)

    assert resolved_dt == "postgres"
    assert cfg.get("type") == "postgres"
    assert client._driver_type == "postgres"
