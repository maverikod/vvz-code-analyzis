"""
Conscience Condition 7 acceptance gate: driver-direct ``domain/projects.py``
orphan-reclaim / global-fallback parity (stage 2 layer collapse, Block B, Part 1).

Ports the assertions of the four pre-existing orphan-reclaim/global-fallback
regression tests (test_insert_project_row_global_id.py,
test_database_projects_get_project_global_fallback.py,
test_scoped_project_write_orphan_reclaim.py,
test_relocate_project_root_orphan_reclaim.py - all of which exercise the OLD
``_ClientAPIProjectsMixin``/``core.database.projects`` layers, kept unchanged and
still passing) onto the NEW
``code_analysis.core.database_driver_pkg.domain.projects`` free-function form.
Per the Block B task contract, this file is the gate that must pass BEFORE any
``projects`` caller is rewired to the new functions.

The fakes below implement only the real driver-shaped surface (``execute``/
``select``/``update``) - no dependency on ``_ClientAPIProjectsMixin`` - since the
new functions take a plain duck-typed ``driver: Any`` argument, not a ``self``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.database_driver_pkg.domain import projects as domain_projects
from code_analysis.core.database_client.objects.project import Project

_SID = "server-current"
_OTHER_SID = "server-orphaned-from"


def _norm_su(sql: str) -> str:
    """Normalize whitespace and case for simple prefix/substring SQL matching."""
    return " ".join(sql.split()).upper()


class _FakeDriver:
    """In-memory ``projects`` table behind the real driver-shaped surface.

    Implements only ``execute``/``select``/``update`` - the same 13-primitive
    surface ``PostgreSQLDriver`` and ``DatabaseClient`` both expose identically
    (scratchpad/stage2-parity-spike.md) - not a subclass of any client/mixin.
    """

    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        """Seed the fake table; ``rows`` is mutated in place by writes."""
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
        """Route SELECT/UPDATE/INSERT against the in-memory table."""
        p = tuple(params or ())
        self.execute_calls.append((sql, p))
        su = _norm_su(sql)

        if su.startswith("SELECT * FROM PROJECTS WHERE ID"):
            row = self._rows.get(p[0])
            return {"data": [dict(row)] if row else []}
        if su.startswith("SELECT WATCH_DIR_ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"data": [{"watch_dir_id": row.get("watch_dir_id")}]}
            return {"data": []}
        if "ID != ?" in su:
            return {"data": []}
        if su.startswith("SELECT ID FROM PROJECTS WHERE SERVER_INSTANCE_ID"):
            sid, pid = p
            row = self._rows.get(pid)
            if row is not None and row.get("server_instance_id") == sid:
                return {"data": [{"id": pid}]}
            return {"data": []}
        if su.startswith("UPDATE PROJECTS") and "SET SERVER_INSTANCE_ID = ?, ROOT_PATH = ?" in su:
            sid, root_path, name, comment, watch_dir_id = p[:5]
            project_id = p[-1]
            row = self._rows.get(project_id)
            if row is None:
                return {"affected_rows": 0}
            if "SERVER_INSTANCE_ID = ?" in su.split("WHERE", 1)[-1]:
                # insert_project_row's reassign branch: WHERE id=? AND server_instance_id=?
                other_sid = p[-2]
                if row.get("server_instance_id") != other_sid:
                    return {"affected_rows": 0}
            row.update(
                {
                    "server_instance_id": sid,
                    "root_path": root_path,
                    "name": name,
                    "comment": comment,
                    "watch_dir_id": watch_dir_id,
                }
            )
            return {"affected_rows": 1}
        if su.startswith("UPDATE PROJECTS") and "SET DELETED" in su:
            deleted, paused, comment, sid, project_id = p
            row = self._rows.get(project_id)
            if row is not None and row.get("server_instance_id") == sid:
                row.update(
                    {"deleted": deleted, "processing_paused": paused, "comment": comment}
                )
                return {"affected_rows": 1, "data": None}
            return {"affected_rows": 0, "data": None}
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
        if su.startswith("UPDATE PROJECTS") and "SET SERVER_INSTANCE_ID" in su:
            new_sid, project_id = p
            row = self._rows.get(project_id)
            if row is not None:
                row["server_instance_id"] = new_sid
                return {"affected_rows": 1}
            return {"affected_rows": 0}
        if su.startswith("INSERT INTO PROJECTS"):
            (
                pid,
                sid,
                root_path,
                name,
                comment,
                watch_dir_id,
                deleted,
                paused,
            ) = p
            self._rows[pid] = {
                "id": pid,
                "server_instance_id": sid,
                "root_path": root_path,
                "name": name,
                "comment": comment,
                "watch_dir_id": watch_dir_id,
                "deleted": deleted,
                "processing_paused": paused,
            }
            return {"affected_rows": 1}
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
        if table_name != "projects" or not where or "id" not in where:
            return []
        row = self._rows.get(where["id"])
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


def _enrich_identity(row: Dict[str, Any], _driver: Any) -> Dict[str, Any]:
    """Return the row unchanged (skip real root-path resolution in these unit tests)."""
    return dict(row)


_ENRICH_PATCH = patch(
    "code_analysis.core.database_driver_pkg.domain.projects."
    "enrich_project_dict_resolve_root_path",
    side_effect=_enrich_identity,
)
_SID_PATCH = patch(
    "code_analysis.core.database_driver_pkg.domain.projects.current_server_instance_id",
    return_value=_SID,
)
_NOW_PATCH = patch(
    "code_analysis.core.database_driver_pkg.domain.projects.sql_julian_timestamp_now_expr",
    return_value="julianday('now')",
)


# ─────────────────────────────────────────────────────────────────────────
# get_project: scoped hit / scoped-miss global-fallback / neither found
# ─────────────────────────────────────────────────────────────────────────


@_ENRICH_PATCH
@_SID_PATCH
def test_get_project_scoped_hit_returns_directly(_sid_mock: Any, _enrich_mock: Any) -> None:
    """Scoped select hits -> returned directly as a Project, no global fallback needed."""
    driver = _FakeDriver(
        {"pid-1": {"id": "pid-1", "server_instance_id": _SID, "root_path": "proj1"}}
    )

    result = domain_projects.get_project(driver, "pid-1")

    assert isinstance(result, Project)
    assert result.id == "pid-1"
    assert driver.execute_calls == []  # scoped select hit; no global-fallback execute() issued


@_ENRICH_PATCH
@_SID_PATCH
def test_get_project_scoped_miss_falls_back_to_global(_sid_mock: Any, _enrich_mock: Any) -> None:
    """Scoped select misses (orphan row under a different sid) -> global fallback finds it."""
    driver = _FakeDriver(
        {
            "pid-orphan": {
                "id": "pid-orphan",
                "server_instance_id": _OTHER_SID,
                "root_path": "orphan_proj",
            }
        }
    )

    result = domain_projects.get_project(driver, "pid-orphan")

    assert isinstance(result, Project)
    assert result.id == "pid-orphan"
    assert result.root_path == "orphan_proj"
    assert len(driver.execute_calls) == 1  # the global-by-id fallback SELECT


@_SID_PATCH
def test_get_project_neither_scoped_nor_global_returns_none(_sid_mock: Any) -> None:
    """Genuinely nonexistent project_id -> None after both lookups miss."""
    driver = _FakeDriver({})

    result = domain_projects.get_project(driver, "does-not-exist")

    assert result is None


# ─────────────────────────────────────────────────────────────────────────
# insert_project_row: orphan reclaim / same-disk reassign / reject
# ─────────────────────────────────────────────────────────────────────────


@_NOW_PATCH
@_SID_PATCH
def test_insert_project_row_reclaims_orphan_without_insert(
    _sid_mock: Any, _now_mock: Any
) -> None:
    """Orphan row with no server_instance_id -> reclaimed via UPDATE, no INSERT."""
    driver = _FakeDriver(
        {"pid-1": {"id": "pid-1", "server_instance_id": None, "root_path": "old"}}
    )

    with patch(
        "code_analysis.core.database_driver_pkg.domain.projects.get_project",
        return_value=None,
    ):
        domain_projects.insert_project_row(
            driver,
            "pid-1",
            "vast_srv",
            "vast_srv",
            comment="AI Admin",
            watch_dir_id="wd-1",
        )

    sqls = [c[0] for c in driver.execute_calls]
    assert any("UPDATE projects" in s for s in sqls)
    assert not any("INSERT INTO projects" in s for s in sqls)


@_NOW_PATCH
@_SID_PATCH
def test_insert_project_row_reassigns_same_disk_root_from_other_instance(
    _sid_mock: Any, _now_mock: Any
) -> None:
    """Row owned by a different sid but same resolved disk root -> reassigned, no INSERT."""
    root = "/home/vasilyvz/projects/tools/vast_srv"
    driver = _FakeDriver(
        {
            "pid-1": {
                "id": "pid-1",
                "server_instance_id": "server-a",
                "root_path": "vast_srv",
                "watch_dir_id": "wd-old",
                "name": "vast_srv",
            }
        }
    )
    with patch(
        "code_analysis.core.database_driver_pkg.domain.projects.get_project",
        return_value=None,
    ), patch(
        "code_analysis.core.database_driver_pkg.domain.projects."
        "resolve_project_root_absolute_str",
        side_effect=lambda **_kw: root,
    ):
        domain_projects.insert_project_row(
            driver, "pid-1", "vast_srv", "vast_srv", watch_dir_id="wd-new"
        )

    sqls = [c[0] for c in driver.execute_calls]
    assert any("UPDATE projects" in s and "server_instance_id = ?" in s for s in sqls)
    assert not any("INSERT INTO projects" in s for s in sqls)


@_NOW_PATCH
@_SID_PATCH
def test_insert_project_row_rejects_id_on_other_server_instance(
    _sid_mock: Any, _now_mock: Any
) -> None:
    """Row owned by a different sid with a genuinely different disk root -> ValueError."""
    driver = _FakeDriver(
        {
            "pid-1": {
                "id": "pid-1",
                "server_instance_id": "server-a",
                "root_path": "other_dir",
            }
        }
    )

    def _resolve(**kw: Any) -> str:
        """Return resolve."""
        stored = str(kw.get("root_path_stored") or "")
        return "/other/project" if stored == "other_dir" else "/home/vast_srv"

    with patch(
        "code_analysis.core.database_driver_pkg.domain.projects.get_project",
        return_value=None,
    ), patch(
        "code_analysis.core.database_driver_pkg.domain.projects."
        "resolve_project_root_absolute_str",
        side_effect=_resolve,
    ):
        with pytest.raises(ValueError, match="server_instance_id=server-a"):
            domain_projects.insert_project_row(driver, "pid-1", "vast_srv", "vast_srv")


# ─────────────────────────────────────────────────────────────────────────
# sync_project_metadata_from_projectid: reclaim / absent / normal
# ─────────────────────────────────────────────────────────────────────────


@_SID_PATCH
def test_sync_project_metadata_reclaims_orphan_row(_sid_mock: Any, tmp_path: Path) -> None:
    """Orphan row (different server_instance_id) -> reclaimed, then the write lands."""
    pid = "pid-orphan"
    driver = _FakeDriver(
        {
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
    )
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch("code_analysis.core.project_resolution.load_project_info") as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "trashed"
        load_info_mock.return_value = info

        result = domain_projects.sync_project_metadata_from_projectid(
            driver, str(project_dir)
        )

    assert result == pid
    assert driver._rows[pid]["server_instance_id"] == _SID
    assert driver._rows[pid]["deleted"] is True
    assert driver._rows[pid]["comment"] == "trashed"
    assert any(
        call[1].get("id") == pid and call[2].get("server_instance_id") == _SID
        for call in driver.update_calls
    ), f"expected a reclaim UPDATE via driver.update; got {driver.update_calls}"


@_SID_PATCH
def test_sync_project_metadata_row_absent_globally_unchanged(
    _sid_mock: Any, tmp_path: Path
) -> None:
    """Project id not present anywhere -> still a no-op, no error, no reclaim attempt."""
    pid = "pid-does-not-exist"
    driver = _FakeDriver({})
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch("code_analysis.core.project_resolution.load_project_info") as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = None
        load_info_mock.return_value = info

        result = domain_projects.sync_project_metadata_from_projectid(
            driver, str(project_dir)
        )

    assert result == pid
    assert driver.update_calls == []


@_SID_PATCH
def test_sync_project_metadata_normal_write_unaffected(_sid_mock: Any, tmp_path: Path) -> None:
    """Row already owned by the current server instance -> single write, no reclaim."""
    pid = "pid-normal"
    driver = _FakeDriver(
        {
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
    )
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    with patch("code_analysis.core.project_resolution.load_project_info") as load_info_mock:
        info = MagicMock()
        info.project_id = pid
        info.deleted = True
        info.processing_paused = False
        info.description = "ok"
        load_info_mock.return_value = info

        result = domain_projects.sync_project_metadata_from_projectid(
            driver, str(project_dir)
        )

    assert result == pid
    assert driver._rows[pid]["deleted"] is True
    assert driver.update_calls == []


# ─────────────────────────────────────────────────────────────────────────
# relocate_project_root_after_disk_move: reclaim / normal / absent
# ─────────────────────────────────────────────────────────────────────────


@_SID_PATCH
def test_relocate_reclaims_orphan_row(_sid_mock: Any, tmp_path: Path) -> None:
    """Orphan row (different server_instance_id) -> reclaimed, then the move lands."""
    pid = "pid-relocate-orphan"
    old_root = (tmp_path / "old" / "proj").resolve()
    new_root = (tmp_path / "moved_proj").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    driver = _FakeDriver(
        {
            pid: {
                "id": pid,
                "server_instance_id": _OTHER_SID,
                "root_path": str(old_root),
                "name": "proj",
                "watch_dir_id": None,
            }
        }
    )

    result = domain_projects.relocate_project_root_after_disk_move(
        driver, pid, str(old_root), str(new_root)
    )

    assert result is True
    assert driver._rows[pid]["server_instance_id"] == _SID
    assert Path(driver._rows[pid]["root_path"]).resolve() == new_root
    assert driver._rows[pid]["name"] == new_root.name
    assert any(
        call[1].get("id") == pid and call[2].get("server_instance_id") == _SID
        for call in driver.update_calls
    ), f"expected a reclaim UPDATE via driver.update; got {driver.update_calls}"


@_SID_PATCH
def test_relocate_normal_write_unaffected(_sid_mock: Any, tmp_path: Path) -> None:
    """Row already owned by the current server instance -> single write, no reclaim."""
    pid = "pid-relocate-normal"
    old_root = (tmp_path / "old" / "proj2").resolve()
    new_root = (tmp_path / "moved_proj2").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    driver = _FakeDriver(
        {
            pid: {
                "id": pid,
                "server_instance_id": _SID,
                "root_path": str(old_root),
                "name": "proj2",
                "watch_dir_id": None,
            }
        }
    )

    result = domain_projects.relocate_project_root_after_disk_move(
        driver, pid, str(old_root), str(new_root)
    )

    assert result is True
    assert Path(driver._rows[pid]["root_path"]).resolve() == new_root
    assert driver.update_calls == []


@_SID_PATCH
def test_relocate_row_absent_globally_returns_false(_sid_mock: Any, tmp_path: Path) -> None:
    """Project id not present anywhere -> False, no error, no reclaim attempted."""
    pid = "pid-relocate-missing"
    old_root = (tmp_path / "old" / "proj3").resolve()
    new_root = (tmp_path / "moved_proj3").resolve()
    old_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    driver = _FakeDriver({})

    result = domain_projects.relocate_project_root_after_disk_move(
        driver, pid, str(old_root), str(new_root)
    )

    assert result is False
    assert driver.update_calls == []
