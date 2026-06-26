"""
Full-text SQL variant follows ``DatabaseClient(..., driver_type=...)`` from config,
not runtime DB version probing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from unittest.mock import MagicMock, patch

from code_analysis.core.database_client.client import DatabaseClient


def test_full_text_search_postgres_driver_uses_tsvector_sql() -> None:
    """Verify test full text search postgres driver uses tsvector sql."""
    client = DatabaseClient(rpc_client=MagicMock(), driver_type="postgres")
    with patch.object(client, "execute", return_value={"data": []}) as ex:
        client.full_text_search("hello", "00000000-0000-0000-0000-000000000001")
    sql = ex.call_args[0][0]
    assert "plainto_tsquery" in sql
    assert "to_tsvector" in sql
    assert "left(" in sql
    assert "'simple'" in sql or "simple" in sql


def test_full_text_search_sqlite_driver_uses_fts5() -> None:
    """Verify test full text search sqlite driver uses fts5."""
    client = DatabaseClient(rpc_client=MagicMock(), driver_type="sqlite_proxy")
    with patch.object(client, "execute", return_value={"data": []}) as ex:
        client.full_text_search("hello", "00000000-0000-0000-0000-000000000001")
    sql = ex.call_args[0][0]
    assert "code_content_fts" in sql
    assert "bm25" in sql


def test_full_text_search_default_driver_assumes_sqlite_fts5() -> None:
    """Verify test full text search default driver assumes sqlite fts5."""
    client = DatabaseClient(rpc_client=MagicMock())
    with patch.object(client, "execute", return_value={"data": []}) as ex:
        client.full_text_search("hello", "00000000-0000-0000-0000-000000000001")
    sql = ex.call_args[0][0]
    assert "code_content_fts" in sql
