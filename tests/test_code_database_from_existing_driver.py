"""CodeDatabase.from_existing_driver driver-type resolution."""

from code_analysis.core.database import CodeDatabase
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgreSQLDriver
from code_analysis.core.database_driver_pkg.drivers.sqlite import SQLiteDriver


def test_from_existing_driver_postgres_sets_driver_type() -> None:
    driver = PostgreSQLDriver.__new__(PostgreSQLDriver)
    db = CodeDatabase.from_existing_driver(driver)
    assert db._driver_type == "postgres"
    assert db.driver_config.get("type") == "postgres"


def test_from_existing_driver_sqlite_rpc_sets_driver_type() -> None:
    driver = SQLiteDriver.__new__(SQLiteDriver)
    driver.db_path = None  # type: ignore[attr-defined]
    db = CodeDatabase.from_existing_driver(driver, {"type": "sqlite", "config": {}})
    assert db._driver_type == "sqlite"
