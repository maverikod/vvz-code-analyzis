"""
Regression: add_file must not treat matching relative_path across projects as conflict.

Allowlisted parallel ``.venv/site-packages/...`` trees under different project roots
share the same project-relative path string but different absolute paths. DB
uniqueness is ``UNIQUE(project_id, path)``; cross-project logic must only consider
the same absolute ``path`` (e.g. relocation / one canonical path via symlinks).

Watcher ignore policy for non-allowlisted ``.venv`` paths is tested elsewhere;
this module exercises add_file via :class:`~tests.sqlite_in_process_legacy_facade.SqliteLegacyRpcFacade`
over :class:`~code_analysis.core.database_client.client.DatabaseClient`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import types
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.core.database.files import crud as crud_module

from tests.sqlite_in_process_legacy_facade import SqliteLegacyRpcFacade
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


class _CrudAlignedRpcFacade(SqliteLegacyRpcFacade):
    """``crud.add_file`` / ``get_file_by_path`` expect dict-shaped ``get_project``."""

    def get_project(self, project_id: str):
        p = self._client.get_project(project_id)
        if p is None:
            return None
        return {
            "id": p.id,
            "root_path": p.root_path,
            "name": getattr(p, "name", None),
            "watch_dir_id": getattr(p, "watch_dir_id", None),
        }


def _insert_project_facade(db, root: Path, name: str, project_id: str) -> None:
    db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(root.resolve()), name),
    )


def _venv_client_path(root: Path) -> Path:
    rel = Path(".venv/lib/python3.12/site-packages/mcp_proxy_adapter/core/client.py")
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# stub\n", encoding="utf-8")
    return p


def _write_projectid(project_root: Path, project_id: str) -> None:
    (project_root / "projectid").write_text(
        json.dumps({"id": project_id, "description": "test"}),
        encoding="utf-8",
    )


@pytest.fixture
def sqlite_db(tmp_path: Path):
    client = sqlite_inprocess_database_client(
        tmp_path / "cross.db", backup_dir=tmp_path / "backups"
    )
    facade = _CrudAlignedRpcFacade(client)
    facade.add_file = types.MethodType(crud_module.add_file, facade)  # type: ignore[attr-defined]
    facade.get_file_by_path = types.MethodType(crud_module.get_file_by_path, facade)  # type: ignore[attr-defined]
    try:
        yield facade
    finally:
        facade.close()


def test_add_file_same_relative_path_two_projects_no_clear(
    sqlite_db, tmp_path: Path
) -> None:
    """
    Same package-relative path under two project roots: both rows stay active;
    clear_file_data must not run for the other project.
    """
    watch = tmp_path / "watch"
    root_a = watch / "project_a"
    root_b = watch / "project_b"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)

    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    _write_projectid(root_a, pid_a)
    _write_projectid(root_b, pid_b)

    path_a = _venv_client_path(root_a)
    path_b = _venv_client_path(root_b)

    assert path_a.resolve() != path_b.resolve()
    assert path_a.relative_to(root_a) == path_b.relative_to(root_b)

    _insert_project_facade(sqlite_db, root_a, "project_a", pid_a)
    _insert_project_facade(sqlite_db, root_b, "project_b", pid_b)

    lines = 1
    mtime = float(path_a.stat().st_mtime)

    clear = sqlite_db.clear_file_data
    with patch.object(sqlite_db, "clear_file_data", wraps=clear) as clear_mock:
        fid_a = sqlite_db.add_file(
            path=str(path_a.resolve()),
            lines=lines,
            last_modified=mtime,
            has_docstring=False,
            project_id=pid_a,
        )
        uuid.UUID(str(fid_a))
        clear_mock.assert_not_called()

        mtime_b = float(path_b.stat().st_mtime)
        fid_b = sqlite_db.add_file(
            path=str(path_b.resolve()),
            lines=lines,
            last_modified=mtime_b,
            has_docstring=False,
            project_id=pid_b,
        )
        uuid.UUID(str(fid_b))
        assert fid_b != fid_a
        clear_mock.assert_not_called()

    row_a = sqlite_db._fetchone(
        "SELECT id, deleted, path FROM files WHERE id = ?", (fid_a,)
    )
    row_b = sqlite_db._fetchone(
        "SELECT id, deleted, path FROM files WHERE id = ?", (fid_b,)
    )
    assert row_a and row_b
    assert row_a["deleted"] in (0, None, False)
    assert row_b["deleted"] in (0, None, False)


def test_add_file_same_project_same_path_updates_single_row(
    sqlite_db, tmp_path: Path
) -> None:
    """UNIQUE(project_id, path): second add_file updates the existing row."""
    root = tmp_path / "single_proj"
    root.mkdir()
    pid = str(uuid.uuid4())
    _write_projectid(root, pid)
    _insert_project_facade(sqlite_db, root, "p", pid)
    f = root / "lib" / "mod.py"
    f.parent.mkdir(parents=True)
    f.write_text("x = 1\n", encoding="utf-8")
    p = str(f.resolve())
    mtime = float(f.stat().st_mtime)
    id1 = sqlite_db.add_file(
        path=p, lines=2, last_modified=mtime, has_docstring=False, project_id=pid
    )
    id2 = sqlite_db.add_file(
        path=p, lines=3, last_modified=mtime + 1.0, has_docstring=True, project_id=pid
    )
    assert id1 == id2
    n = sqlite_db._fetchone(
        "SELECT COUNT(*) AS c FROM files WHERE project_id = ? AND path = ?",
        (pid, "lib/mod.py"),
    )
    assert int(n["c"]) == 1


def test_add_file_cleanup_safety_chunks_preserved_other_project(
    sqlite_db, tmp_path: Path
) -> None:
    """Indexing project B must not clear code_chunks tied to project A's file_id."""
    watch = tmp_path / "watch2"
    root_a = watch / "pa"
    root_b = watch / "pb"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    _write_projectid(root_a, pid_a)
    _write_projectid(root_b, pid_b)
    path_a = _venv_client_path(root_a)
    path_b = _venv_client_path(root_b)
    _insert_project_facade(sqlite_db, root_a, "pa", pid_a)
    _insert_project_facade(sqlite_db, root_b, "pb", pid_b)

    fid_a = sqlite_db.add_file(
        path=str(path_a.resolve()),
        lines=1,
        last_modified=float(path_a.stat().st_mtime),
        has_docstring=False,
        project_id=pid_a,
    )
    chunk_uuid = "00000000-0000-4000-8000-00000000aaa1"
    sqlite_db._execute(
        "INSERT INTO code_chunks (id, file_id, project_id, chunk_uuid, chunk_type, "
        "chunk_text, chunk_ordinal) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), fid_a, pid_a, chunk_uuid, "docstring", "chunk body", 1),
    )
    sqlite_db._commit()

    sqlite_db.add_file(
        path=str(path_b.resolve()),
        lines=1,
        last_modified=float(path_b.stat().st_mtime),
        has_docstring=False,
        project_id=pid_b,
    )

    c = sqlite_db._fetchone(
        "SELECT COUNT(*) AS n FROM code_chunks WHERE file_id = ?", (fid_a,)
    )
    assert int(c["n"]) == 1


