"""
Regression: export_graph call_graph entity node identity (unique per entity).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from code_analysis.commands.ast.graph import ExportGraphMCPCommand, _is_valid_uuid4
from code_analysis.commands.ast.graph_entity_nodes import (
    resolve_usage_target_cst_node_id,
)
from code_analysis.core.database.base import create_driver_config_for_worker
from code_analysis.core.database import CodeDatabase


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def project_id():
    return str(uuid.uuid4())


@pytest.fixture
def test_db(temp_dir):
    db_path = temp_dir / "test.db"
    driver_config = create_driver_config_for_worker(
        db_path, driver_type="sqlite", backup_dir=temp_dir / "backups"
    )
    db = CodeDatabase(driver_config=driver_config)
    db.sync_schema()
    yield db
    db.close()


@pytest.fixture
def test_project(test_db, temp_dir, project_id):
    test_db._execute(
        "INSERT INTO projects (id, root_path, name, updated_at) VALUES (?, ?, ?, julianday('now'))",
        (project_id, str(temp_dir), temp_dir.name),
    )
    test_db._commit()
    return project_id


def _uuid4() -> str:
    return str(uuid.uuid4())


class TestResolveUsageTargetUniquePerFile:
    """Same simple class name in two files must resolve to distinct cst_node_ids."""

    def test_class_name_collision_prefers_same_file(
        self, test_db, test_project, temp_dir
    ):
        path_a = temp_dir / "a.py"
        path_b = temp_dir / "b.py"
        path_a.write_text("# a", encoding="utf-8")
        path_b.write_text("# b", encoding="utf-8")
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 1, 0, 0)""",
            (test_project, str(path_a)),
        )
        test_db._commit()
        fid_a = test_db._lastrowid()
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 1, 0, 0)""",
            (test_project, str(path_b)),
        )
        test_db._commit()
        fid_b = test_db._lastrowid()

        cid_a = _uuid4()
        cid_b = _uuid4()
        test_db._execute(
            "INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?)",
            (fid_a, "Dup", 1, None, "[]", cid_a),
        )
        test_db._execute(
            "INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?)",
            (fid_b, "Dup", 1, None, "[]", cid_b),
        )
        test_db._commit()

        ra = resolve_usage_target_cst_node_id(
            test_db,
            test_project,
            fid_a,
            "class",
            "Dup",
            None,
            _is_valid_uuid4,
        )
        rb = resolve_usage_target_cst_node_id(
            test_db,
            test_project,
            fid_b,
            "class",
            "Dup",
            None,
            _is_valid_uuid4,
        )
        assert ra is not None and rb is not None
        assert ra[0] != rb[0]
        assert ra[0] == cid_a and ra[1] == str(path_a)
        assert rb[0] == cid_b and rb[1] == str(path_b)


class TestCallGraphEntityNodesNoDuplicateNodeId:
    """Simulate call_graph aggregation: node_id keys must be unique (cst_node_id)."""

    def test_entity_nodes_dict_unique_node_ids(self, test_db, test_project, temp_dir):
        path_a = temp_dir / "a.py"
        path_b = temp_dir / "b.py"
        path_a.write_text("# a", encoding="utf-8")
        path_b.write_text("# b", encoding="utf-8")
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 1, 0, 0)""",
            (test_project, str(path_a)),
        )
        test_db._commit()
        fid_a = test_db._lastrowid()
        test_db._execute(
            """INSERT INTO files (project_id, path, lines, last_modified, has_docstring)
               VALUES (?, ?, 1, 0, 0)""",
            (test_project, str(path_b)),
        )
        test_db._commit()
        fid_b = test_db._lastrowid()

        cid_a = _uuid4()
        cid_b = _uuid4()
        test_db._execute(
            "INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?)",
            (fid_a, "Dup", 1, None, "[]", cid_a),
        )
        test_db._execute(
            "INSERT INTO classes (file_id, name, line, docstring, bases, cst_node_id) VALUES (?, ?, ?, ?, ?, ?)",
            (fid_b, "Dup", 1, None, "[]", cid_b),
        )
        test_db._commit()

        entity_nodes_by_cid: dict[str, dict[str, str]] = {}
        for uf in (fid_a, fid_b):
            resolved = resolve_usage_target_cst_node_id(
                test_db,
                test_project,
                uf,
                "class",
                "Dup",
                None,
                _is_valid_uuid4,
            )
            assert resolved is not None
            cid, entity_path = resolved
            entity_nodes_by_cid[cid] = {
                "node_id": cid,
                "file_path": entity_path,
                "cst_node_id": cid,
                "label": "Dup",
            }

        assert len(entity_nodes_by_cid) == 2
        assert len({e["node_id"] for e in entity_nodes_by_cid.values()}) == 2


class TestIsValidUuid4Helper:
    def test_rejects_non_uuid4_cst_placeholder(self):
        assert _is_valid_uuid4("fixture:TestClass:ClassDef:10:0-14:0") is False
        assert _is_valid_uuid4(str(uuid.uuid4())) is True


class TestExportGraphQueued:
    """export_graph runs via job queue so long call_graph exports do not hit MCP timeouts."""

    def test_use_queue_true(self):
        assert ExportGraphMCPCommand.use_queue is True
