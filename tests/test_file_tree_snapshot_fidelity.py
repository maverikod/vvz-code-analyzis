"""
Fidelity, atomicity, and round-trip test suite for unified file-level DB write.

Proves: unified code path (tree-save and background indexing), file-level atomicity,
restore policy, and text fidelity end-to-end. TZ §10.1, §10.2, §10.3.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.commands.file_management import RepairDatabaseCommand
from code_analysis.commands.update_indexes_analyzer import analyze_file
from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
from code_analysis.core.cst_tree.tree_saver import save_tree_to_file

from tests.sqlite_in_process_legacy_facade import (
    SqliteLegacyRpcFacade,
)
from tests.sqlite_inprocess_database import sqlite_inprocess_database_client


class _FileTreeReadCompatFacade:
    """Delegates to SqliteLegacyRpcFacade; exposes dict-shaped ``get_project`` for read helpers."""

    def __init__(self, facade: SqliteLegacyRpcFacade) -> None:
        object.__setattr__(self, "_facade", facade)

    def get_project(self, project_id: str):
        p = self._facade._client.get_project(project_id)
        if p is None:
            return None
        return {"id": p.id, "root_path": p.root_path}

    def __getattr__(self, name: str):
        return getattr(self._facade, name)

    def __setattr__(self, name: str, value) -> None:  # noqa: ANN001
        if name == "_facade":
            object.__setattr__(self, name, value)
        else:
            setattr(self._facade, name, value)


MOCK_FILE_UUID = "00000000-0000-4000-8000-000000000001"


# --- Fixtures ---


@pytest.fixture
def temp_dir():
    """Temporary directory for test files and DB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    """UUID4 project ID."""
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir):
    """Full SQLite DDL + legacy RPC facade + read-compat wrapper for snapshot helpers."""
    client = sqlite_inprocess_database_client(
        temp_dir / "test.db", backup_dir=temp_dir / "backups"
    )
    facade = SqliteLegacyRpcFacade(client)
    setattr(facade, "_clear_file_vectors", lambda file_id: None)
    try:
        yield _FileTreeReadCompatFacade(facade)
    finally:
        facade.close()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    """Project row and projectid file."""
    from code_analysis.core.server_instance import get_server_instance_id

    test_db._execute(
        "INSERT INTO projects (id, server_instance_id, root_path, name, updated_at) "
        "VALUES (?, ?, ?, ?, julianday('now'))",
        (project_id, get_server_instance_id(), str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    (temp_dir / "projectid").write_text(
        '{"id": "' + project_id + '"}', encoding="utf-8"
    )
    return project_id


# --- TZ §10.1: Unified code path (tests 1–3) ---


def test_tree_save_flow_calls_unified_sync(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.1 (1): Tree save flow calls the unified file sync function."""
    code = "x = 1\n"
    path = temp_dir / "a.py"
    path.write_text(code, encoding="utf-8")
    tree = create_tree_from_code(str(path), code)
    with patch(
        "code_analysis.core.database.file_tree_sync.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": True, "file_id": MOCK_FILE_UUID}
        test_db.get_file_by_path = lambda p, pid: None
        test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
        created = type("File", (), {"id": MOCK_FILE_UUID})()
        test_db.create_file = lambda *a, **k: created
        updated = type("File", (), {"id": MOCK_FILE_UUID})()
        test_db.update_file = lambda *a, **k: updated
        test_db.select = lambda *a, **k: []
        test_db.execute_logical_write_operation = lambda *a, **k: {
            "success": True,
            "data": {"batch_results": []},
        }
        result = save_tree_to_file(
            tree_id=tree.tree_id,
            file_path="a.py",
            root_dir=temp_dir,
            project_id=project_id,
            database=test_db,
            validate=True,
            backup=False,
        )
    assert result.get("success") is True
    sync_mock.assert_called_once()
    call_kw = sync_mock.call_args[1]
    src = call_kw.get("source_code") or ""
    assert src.split("# cst-node-ids:", 1)[0].strip() == code.strip()
    assert call_kw.get("project_id") == project_id


def test_background_indexing_flow_calls_unified_sync(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.1 (2): Background indexing flow calls the same unified function."""
    path = temp_dir / "b.py"
    code = "y = 2\n"
    path.write_text(code, encoding="utf-8")
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    with patch(
        "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": True, "file_id": MOCK_FILE_UUID}
        result = analyze_file(
            database=test_db,
            file_path=path,
            project_id=project_id,
            root_path=temp_dir,
        )
    assert result.get("status") == "success"
    sync_mock.assert_called_once()
    # sync_file_to_db_atomic(database, project_id, absolute_path, source_code, file_mtime, file_id=...)
    call_args, call_kw = sync_mock.call_args
    assert call_args[3] == code
    assert call_args[1] == project_id


def test_no_bypass_path_both_flows_use_same_sync(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.1 (3): No bypass path; both flows call the same sync (spy)."""
    code = "z = 3\n"
    path = temp_dir / "c.py"
    path.write_text(code, encoding="utf-8")
    tree = create_tree_from_code(str(path), code)
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    created = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.create_file = lambda *a, **k: created
    updated = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.update_file = lambda *a, **k: updated
    test_db.select = lambda *a, **k: []
    with patch(
        "code_analysis.core.database.file_tree_sync.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": True, "file_id": MOCK_FILE_UUID}
        save_tree_to_file(
            tree_id=tree.tree_id,
            file_path="c.py",
            root_dir=temp_dir,
            project_id=project_id,
            database=test_db,
            validate=True,
            backup=False,
        )
    sync_mock.assert_called_once()
    sync_mock.reset_mock()
    path2 = temp_dir / "d.py"
    path2.write_text("w = 4\n", encoding="utf-8")
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    with patch(
        "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
    ) as sync_mock2:
        sync_mock2.return_value = {"success": True, "file_id": MOCK_FILE_UUID}
        analyze_file(
            database=test_db,
            file_path=path2,
            project_id=project_id,
            root_path=temp_dir,
        )
    sync_mock2.assert_called_once()


def test_sync_file_to_db_atomic_repeated_same_file_succeeds(
    test_db, test_project, temp_dir, project_id
) -> None:
    """Repeated sync for one file must succeed (snapshot rows torn down without FK errors)."""
    code = "x = 1\n"
    path = temp_dir / "repeat_sync.py"
    path.write_text(code, encoding="utf-8")
    mtime = path.stat().st_mtime
    file_id = test_db.add_file(
        path=str(path),
        lines=1,
        last_modified=mtime,
        has_docstring=False,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    r1 = sync_file_to_db_atomic(test_db, project_id, str(path), code, mtime, file_id)
    assert r1.get("success") is True, r1.get("error")
    r2 = sync_file_to_db_atomic(test_db, project_id, str(path), code, mtime, file_id)
    assert r2.get("success") is True, r2.get("error")
    row = test_db._fetchone(
        "SELECT COUNT(*) AS c FROM file_tree_snapshots WHERE file_id = ?",
        (file_id,),
    )
    assert row is not None
    assert int(row.get("c", 0)) == 1


# --- TZ §10.2: File-level write unit (tests 4–6) ---


def test_inject_failure_during_sync_operation_fails(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.2 (4): Inject failure during file DB sync; operation fails for that file."""
    code = "a = 1\n"
    path = temp_dir / "fail.py"
    path.write_text(code, encoding="utf-8")
    tree = create_tree_from_code(str(path), code)
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    created = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.create_file = lambda *a, **k: created
    updated = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.update_file = lambda *a, **k: updated
    test_db.select = lambda *a, **k: []
    with patch(
        "code_analysis.core.database.file_tree_sync.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": False, "error": "injected failure"}
        result = save_tree_to_file(
            tree_id=tree.tree_id,
            file_path="fail.py",
            root_dir=temp_dir,
            project_id=project_id,
            database=test_db,
            validate=True,
            backup=False,
        )
    assert result.get("success") is False
    assert (
        "injected" in result.get("error", "").lower()
        or "sync" in result.get("error", "").lower()
    )


def test_file_not_reported_success_on_sync_failure(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.2 (5): File must not be reported as successfully indexed/saved on failure."""
    path = temp_dir / "nope.py"
    path.write_text("b = 2\n", encoding="utf-8")
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    with patch(
        "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": False, "error": "sync failed"}
        result = analyze_file(
            database=test_db,
            file_path=path,
            project_id=project_id,
            root_path=temp_dir,
        )
    assert result.get("status") != "success"
    assert result.get("status") in ("error", "syntax_error") or "error" in result


def test_rerun_after_failure_restores_full_file_state(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.2 (6): Re-run after failure restores consistent full-file state."""
    code = "c = 3\n"
    path = temp_dir / "retry.py"
    path.write_text(code, encoding="utf-8")
    tree = create_tree_from_code(str(path), code)
    test_db.get_file_by_path = lambda p, pid: None
    test_db.add_file = lambda *a, **k: MOCK_FILE_UUID
    created = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.create_file = lambda *a, **k: created
    updated = type("File", (), {"id": MOCK_FILE_UUID})()
    test_db.select = lambda *a, **k: []
    test_db.execute_logical_write_operation = lambda *a, **k: {
        "success": True,
        "data": {"batch_results": []},
    }
    call_count = [0]

    def fail_once_then_ok(*args, **kwargs):
        from code_analysis.core.database import file_tree_sync as m

        call_count[0] += 1
        if call_count[0] == 1:
            return {"success": False, "error": "injected"}
        return m.sync_file_to_db_atomic(
            test_db,
            project_id,
            kwargs["absolute_path"],
            code,
            0.0,
            MOCK_FILE_UUID,
        )

    with patch(
        "code_analysis.core.database.file_tree_sync.sync_file_to_db_atomic",
        side_effect=fail_once_then_ok,
    ):
        r1 = save_tree_to_file(
            tree_id=tree.tree_id,
            file_path="retry.py",
            root_dir=temp_dir,
            project_id=project_id,
            database=test_db,
            validate=True,
            backup=False,
        )
    assert r1.get("success") is False
    with patch(
        "code_analysis.core.database.file_tree_sync.sync_file_to_db_atomic"
    ) as sync_mock:
        sync_mock.return_value = {"success": True, "file_id": MOCK_FILE_UUID}
        r2 = save_tree_to_file(
            tree_id=tree.tree_id,
            file_path="retry.py",
            root_dir=temp_dir,
            project_id=project_id,
            database=test_db,
            validate=True,
            backup=False,
        )
    assert r2.get("success") is True
    disk = path.read_text(encoding="utf-8")
    assert disk.split("# cst-node-ids:", 1)[0].strip() == code.strip()


# --- TZ §10.3: Restoration (tests 7–9) ---


@pytest.mark.asyncio
async def test_restore_file_missing_db_source_exists(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (7): File missing + DB source exists -> full restore succeeds."""
    code = '"""doc"""\nrestored = 1\n'
    rel = "e.py"
    path = temp_dir / rel
    path.write_text(code, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=len(code.splitlines()),
        last_modified=path.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    path.unlink()
    assert not path.exists()
    cmd = RepairDatabaseCommand(
        database=test_db,
        project_id=project_id,
        root_dir=temp_dir,
        version_dir=str(temp_dir / "versions"),
        dry_run=False,
        force=False,
    )
    restored = await cmd._restore_file_from_cst(
        file_id, rel, {"project_id": project_id, "deleted": False}
    )
    assert restored is True
    assert path.exists()
    assert path.read_text(encoding="utf-8") == code


@pytest.mark.asyncio
async def test_restore_file_exists_force_false_safe_refusal(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (8): File exists + force=false -> safe refusal (no overwrite)."""
    code = "x = 1\n"
    path = temp_dir / "f.py"
    path.write_text(code, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=1,
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    path.write_text("other\n", encoding="utf-8")
    cmd = RepairDatabaseCommand(
        database=test_db,
        project_id=project_id,
        root_dir=temp_dir,
        version_dir=str(temp_dir / "versions"),
        dry_run=False,
        force=False,
    )
    restored = await cmd._restore_file_from_cst(
        file_id, "f.py", {"project_id": project_id, "deleted": False}
    )
    assert restored is False
    assert path.read_text(encoding="utf-8") == "other\n"


@pytest.mark.asyncio
async def test_restore_file_exists_force_true_overwrite_with_backup(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (9): File exists + force=true -> overwrite with backup."""
    code = "y = 2\n"
    path = temp_dir / "g.py"
    path.write_text("existing\n", encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=1,
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    path.write_text("existing\n", encoding="utf-8")
    cmd = RepairDatabaseCommand(
        database=test_db,
        project_id=project_id,
        root_dir=temp_dir,
        version_dir=str(temp_dir / "versions"),
        dry_run=False,
        force=True,
    )
    with patch("code_analysis.core.backup_manager.BackupManager") as bm_mock:
        inst = bm_mock.return_value
        inst.create_backup.return_value = "backup-uuid"
        restored = await cmd._restore_file_from_cst(
            file_id,
            "g.py",
            {"project_id": project_id, "deleted": False},
            force=True,
        )
    assert restored is True
    assert path.read_text(encoding="utf-8") == code


# --- TZ §10.3: Fidelity (tests 10–13) ---


def test_fidelity_index_delete_restore_full_text_equality(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (10): Index -> delete -> restore -> full text equality."""
    code = '"""Fidelity test."""\na = 1\nb = 2\n'
    path = temp_dir / "h.py"
    path.write_text(code, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=len(code.splitlines()),
        last_modified=path.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    path.unlink()
    row = test_db._fetchone(
        "SELECT source_payload FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_id,),
    )
    assert row is not None
    payload = row.get("source_payload")
    assert payload == code
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == code


def test_sibling_order_roundtrip(test_db, test_project, temp_dir, project_id) -> None:
    """TZ 10.3 (11): Sibling order round-trip: save/load preserves child order."""
    code = "a = 1\nb = 2\nc = 3\n"
    path = temp_dir / "sib.py"
    path.write_text(code, encoding="utf-8")
    tree = create_tree_from_code(str(path), code)
    order_before = [
        getattr(n, "value", getattr(n, "name", str(n))) for n in tree.module.body
    ]
    file_id = test_db.add_file(
        path=str(path),
        lines=3,
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    row = test_db._fetchone(
        "SELECT source_payload FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_id,),
    )
    assert row is not None
    restored_code = row.get("source_payload")
    tree2 = create_tree_from_code(str(path), restored_code)
    order_after = [
        getattr(n, "value", getattr(n, "name", str(n))) for n in tree2.module.body
    ]
    assert order_after == order_before
    assert restored_code == code


def test_comment_docstring_fidelity_roundtrip(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (12): Comment/docstring fidelity: round-trip unchanged."""
    source = '# top\n"""Module doc."""\ndef f():\n    """F doc."""\n    pass  # eol\n'
    path = temp_dir / "comm.py"
    path.write_text(source, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=len(source.splitlines()),
        last_modified=path.stat().st_mtime,
        has_docstring=True,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), source, path.stat().st_mtime, file_id
    )
    row = test_db._fetchone(
        "SELECT source_payload FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_id,),
    )
    assert row is not None
    restored = row.get("source_payload")
    assert "# top" in restored
    assert '"""Module doc."""' in restored or "Module doc" in restored
    assert "F doc" in restored
    assert "# eol" in restored


def test_data_type_fidelity_literals_containers(
    test_db, test_project, temp_dir, project_id
) -> None:
    """TZ 10.3 (13): Data-type fidelity: literals and containers preserved."""
    code = (
        "n = 42\ns = 'hi'\nb = True\nx = None\n"
        "lst = [1, 2]\nd = {'k': 1}\nt = (1, 2)\nst = {1, 2}\n"
    )
    path = temp_dir / "types.py"
    path.write_text(code, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=len(code.splitlines()),
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    row = test_db._fetchone(
        "SELECT source_payload FROM file_tree_snapshots WHERE file_id = ? ORDER BY id DESC LIMIT 1",
        (file_id,),
    )
    assert row is not None
    restored = row.get("source_payload")
    assert "42" in restored and "'hi'" in restored
    assert "True" in restored and "None" in restored
    assert "[1, 2]" in restored and "{'k': 1}" in restored
    assert "(1, 2)" in restored and "{1, 2}" in restored
    assert restored == code


def test_get_snapshot_tree_structure_returns_nodes(
    test_db, test_project, temp_dir, project_id
) -> None:
    """Step 10: get_snapshot_tree_structure returns node_id, parent_node_id, child_index."""
    from code_analysis.core.database.file_tree_read import get_snapshot_tree_structure
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    code = "a = 1\nb = 2\n"
    path = temp_dir / "read_api.py"
    path.write_text(code, encoding="utf-8")
    file_id = test_db.add_file(
        path=str(path),
        lines=len(code.splitlines()),
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    sync_file_to_db_atomic(
        test_db, project_id, str(path), code, path.stat().st_mtime, file_id
    )
    result = get_snapshot_tree_structure(project_id, "read_api.py", test_db)
    assert result["has_snapshot"] is True
    assert result["snapshot_id"] is not None
    assert isinstance(result["snapshot_id"], str)
    assert result["root_node_id"] is not None
    assert isinstance(result["root_node_id"], str)
    assert len(result["nodes"]) >= 1
    for node in result["nodes"]:
        assert "node_id" in node
        assert "parent_node_id" in node
        assert "child_index" in node
        assert isinstance(node["child_index"], int)
    root_ids = {n["node_id"] for n in result["nodes"] if n["parent_node_id"] is None}
    assert result["root_node_id"] in root_ids or any(
        n["node_id"] == result["root_node_id"] for n in result["nodes"]
    )


def test_get_snapshot_tree_structure_no_snapshot(
    test_db, test_project, temp_dir, project_id
) -> None:
    """Step 10: get_snapshot_tree_structure returns no_snapshot when no snapshot exists."""
    from code_analysis.core.database.file_tree_read import get_snapshot_tree_structure

    path = temp_dir / "no_snap.py"
    path.write_text("x = 1\n", encoding="utf-8")
    test_db.add_file(
        path=str(path),
        lines=1,
        last_modified=path.stat().st_mtime,
        has_docstring=False,
        project_id=project_id,
    )
    result = get_snapshot_tree_structure(project_id, "no_snap.py", test_db)
    assert result["has_snapshot"] is False
    assert result["snapshot_id"] is None
    assert result["root_node_id"] is None
    assert result["nodes"] == []
