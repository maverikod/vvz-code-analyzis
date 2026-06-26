"""Contract: driver kind + config when attaching to an existing packaged driver instance.

Mirrors factory-style resolution (driver class + explicit ``driver_config``) used when
:class:`~code_analysis.core.database_client.client.DatabaseClient` is constructed against
an already-open SQLite/Postgres packaged driver so ``driver_type`` and config blocks stay
consistent with :func:`~code_analysis.core.database_driver_pkg.driver_factory.create_driver`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock

from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver


def _resolve_existing_pkg_driver_facade(
    driver: Any, driver_config: Optional[Dict[str, Any]] = None
) -> Tuple[str, Dict[str, Any]]:
    """Derive normalized ``driver_type`` and ``driver_config`` from a live driver + optional override."""
    rpc_sqlite = SQLiteDriver

    db_path = getattr(driver, "db_path", None)
    if driver_config is None:
        if isinstance(driver, PostgreSQLDriver):
            driver_config = {"type": "postgres", "config": {}}
        elif db_path is not None:
            driver_config = {
                "type": "sqlite",
                "config": {"path": str(Path(db_path).resolve())},
            }
        else:
            driver_config = {"type": "sqlite", "config": {}}

    if isinstance(driver, PostgreSQLDriver):
        resolved_driver_type = "postgres"
    elif isinstance(driver, rpc_sqlite) or db_path is not None:
        resolved_driver_type = "sqlite"
    else:
        resolved_driver_type = str(driver_config.get("type") or "sqlite")

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


def test_existing_driver_sqlite_rpc_sets_driver_type_and_config_type() -> None:
    """Verify test existing driver sqlite rpc sets driver type and config type."""
    driver = SQLiteDriver.__new__(SQLiteDriver)
    driver.db_path = None
    explicit_cfg = {"type": "sqlite", "config": {}}

    resolved_dt, cfg = _resolve_existing_pkg_driver_facade(driver, explicit_cfg)

    rpc = MagicMock(name="rpc")
    client = DatabaseClient(rpc_client=rpc, driver_type=resolved_dt)

    assert resolved_dt == "sqlite"
    assert cfg.get("type") == "sqlite"
    assert client._driver_type == "sqlite"