def test_same_absolute_path_nested_roots_second_project_triggers_cross_project_cleanup(
    sqlite_db, tmp_path: Path
) -> None:
    """
    When one project root is nested inside another, the same absolute path can be
    indexed under two ``project_id`` values. Current behavior: ``add_file`` for
    the second project finds the first project's row (same ``path`` column) and
    clears / soft-deletes the outer project's file row.

    This documents same-path cross-project semantics (nested monorepo / overlap);
    it is distinct from the parallel-``.venv`` false positive (same relative path,
    different absolute paths).
    """
    root_outer = tmp_path / "nest" / "super"
    root_inner = root_outer / "submodule"
    root_inner.mkdir(parents=True)
    inner_file = root_inner / "x.py"
    inner_file.write_text("# nested\n", encoding="utf-8")
    p = str(inner_file.resolve())

    pid_outer = str(uuid.uuid4())
    pid_inner = str(uuid.uuid4())
    _write_projectid(root_outer, pid_outer)
    _write_projectid(root_inner, pid_inner)
    _insert_project_facade(sqlite_db, root_outer, "outer", pid_outer)
    _insert_project_facade(sqlite_db, root_inner, "inner", pid_inner)

    mtime0 = float(inner_file.stat().st_mtime)
    sqlite_db.add_file(
        path=p,
        lines=2,
        last_modified=mtime0,
        has_docstring=False,
        project_id=pid_outer,
    )

    with patch.object(sqlite_db, "clear_file_data") as clear_mock:
        sqlite_db.add_file(
            path=p,
            lines=2,
            last_modified=mtime0 + 1.0,
            has_docstring=False,
            project_id=pid_inner,
        )
        clear_mock.assert_called_once()

    row_outer = sqlite_db._fetchone(
        "SELECT deleted FROM files WHERE project_id = ? AND path = ?",
        (pid_outer, "submodule/x.py"),
    )
    assert row_outer is not None
    assert row_outer["deleted"] in (1, True)
