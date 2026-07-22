"""Scoped ``projects`` writes must reclaim orphan rows instead of silently no-op'ing.

Regression for planner card 291e61e2. A ``projects`` row can exist under a
different/rotated ``server_instance_id`` (orphan instance after a server
reinstall/rebind) while still being the same on-disk project.
``get_project`` already finds such rows via its global-by-id fallback
(``_project_row_by_id_global`` / see tests/test_database_projects_get_project_global_fallback.py
and tests/test_insert_project_row_global_id.py), so callers reasonably believe
the project exists. But a *scoped write* (``WHERE server_instance_id = ? AND
id = ?``) against that same row previously matched 0 rows and returned
successfully with no error and no effect - a silent no-op.

The fix (``_reclaim_orphan_and_retry_scoped_projects_write`` /
``_reclaim_orphan_and_retry_scoped_write``): when a scoped write affects 0 rows
AND a global-by-id row exists under a *different* server_instance_id, reclaim
the row to the current server_instance_id (same semantics as
``insert_project_row``'s orphan reclaim) and retry the write once.

Covers both call sites the fix touched:
- ``code_analysis.core.database_driver_pkg.domain.projects`` (driver-direct
  free function, stage 2 layer collapse: ``sync_project_metadata_from_projectid``).
  It originally also covered ``update_project``, but that method was deleted as
  dead code (stage 2 dead-code cleanup, sub-step A1; zero production callers)
  along with its dedicated tests here.
- ``code_analysis.core.database.projects`` (the ``CodeDatabase`` driver leaf
  shared by sqlite+postgres per the project's driver-chain invariant:
  ``sync_project_metadata_from_projectid``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from code_analysis.core.database import projects as leaf_projects_mod
from code_analysis.core.database_driver_pkg.domain.projects import (
    sync_project_metadata_from_projectid,
)

_SID = "server-current"
_OTHER_SID = "server-orphaned-from"


# ─────────────────────────────────────────────────────────────────────────
# database_driver_pkg/domain/projects.py (driver-direct free function, stage 2)
# ─────────────────────────────────────────────────────────────────────────


class _FakeProjectsTable:
    """In-memory ``projects`` table behind the real driver-direct free function."""

    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        """Seed the fake table; ``rows`` is mutated in place by writes."""
        self.rpc_client = MagicMock()
        self._rows = rows
        self.execute_calls: List[Tuple[str, Tuple[Any, ...]]] = []
        self.update_calls: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Route SELECTs / the raw sync UPDATE against the in-memory table."""
        p = tuple(params or ())
        self.execute_calls.append((sql, p))
        s_upper = sql.strip().upper()
        if s_upper.startswith("SELECT") and "WHERE ID = ?" in s_upper:
            row = self._rows.get(p[0])
            return {"data": [dict(row)] if row else []}
        if s_upper.startswith("UPDATE PROJECTS") and "SET DELETED" in s_upper:
            deleted, paused, comment, sid, project_id = p
            row = self._rows.get(project_id)
            if row is not None and row.get("server_instance_id") == sid:
                row.update(
                    {
                        "deleted": deleted,
                        "processing_paused": paused,
                        "comment": comment,
                    }
                )
                return {"affected_rows": 1, "data": None}
            return {"affected_rows": 0, "data": None}
        return {"affected_rows": 0, "data": []}

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
        *,
        priority: int = 0,
    ) -> List[Dict[str, Any]]:
        """Scoped select used by ``get_project``'s first (server_instance_id, id) lookup."""
        if table_name != "projects" or not where:
            return []
        row = self._rows.get(where.get("id"))
        if row is None:
            return []
        if (
            "server_instance_id" in where
            and row.get("server_instance_id") != where["server_instance_id"]
        ):
            return []
        return [dict(row)]

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Generic scoped UPDATE used by the reclaim helper."""
        self.update_calls.append((table_name, dict(where), dict(data)))
        if table_name != "projects":
            return 0
        affected = 0
        for row in self._rows.values():
            if all(row.get(k) == v for k, v in where.items()):
                row.update(data)
                affected += 1
        return affected


def _enrich_identity(row: Dict[str, Any], _db: Any) -> Dict[str, Any]:
    """Return enrich identity."""
    return dict(row)


@patch(
    "code_analysis.core.database_driver_pkg.domain.projects.current_server_instance_id",
    return_value=_SID,
)
@patch(
    "code_analysis.core.database_driver_pkg.domain.projects.enrich_project_dict_resolve_root_path",
    side_effect=_enrich_identity,
)
def test_sync_project_metadata_reclaims_orphan_row(
    _enrich_mock: Any, _sid_mock: Any, tmp_path: Any
) -> None:
    """Orphan row (different server_instance_id) -> reclaimed, then the write lands."""
    pid = "pid-orphan"
    rows = {
        pid: {
            "id": pid,
            "server_instance_id": _OTHER_SID,
            "root_path": "proj",
            "name": "proj",
            "comment": None,
            "watch_dir_id": None,
            "deleted": False,
            "processing_paused": False,
        }
    }
    client = _FakeProjectsTable(rows)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "projectid").write_text(
        f'{{"project_id": "{pid}", "deleted": true, "processing_paused": false, '
        '"description": "trashed"}}\n',
        encoding="utf-8",
    )

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "trashed"
        load_info_mock.return_value = info

        result = sync_project_metadata_from_projectid(client, str(project_dir))

    assert result == pid
    # Reclaimed to the current server instance and the sync write actually landed.
    assert rows[pid]["server_instance_id"] == _SID
    assert rows[pid]["deleted"] is True
    assert rows[pid]["comment"] == "trashed"
    assert any(
        call[1].get("id") == pid and call[2].get("server_instance_id") == _SID
        for call in client.update_calls
    ), f"expected a reclaim UPDATE via self.update; got {client.update_calls}"


@patch(
    "code_analysis.core.database_driver_pkg.domain.projects.current_server_instance_id",
    return_value=_SID,
)
def test_sync_project_metadata_row_absent_globally_unchanged(
    _sid_mock: Any, tmp_path: Any
) -> None:
    """Project id not present anywhere -> still a no-op, no error, no reclaim attempt."""
    pid = "pid-does-not-exist"
    client = _FakeProjectsTable({})

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = None
        load_info_mock.return_value = info

        result = sync_project_metadata_from_projectid(client, str(project_dir))

    assert result == pid
    assert client.update_calls == []  # no reclaim attempted; row never existed


@patch(
    "code_analysis.core.database_driver_pkg.domain.projects.current_server_instance_id",
    return_value=_SID,
)
def test_sync_project_metadata_normal_write_unaffected(
    _sid_mock: Any, tmp_path: Any
) -> None:
    """Row already owned by the current server instance -> single write, no reclaim."""
    pid = "pid-normal"
    rows = {
        pid: {
            "id": pid,
            "server_instance_id": _SID,
            "root_path": "proj",
            "name": "proj",
            "comment": None,
            "watch_dir_id": None,
            "deleted": False,
            "processing_paused": False,
        }
    }
    client = _FakeProjectsTable(rows)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "ok"
        load_info_mock.return_value = info

        result = sync_project_metadata_from_projectid(client, str(project_dir))

    assert result == pid
    assert rows[pid]["deleted"] is True
    assert rows[pid]["comment"] == "ok"
    assert client.update_calls == []  # no reclaim - the scoped write matched directly


# ─────────────────────────────────────────────────────────────────────────
# core/database/projects.py (CodeDatabase driver leaf, shared sqlite+postgres)
# ─────────────────────────────────────────────────────────────────────────


class _FakeDriverSelf:
    """Minimal ``self`` stand-in for the ``CodeDatabase``-bound leaf functions.

    Mirrors tests/test_database_projects_get_project_global_fallback.py's fake,
    extended with an in-memory ``projects`` table so ``_execute`` can report a
    realistic ``affected_rows`` (as ``CodeDatabase._execute`` does via
    ``self._last_execute_result``, see core/database/base.py).
    """

    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        """Seed the fake table; ``rows`` is mutated in place by writes."""
        self._rows = rows
        self._last_execute_result: Dict[str, Any] = {}
        self.execute_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Simulate the two UPDATE statements the leaf's sync function issues."""
        p = tuple(params or ())
        self.execute_calls.append((sql, p))
        s_upper = sql.strip().upper()
        if s_upper.startswith("UPDATE PROJECTS SET SERVER_INSTANCE_ID"):
            new_sid, project_id = p
            row = self._rows.get(project_id)
            if row is not None:
                row["server_instance_id"] = new_sid
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        if s_upper.startswith("UPDATE PROJECTS") and "SET DELETED" in s_upper:
            deleted, paused, comment, sid, project_id = p
            row = self._rows.get(project_id)
            if row is not None and row.get("server_instance_id") == sid:
                row.update(
                    {
                        "deleted": deleted,
                        "processing_paused": paused,
                        "comment": comment,
                    }
                )
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        self._last_execute_result = {"affected_rows": 0}

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Return the global-by-id row (the only SELECT the leaf issues here)."""
        p = tuple(params or ())
        if (
            "SELECT server_instance_id FROM projects WHERE id = ?".upper()
            in sql.upper()
        ):
            row = self._rows.get(p[0])
            return {"server_instance_id": row["server_instance_id"]} if row else None
        return None

    def _commit(self) -> None:
        """No-op commit for the fake driver."""
        return None


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_sync_project_metadata_reclaims_orphan_row(
    _sid_mock: Any, tmp_path: Any
) -> None:
    """Leaf sync_project_metadata_from_projectid reclaims an orphan row on 0-row no-op."""
    pid = "leaf-pid-orphan"
    rows = {
        pid: {
            "id": pid,
            "server_instance_id": _OTHER_SID,
            "deleted": False,
            "processing_paused": False,
            "comment": None,
        }
    }
    fake_self = _FakeDriverSelf(rows)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "trashed"
        load_info_mock.return_value = info

        result = leaf_projects_mod.sync_project_metadata_from_projectid(
            fake_self, str(project_dir)
        )

    assert result == pid
    assert rows[pid]["server_instance_id"] == _SID
    assert rows[pid]["deleted"] is True
    assert rows[pid]["comment"] == "trashed"
    # scoped write (miss) -> global lookup -> reclaim UPDATE -> scoped write (retry, hit)
    assert len(fake_self.execute_calls) == 3


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_sync_project_metadata_row_absent_globally_unchanged(
    _sid_mock: Any, tmp_path: Any
) -> None:
    """Leaf: project id not present anywhere -> single failed write, no reclaim, no error."""
    pid = "leaf-pid-missing"
    fake_self = _FakeDriverSelf({})

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = None
        load_info_mock.return_value = info

        result = leaf_projects_mod.sync_project_metadata_from_projectid(
            fake_self, str(project_dir)
        )

    assert result == pid
    # scoped write (miss) -> global lookup (miss) -> stop, no reclaim attempted
    assert len(fake_self.execute_calls) == 1


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_sync_project_metadata_normal_write_unaffected(
    _sid_mock: Any, tmp_path: Any
) -> None:
    """Leaf: row already owned by the current instance -> single write, no reclaim."""
    pid = "leaf-pid-normal"
    rows = {
        pid: {
            "id": pid,
            "server_instance_id": _SID,
            "deleted": False,
            "processing_paused": False,
            "comment": None,
        }
    }
    fake_self = _FakeDriverSelf(rows)

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch(
        "code_analysis.core.project_resolution.load_project_info"
    ) as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "ok"
        load_info_mock.return_value = info

        result = leaf_projects_mod.sync_project_metadata_from_projectid(
            fake_self, str(project_dir)
        )

    assert result == pid
    assert rows[pid]["deleted"] is True
    assert rows[pid]["comment"] == "ok"
    assert len(fake_self.execute_calls) == 1  # direct hit, no reclaim
