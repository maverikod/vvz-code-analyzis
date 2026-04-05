"""
Tests for persisted CST UUID4 identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from code_analysis.core.cst_tree.models import TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.node_id_markers import (
    MARKERS_BEGIN,
    MARKERS_END,
    append_persisted_node_ids,
    strip_persisted_node_ids,
)
from code_analysis.core.cst_tree.tree_builder import (
    create_tree_from_code,
    load_file_to_tree,
)
from code_analysis.core.cst_tree.tree_finder import find_nodes
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.cst_tree.tree_saver import save_tree_to_file


def _make_db_mock_for_sync() -> MagicMock:
    """Mock DB for sync_file_to_db_atomic: one logical write RPC."""
    db = MagicMock()
    db.get_file_by_path = MagicMock(return_value={"id": 1})
    db.execute_logical_write_operation = MagicMock(
        return_value={
            "success": True,
            "data": {"batch_results": [], "transaction_id": "tid"},
        }
    )
    return db


def _make_db_mock() -> MagicMock:
    db = MagicMock()
    db.select = MagicMock(return_value=[])
    created = MagicMock()
    created.id = 1
    db.create_file = MagicMock(return_value=created)
    db.update_file = MagicMock(return_value=created)
    db.execute_logical_write_operation = MagicMock(
        return_value={
            "success": True,
            "data": {"batch_results": [], "transaction_id": "tid"},
        }
    )
    return db


def test_marker_block_round_trip_keeps_clean_source() -> None:
    """Appending and stripping the marker block must preserve logical source."""
    source = '"""Doc."""\n\nx = 1\n'
    tree = create_tree_from_code("/tmp/example.py", source)

    persisted_source = append_persisted_node_ids(
        source,
        tree.metadata_map,
        tree.root_node_id,
    )
    clean_source, persisted_node_ids = strip_persisted_node_ids(persisted_source)

    assert MARKERS_BEGIN in persisted_source
    assert MARKERS_END in persisted_source
    assert clean_source == source
    assert len(persisted_node_ids) == len(tree.metadata_map)


def test_save_and_reload_preserve_node_ids(tmp_path: Path) -> None:
    """Saving with marker block and loading again must reproduce the same UUIDs."""
    db = _make_db_mock()
    file_path = tmp_path / "sample.py"
    tree = create_tree_from_code(
        str(file_path),
        '"""Doc."""\n\nimport os\n\n\ndef foo() -> int:\n    return 1\n',
    )
    result = save_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(file_path),
        root_dir=tmp_path,
        project_id=str(uuid.uuid4()),
        database=db,
        validate=True,
        backup=False,
    )

    assert result["success"] is True
    persisted_text = file_path.read_text(encoding="utf-8")
    assert MARKERS_BEGIN in persisted_text
    assert MARKERS_END in persisted_text

    reloaded = load_file_to_tree(str(file_path))
    assert reloaded.root_node_id == tree.root_node_id
    before_function = find_nodes(
        tree.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    after_function = find_nodes(
        reloaded.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    assert before_function.node_id == after_function.node_id


def test_modify_save_reload_preserves_replaced_function_id(tmp_path: Path) -> None:
    """A replaced function keeps its UUID after save and reload."""
    db = _make_db_mock()
    file_path = tmp_path / "sample.py"
    tree = create_tree_from_code(
        str(file_path),
        "def foo() -> int:\n    return 1\n",
    )
    function_meta = find_nodes(
        tree.tree_id,
        search_type="simple",
        node_type="FunctionDef",
    )[0]
    original_function_id = function_meta.node_id

    modify_tree(
        tree.tree_id,
        [
            TreeOperation(
                action=TreeOperationType.REPLACE,
                node_id=original_function_id,
                code_lines=[
                    "def foo() -> int:",
                    '    """Updated."""',
                    "    return 2",
                ],
            )
        ],
    )

    save_result = save_tree_to_file(
        tree_id=tree.tree_id,
        file_path=str(file_path),
        root_dir=tmp_path,
        project_id=str(uuid.uuid4()),
        database=db,
        validate=True,
        backup=False,
    )
    assert save_result["success"] is True

    reloaded = load_file_to_tree(str(file_path))
    reloaded_function = find_nodes(
        reloaded.tree_id,
        search_type="simple",
        node_type="FunctionDef",
        name="foo",
    )[0]
    assert reloaded_function.node_id == original_function_id


def test_sync_with_marked_source_writes_same_root_node_id() -> None:
    """sync_file_to_db_atomic with source that has markers produces same node_ids; snapshot stores them."""
    from code_analysis.core.database.file_tree_sync import sync_file_to_db_atomic

    clean = '"""Doc."""\n\ndef foo() -> int:\n    return 1\n'
    path = "/tmp/sync_align.py"
    tree = create_tree_from_code(path, clean)
    source_with_markers = append_persisted_node_ids(
        clean, tree.metadata_map, tree.root_node_id
    )
    tree2 = create_tree_from_code(path, source_with_markers)
    assert (
        tree.root_node_id == tree2.root_node_id
    ), "same source with markers => same IDs"

    db = _make_db_mock_for_sync()
    root_captured: list = []

    def capture_lw(program: dict) -> dict[str, Any]:
        for batch in program.get("batches") or []:
            for sql, params in batch:
                if "file_tree_snapshot_roots" in sql and "INSERT" in sql:
                    root_captured.append(params)
        return {
            "success": True,
            "data": {"batch_results": [], "transaction_id": "tid"},
        }

    db.execute_logical_write_operation = MagicMock(side_effect=capture_lw)
    sync_file_to_db_atomic(
        database=db,
        project_id="test-project",
        absolute_path=path,
        source_code=source_with_markers,
        file_mtime=0.0,
        file_id=1,
    )
    assert len(root_captured) >= 1
    (snapshot_id, root_node_id) = root_captured[0]
    assert root_node_id == tree.root_node_id
