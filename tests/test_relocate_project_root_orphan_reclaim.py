"""``relocate_project_root_after_disk_move`` must not silently miss orphan rows.

Regression for planner card d216b9f9. A ``projects`` row can exist under a
different/rotated ``server_instance_id`` (orphan instance after a server
reinstall/rebind) while still being the same on-disk project.
``get_project``'s global-by-id fallback (see
tests/test_database_projects_get_project_global_fallback.py and
tests/test_insert_project_row_global_id.py) and the scoped-write reclaim helper
(see tests/test_scoped_project_write_orphan_reclaim.py, fixing
``sync_project_metadata_from_projectid``) already read/write
around this defect class elsewhere. ``relocate_project_root_after_disk_move``
previously had neither: its scoped "project not found" guard returned False
for a row that exists globally under a different server_instance_id, and its
final scoped UPDATE would have silently affected 0 rows even if that guard had
been bypassed.

The fix applies the same two remedies used elsewhere in this function:
- reads (the ``watch_dir_id`` lookup and the "project not found" guard) fall
  back to an unscoped global-by-id lookup when the scoped lookup misses.
- the final write reclaims the orphan row (reassigns ``server_instance_id`` to
  the current instance) and retries once, via the existing
  ``_reclaim_orphan_and_retry_scoped_projects_write`` /
  ``_reclaim_orphan_and_retry_scoped_write`` helpers - reused, not duplicated.

Covers both layers per the project's dual-layer driver-chain convention:
- ``code_analysis.core.database_client.client_api_projects`` (the RPC/production
  ``DatabaseClient`` layer - the layer the live file-watcher relocate call path
  actually invokes, see ``core/file_watcher_pkg/multi_project_worker_init.py``
  via ``create_worker_database_client``; primary test target).
- ``code_analysis.core.database.projects`` (the ``CodeDatabase`` driver leaf
  shared by sqlite+postgres per the project's driver-chain invariant).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from code_analysis.core.database import projects as leaf_projects_mod
from code_analysis.core.database_client.client_api_projects import (
    _ClientAPIProjectsMixin,
)

_SID = "server-current"
_OTHER_SID = "server-orphaned-from"


def _norm_su(sql: str) -> str:
    """Normalize whitespace and case for simple prefix/substring SQL matching."""
    return " ".join(sql.split()).upper()


# ─────────────────────────────────────────────────────────────────────────
# client_api_projects.py (RPC / production DatabaseClient layer)
# ─────────────────────────────────────────────────────────────────────────


class _FakeClientRelocateTable(_ClientAPIProjectsMixin):
    """In-memory ``projects`` table behind the real ``_ClientAPIProjectsMixin`` code.

    Implements only ``.execute()`` / ``.update()`` - the real public surface of
    ``DatabaseClient`` (it has no ``_fetchall``/``_execute`` privates).
    """

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
        """Route relocate's SELECTs/UPDATEs against the in-memory table."""
        p = tuple(params or ())
        self.execute_calls.append((sql, p))
        su = _norm_su(sql)

        if su.startswith("SELECT WATCH_DIR_ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"data": [{"watch_dir_id": row.get("watch_dir_id")}]}
            return {"data": []}
        if su.startswith("SELECT * FROM PROJECTS WHERE ID"):
            pid = p[0]
            row = self._rows.get(pid)
            return {"data": [dict(row)] if row is not None else []}
        if "ID != ?" in su:
            # "other project already at this path" conflict check - never
            # triggered in these tests (single project per scenario).
            return {"data": []}
        if su.startswith("SELECT ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"data": [{"id": pid}]}
            return {"data": []}
        if su.startswith("UPDATE PROJECTS SET ROOT_PATH") and "WATCH_DIR_ID" in su:
            new_stored, new_name, new_wd, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update(
                    {"root_path": new_stored, "name": new_name, "watch_dir_id": new_wd}
                )
                return {"affected_rows": 1}
            return {"affected_rows": 0}
        if su.startswith("UPDATE PROJECTS SET ROOT_PATH"):
            new_stored, new_name, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update({"root_path": new_stored, "name": new_name})
                return {"affected_rows": 1}
            return {"affected_rows": 0}
        if su.startswith("UPDATE PROJECTS SET WATCH_DIR_ID"):
            new_wd, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update({"watch_dir_id": new_wd})
                return {"affected_rows": 1}
            return {"affected_rows": 0}
        return {"data": [], "affected_rows": 0}

    def update(
        self, table_name: str, where: Dict[str, Any], data: Dict[str, Any]
    ) -> int:
        """Generic scoped UPDATE used by the reclaim helper (reassign server_instance_id)."""
        self.update_calls.append((table_name, dict(where), dict(data)))
        if table_name != "projects":
            return 0
        affected = 0
        for row in self._rows.values():
            if all(row.get(k) == v for k, v in where.items()):
                row.update(data)
                affected += 1
        return affected


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value=_SID,
)
def test_client_relocate_reclaims_orphan_row(_sid_mock: Any, tmp_path: Path) -> None:
    """Orphan row (different server_instance_id) -> reclaimed, then the move lands."""
    pid = "pid-relocate-orphan"
    old_root = (tmp_path / "old" / "proj").resolve()
    new_root = (tmp_path / "moved_proj").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    rows: Dict[str, Dict[str, Any]] = {
        pid: {
            "id": pid,
            "server_instance_id": _OTHER_SID,
            "root_path": str(old_root),
            "name": "proj",
            "watch_dir_id": None,
        }
    }
    client = _FakeClientRelocateTable(rows)

    result = client.relocate_project_root_after_disk_move(
        pid, str(old_root), str(new_root)
    )

    assert result is True
    assert rows[pid]["server_instance_id"] == _SID
    assert Path(rows[pid]["root_path"]).resolve() == new_root
    assert rows[pid]["name"] == new_root.name
    assert any(
        call[1].get("id") == pid and call[2].get("server_instance_id") == _SID
        for call in client.update_calls
    ), f"expected a reclaim UPDATE via self.update; got {client.update_calls}"


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value=_SID,
)
def test_client_relocate_normal_write_unaffected(
    _sid_mock: Any, tmp_path: Path
) -> None:
    """Row already owned by the current server instance -> single write, no reclaim."""
    pid = "pid-relocate-normal"
    old_root = (tmp_path / "old" / "proj2").resolve()
    new_root = (tmp_path / "moved_proj2").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    rows: Dict[str, Dict[str, Any]] = {
        pid: {
            "id": pid,
            "server_instance_id": _SID,
            "root_path": str(old_root),
            "name": "proj2",
            "watch_dir_id": None,
        }
    }
    client = _FakeClientRelocateTable(rows)

    result = client.relocate_project_root_after_disk_move(
        pid, str(old_root), str(new_root)
    )

    assert result is True
    assert Path(rows[pid]["root_path"]).resolve() == new_root
    assert client.update_calls == []  # no reclaim - the scoped write matched directly


