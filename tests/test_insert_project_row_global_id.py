"""insert_project_row: global id lookup and orphan reclaim via DatabaseClient RPC."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_client.client_api_projects import (
    _ClientAPIProjectsMixin,
    _project_row_by_id_global,
)


class _ProjectsClient(_ClientAPIProjectsMixin):
    """Represent ProjectsClient."""

    def __init__(self) -> None:
        """Initialize the instance."""
        self.rpc_client = MagicMock()
        self._execute_calls: List[Tuple[str, tuple[Any, ...]]] = []

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Execute the command."""
        self._execute_calls.append((sql, params or ()))
        return {"data": []}


def test_project_row_by_id_global_parses_execute_result() -> None:
    """Verify test project row by id global parses execute result."""
    client = _ProjectsClient()

    def _exec(
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Return exec."""
        return {
            "data": [
                {
                    "id": "pid-1",
                    "server_instance_id": None,
                    "root_path": "vast_srv",
                }
            ]
        }

    client.execute = _exec  # type: ignore[method-assign]
    row = _project_row_by_id_global(client, "pid-1")
    assert row is not None
    assert row["root_path"] == "vast_srv"


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value="server-b",
)
@patch(
    "code_analysis.core.database_client.client_api_projects.sql_julian_timestamp_now_expr",
    return_value="julianday('now')",
)
def test_insert_project_row_reclaims_orphan_without_insert(
    _now_mock: MagicMock,
    _sid_mock: MagicMock,
) -> None:
    """Verify test insert project row reclaims orphan without insert."""
    client = _ProjectsClient()
    client.get_project = MagicMock(return_value=None)  # type: ignore[method-assign]

    def _exec(
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Return exec."""
        client._execute_calls.append((sql, params or ()))
        if "FROM projects WHERE id =" in sql:
            return {
                "data": [
                    {
                        "id": "pid-1",
                        "server_instance_id": None,
                        "root_path": "old",
                    }
                ]
            }
        return {"data": []}

    client.execute = _exec  # type: ignore[method-assign]
    client.insert_project_row(
        "pid-1",
        "vast_srv",
        "vast_srv",
        comment="AI Admin",
        watch_dir_id="wd-1",
    )
    sqls = [c[0] for c in client._execute_calls]
    assert any("UPDATE projects" in s for s in sqls)
    assert not any("INSERT INTO projects" in s for s in sqls)


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value="server-b",
)
@patch(
    "code_analysis.core.database_client.client_api_projects.sql_julian_timestamp_now_expr",
    return_value="julianday('now')",
)
def test_insert_project_row_reassigns_same_disk_root_from_other_instance(
    _now_mock: MagicMock,
    _sid_mock: MagicMock,
) -> None:
    """Verify test insert project row reassigns same disk root from other instance."""
    client = _ProjectsClient()
    client.get_project = MagicMock(return_value=None)  # type: ignore[method-assign]
    root = "/home/vasilyvz/projects/tools/vast_srv"

    def _exec(
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Return exec."""
        client._execute_calls.append((sql, params or ()))
        if "FROM projects WHERE id =" in sql:
            return {
                "data": [
                    {
                        "id": "pid-1",
                        "server_instance_id": "server-a",
                        "root_path": "vast_srv",
                        "watch_dir_id": "wd-old",
                        "name": "vast_srv",
                    }
                ]
            }
        return {"data": []}

    client.execute = _exec  # type: ignore[method-assign]

    with patch(
        "code_analysis.core.database_client.client_api_projects.resolve_project_root_absolute_str",
        side_effect=lambda **_kw: root,
    ):
        client.insert_project_row(
            "pid-1",
            "vast_srv",
            "vast_srv",
            watch_dir_id="wd-new",
        )

    sqls = [c[0] for c in client._execute_calls]
    assert any("UPDATE projects" in s and "server_instance_id = ?" in s for s in sqls)
    assert not any("INSERT INTO projects" in s for s in sqls)


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value="server-b",
)
@patch(
    "code_analysis.core.database_client.client_api_projects.sql_julian_timestamp_now_expr",
    return_value="julianday('now')",
)
def test_insert_project_row_rejects_id_on_other_server_instance(
    _now_mock: MagicMock,
    _sid_mock: MagicMock,
) -> None:
    """Verify test insert project row rejects id on other server instance."""
    client = _ProjectsClient()
    client.get_project = MagicMock(return_value=None)  # type: ignore[method-assign]

    def _exec(
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Return exec."""
        if "FROM projects WHERE id =" in sql:
            return {
                "data": [
                    {
                        "id": "pid-1",
                        "server_instance_id": "server-a",
                        "root_path": "other_dir",
                    }
                ]
            }
        return {"data": []}

    def _resolve(**kw: Any) -> str:
        """Return resolve."""
        stored = str(kw.get("root_path_stored") or "")
        if stored == "other_dir":
            return "/other/project"
        return "/home/vast_srv"

    client.execute = _exec  # type: ignore[method-assign]
    with patch(
        "code_analysis.core.database_client.client_api_projects.resolve_project_root_absolute_str",
        side_effect=_resolve,
    ):
        with pytest.raises(ValueError, match="server_instance_id=server-a"):
            client.insert_project_row("pid-1", "vast_srv", "vast_srv")
