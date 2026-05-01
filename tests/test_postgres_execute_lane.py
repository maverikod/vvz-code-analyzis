# Classification for PostgreSQL execute pool lanes (read vs write).

from __future__ import annotations

from code_analysis.core.database_driver_pkg.drivers.postgres_execute_lane import (
    postgres_batch_requires_write_pool,
    postgres_execute_requires_write_pool,
)


def test_execute_select_is_read_lane() -> None:
    assert postgres_execute_requires_write_pool("SELECT 1") is False


def test_execute_with_select_is_read_lane() -> None:
    assert (
        postgres_execute_requires_write_pool(
            "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
        )
        is False
    )


def test_execute_insert_is_write_lane() -> None:
    assert postgres_execute_requires_write_pool("INSERT INTO a VALUES (1)") is True


def test_execute_batch_any_write_uses_write_lane() -> None:
    assert (
        postgres_batch_requires_write_pool(
            [("SELECT 1", None), ("UPDATE x SET y=1", None)]
        )
        is True
    )


def test_execute_batch_all_read_uses_read_lane() -> None:
    assert (
        postgres_batch_requires_write_pool([("SELECT 1", None), ("SELECT 2", None)])
        is False
    )


def test_execute_multistatement_write_detected() -> None:
    assert (
        postgres_execute_requires_write_pool("SELECT 1; DELETE FROM t WHERE id=1")
        is True
    )


def test_comment_stripped_before_classify() -> None:
    assert postgres_execute_requires_write_pool("-- hint\nSELECT 1") is False