@patch(
    "code_analysis.core.database_client.client_api_projects.current_server_instance_id",
    return_value=_SID,
)
def test_client_relocate_row_absent_globally_returns_false(
    _sid_mock: Any, tmp_path: Path
) -> None:
    """Project id not present anywhere -> False, no error, no reclaim attempted."""
    pid = "pid-relocate-missing"
    old_root = (tmp_path / "old" / "proj3").resolve()
    new_root = (tmp_path / "moved_proj3").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    client = _FakeClientRelocateTable({})

    result = client.relocate_project_root_after_disk_move(
        pid, str(old_root), str(new_root)
    )

    assert result is False
    assert client.update_calls == []  # no reclaim attempted; row never existed


# ─────────────────────────────────────────────────────────────────────────
# core/database/projects.py (CodeDatabase driver leaf, shared sqlite+postgres)
# ─────────────────────────────────────────────────────────────────────────


class _FakeLeafRelocateSelf:
    """Minimal ``self`` stand-in for the ``CodeDatabase``-bound leaf function."""

    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        """Seed the fake table; ``rows`` is mutated in place by writes."""
        self._rows = rows
        self._last_execute_result: Dict[str, Any] = {}
        self.execute_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        """Route relocate's SELECTs against the in-memory table."""
        p = tuple(params or ())
        su = _norm_su(sql)
        if su.startswith("SELECT WATCH_DIR_ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"watch_dir_id": row.get("watch_dir_id")}
            return None
        if su.startswith("SELECT WATCH_DIR_ID FROM PROJECTS WHERE ID"):
            pid = p[0]
            row = self._rows.get(pid)
            return (
                {"watch_dir_id": row.get("watch_dir_id")} if row is not None else None
            )
        if "ID != ?" in su:
            return None
        if su.startswith("SELECT ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"id": pid}
            return None
        if su.startswith("SELECT ID FROM PROJECTS WHERE ID"):
            pid = p[0]
            row = self._rows.get(pid)
            return {"id": pid} if row is not None else None
        if su.startswith("SELECT SERVER_INSTANCE_ID FROM PROJECTS WHERE ID"):
            pid = p[0]
            row = self._rows.get(pid)
            return (
                {"server_instance_id": row["server_instance_id"]}
                if row is not None
                else None
            )
        return None

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        """Route relocate's UPDATEs against the in-memory table."""
        p = tuple(params or ())
        self.execute_calls.append((sql, p))
        su = _norm_su(sql)
        if su.startswith("UPDATE PROJECTS SET SERVER_INSTANCE_ID"):
            new_sid, pid = p
            row = self._rows.get(pid)
            if row is not None:
                row["server_instance_id"] = new_sid
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        if su.startswith("UPDATE PROJECTS SET ROOT_PATH") and "WATCH_DIR_ID" in su:
            new_stored, new_name, new_wd, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update(
                    {"root_path": new_stored, "name": new_name, "watch_dir_id": new_wd}
                )
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        if su.startswith("UPDATE PROJECTS SET ROOT_PATH"):
            new_stored, new_name, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update({"root_path": new_stored, "name": new_name})
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        if su.startswith("UPDATE PROJECTS SET WATCH_DIR_ID"):
            new_wd, sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                row.update({"watch_dir_id": new_wd})
                self._last_execute_result = {"affected_rows": 1}
            else:
                self._last_execute_result = {"affected_rows": 0}
            return
        self._last_execute_result = {"affected_rows": 0}

    def _commit(self) -> None:
        """No-op commit for the fake driver."""
        return None


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_relocate_reclaims_orphan_row(_sid_mock: Any, tmp_path: Path) -> None:
    """Leaf relocate reclaims an orphan row on 0-row scoped no-op."""
    pid = "leaf-relocate-orphan"
    old_root = (tmp_path / "old" / "proj").resolve()
    new_root = (tmp_path / "moved_proj").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    rows: Dict[str, Dict[str, Any]] = {
        pid: {
            "id": pid,
            "server_instance_id": _OTHER_SID,
            "root_path": str(old_root),
            "name": "proj",
            "watch_dir_id": None,
        }
    }
    fake_self = _FakeLeafRelocateSelf(rows)

    result = leaf_projects_mod.relocate_project_root_after_disk_move(
        fake_self, pid, str(old_root), str(new_root)
    )

    assert result is True
    assert rows[pid]["server_instance_id"] == _SID
    assert Path(rows[pid]["root_path"]).resolve() == new_root
    assert rows[pid]["name"] == new_root.name


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_relocate_normal_write_unaffected(_sid_mock: Any, tmp_path: Path) -> None:
    """Leaf: row already owned by the current instance -> single write, no reclaim."""
    pid = "leaf-relocate-normal"
    old_root = (tmp_path / "old" / "proj2").resolve()
    new_root = (tmp_path / "moved_proj2").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    rows: Dict[str, Dict[str, Any]] = {
        pid: {
            "id": pid,
            "server_instance_id": _SID,
            "root_path": str(old_root),
            "name": "proj2",
            "watch_dir_id": None,
        }
    }
    fake_self = _FakeLeafRelocateSelf(rows)

    result = leaf_projects_mod.relocate_project_root_after_disk_move(
        fake_self, pid, str(old_root), str(new_root)
    )

    assert result is True
    assert Path(rows[pid]["root_path"]).resolve() == new_root
    # No reclaim UPDATE issued (only the direct scoped UPDATE runs).
    assert not any(
        _norm_su(sql).startswith("UPDATE PROJECTS SET SERVER_INSTANCE_ID")
        for sql, _ in fake_self.execute_calls
    )


@patch(
    "code_analysis.core.database.projects.current_server_instance_id",
    return_value=_SID,
)
def test_leaf_relocate_row_absent_globally_returns_false(
    _sid_mock: Any, tmp_path: Path
) -> None:
    """Leaf: project id not present anywhere -> False, no reclaim attempted."""
    pid = "leaf-relocate-missing"
    old_root = (tmp_path / "old" / "proj3").resolve()
    new_root = (tmp_path / "moved_proj3").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    fake_self = _FakeLeafRelocateSelf({})

    result = leaf_projects_mod.relocate_project_root_after_disk_move(
        fake_self, pid, str(old_root), str(new_root)
    )

    assert result is False
    assert not any(
        _norm_su(sql).startswith("UPDATE PROJECTS SET SERVER_INSTANCE_ID")
        for sql, _ in fake_self.execute_calls
    )
