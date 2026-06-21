"""
Regression tests for JSON save-tree metadata sync (CA-BUG-001).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_analysis.core.json_tree.json_saver import save_json_tree_to_file
from code_analysis.core.json_tree.tree_builder import build_tree_from_data

_META_PATCH = (
    "code_analysis.core.file_handlers.text_handler.persist_plain_text_file_metadata"
)


def test_save_json_tree_accepts_uuid_file_id(tmp_path: Path) -> None:
    """UUID file ids must not fail after disk write (no int-only assert)."""
    root_dir = tmp_path / "proj"
    root_dir.mkdir()
    target = root_dir / "wf_test" / "config.json"
    data = {"timeout": 30, "status": "draft", "items": ["a", "b"]}
    tree = build_tree_from_data(str(target.resolve()), data, register=True)
    file_uuid = "53094b18-b8a3-482f-a73d-3a102ecb1fd1"

    with patch(
        _META_PATCH,
        return_value={"success": True, "file_id": file_uuid, "metadata_only": True},
    ) as meta_fn:
        result = save_json_tree_to_file(
            tree_id=tree.tree_id,
            file_path=str(target),
            root_dir=root_dir,
            project_id="978e605f-04a5-42f5-8fbc-0d29cab5718a",
            database=MagicMock(),
            backup=False,
        )

    assert result["success"] is True
    assert result["file_id"] == file_uuid
    assert json.loads(target.read_text(encoding="utf-8")) == data
    meta_fn.assert_called_once()


def test_save_json_tree_metadata_failure_removes_new_file(tmp_path: Path) -> None:
    root_dir = tmp_path / "proj"
    root_dir.mkdir()
    target = root_dir / "wf_test" / "ct_repro.json"
    tree = build_tree_from_data(
        str(target.resolve()),
        {"status": "draft"},
        register=True,
    )

    with patch(
        _META_PATCH,
        return_value={
            "success": False,
            "error": "database unavailable",
            "error_code": "UPDATE_FILE_DATA_ERROR",
        },
    ):
        result = save_json_tree_to_file(
            tree_id=tree.tree_id,
            file_path=str(target),
            root_dir=root_dir,
            project_id="978e605f-04a5-42f5-8fbc-0d29cab5718a",
            database=MagicMock(),
            backup=False,
        )

    assert result["success"] is False
    assert result["error"] == "database unavailable"
    assert result["error_code"] == "UPDATE_FILE_DATA_ERROR"
    assert target.exists() is False


def test_save_json_tree_uses_metadata_only_sync(tmp_path: Path) -> None:
    root_dir = tmp_path / "proj"
    root_dir.mkdir()
    target = root_dir / "data.json"
    tree = build_tree_from_data(str(target.resolve()), {"ok": True}, register=True)

    with patch(
        _META_PATCH,
        return_value={"success": True, "file_id": "abc", "metadata_only": True},
    ) as meta_fn:
        result = save_json_tree_to_file(
            tree_id=tree.tree_id,
            file_path=str(target),
            root_dir=root_dir,
            project_id="pid",
            database=MagicMock(),
            backup=False,
        )

    assert result["success"] is True
    meta_fn.assert_called_once()
    assert meta_fn.call_args.kwargs["source_code"].startswith("{\n")
