"""
Full-text SQL variant uses PostgreSQL ``tsvector``/``plainto_tsquery`` syntax
(driver-direct, stage 2: ``full_text_search`` takes a driver directly instead
of dispatching on ``DatabaseClient(..., driver_type=...)``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from unittest.mock import MagicMock

from code_analysis.core.database_driver_pkg.domain.search import full_text_search


def test_full_text_search_postgres_driver_uses_tsvector_sql() -> None:
    """Verify test full text search postgres driver uses tsvector sql."""
    driver = MagicMock()
    driver.execute.return_value = {"data": []}
    full_text_search(driver, "hello", "00000000-0000-0000-0000-000000000001")
    sql = driver.execute.call_args[0][0]
    assert "plainto_tsquery" in sql
    assert "to_tsvector" in sql
    assert "left(" in sql
    assert "'simple'" in sql or "simple" in sql

