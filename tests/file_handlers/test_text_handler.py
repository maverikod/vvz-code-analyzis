"""
Tests for plain-text :class:`~code_analysis.core.file_handlers.text_handler.TextFileHandler`
(read/save/replace/delete) and helpers — no Python AST/code-index batch on text paths.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.core.file_handlers.base import FileHandlerRequest
from code_analysis.core.file_handlers.registry import HANDLER_TEXT
from code_analysis.core.file_handlers.text_handler import (
    TextFileHandler,
    compute_replace_lines_multi,
    persist_plain_text_file_metadata,
    validate_write_range,
)


def _reject_ast(*args: object, **kwargs: object) -> None:
    raise AssertionError("ast.parse must not be called for markdown/text")


def _reject_batch(*args: object, **kwargs: object) -> None:
    raise AssertionError("update_file_data_atomic_batch must not be called for text")


def test_write_project_text_lines_module_has_no_atomic_batch_import() -> None:
    import code_analysis.commands.write_project_text_lines_command as m

    assert not hasattr(m, "update_file_data_atomic_batch")


def test_validate_write_range_out_of_bounds_raises() -> None:
    with pytest.raises(ValueError, match="bounds"):
        validate_write_range(10, 12, 3)


def test_compute_replace_multi_rejects_overlapping_ranges() -> None:
    lines = ["a", "b", "c", "d"]
    with pytest.raises(ValueError, match="Overlapping"):
        compute_replace_lines_multi(lines, [(1, 2, ["x"]), (2, 3, ["y"])])


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_persist_plain_text_file_metadata_updates_files_row_only(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    f = tmp_path / "n.md"
    f.write_text("# hi\n", encoding="utf-8")
    db = MagicMock()
    db.select.return_value = [{"id": 7}]
    out = persist_plain_text_file_metadata(
        database=db,
        project_id="p1",
        absolute_path=f,
        normalized_path="/abs/n.md",
        source_code="# hi\n",
    )
    assert out["success"] is True
    assert out.get("metadata_only") is True
    db.update_file.assert_called_once()
    db.create_file.assert_not_called()


def test_text_file_handler_registration_ready() -> None:
    h = TextFileHandler()
    assert h.handler_id == HANDLER_TEXT
    assert h.ready_for_all_operations_schema()


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_md_save_apply_does_not_call_ast_or_batch_file_data(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    fp = tmp_path / "readme.md"
    fp.write_text("before\n", encoding="utf-8")
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="readme.md",
        handler_id=HANDLER_TEXT,
        operation="save",
        dry_run=False,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "content": "after\n",
        },
    )
    out = h.save(req)
    assert out.success is True
    assert out.changed is True
    assert fp.read_text(encoding="utf-8") == "after\n"


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_txt_replace_apply_no_ast_or_batch(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    fp = tmp_path / "note.txt"
    fp.write_text("one\ntwo\nthree\n", encoding="utf-8")
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="note.txt",
        handler_id=HANDLER_TEXT,
        operation="replace",
        dry_run=False,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "start_line": 2,
            "end_line": 2,
            "new_lines": ["TWO"],
        },
    )
    res = h.replace(req)
    assert res.success is True
    assert fp.read_text(encoding="utf-8") == "one\nTWO\nthree"


@patch(
    "code_analysis.core.database_client.file_data_batch.update_file_data_atomic_batch",
    side_effect=_reject_batch,
)
@patch("ast.parse", side_effect=_reject_ast)
def test_save_dry_run_returns_diff_without_writing_disk(
    _mock_ast_parse: MagicMock,
    _mock_batch: MagicMock,
    tmp_path: Path,
) -> None:
    fp = tmp_path / "x.md"
    fp.write_text("alpha\nbeta\n", encoding="utf-8")
    before = fp.read_bytes()
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="x.md",
        handler_id=HANDLER_TEXT,
        operation="save",
        dry_run=True,
        diff=True,
        backup=False,
        extra={
            "absolute_path": fp,
            "content": "omega\nsigma\n",
        },
    )
    out = h.save(req)
    assert out.success is True
    assert out.changed is True
    assert out.dry_run is True
    assert "would_change" in out.data
    d = str(out.data.get("diff", ""))
    assert d.strip() != ""
    assert fp.read_bytes() == before


@pytest.mark.parametrize("suffix", ["md", "txt"])
def test_replace_diff_true_unified_diff_and_changed_ranges(
    suffix: str,
    tmp_path: Path,
) -> None:
    fp = tmp_path / f"d.{suffix}"
    fp.write_text("keep\nDROP\ntail\n", encoding="utf-8")
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path=str(fp.name),
        handler_id=HANDLER_TEXT,
        operation="replace",
        dry_run=True,
        diff=True,
        backup=False,
        extra={
            "absolute_path": fp,
            "start_line": 2,
            "end_line": 2,
            "new_lines": ["MID"],
        },
    )
    res = h.replace(req)
    assert res.success is True
    diff_s = str(res.data.get("diff", "")).strip()
    assert "@@" in diff_s or "---" in diff_s
    clr = res.data.get("changed_line_ranges")
    assert isinstance(clr, list)
    assert clr  # edits to line 2 surface in merged after-text ranges


def test_multi_range_replace_second_range_out_of_bounds_file_unchanged(
    tmp_path: Path,
) -> None:
    fp = tmp_path / "m.md"
    fp.write_text("a\nb\nc\nd\ne\nf\ng\nh\ni\nj\n", encoding="utf-8")  # 10 lines
    before = fp.read_bytes()
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="m.md",
        handler_id=HANDLER_TEXT,
        operation="replace",
        dry_run=False,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "replacements": [(1, 1, ["A"]), (99, 99, ["oops"])],
        },
    )
    res = h.replace(req)
    assert res.success is False
    assert res.code == "INVALID_RANGE"
    assert fp.read_bytes() == before


def test_overlapping_replacements_rejected_before_replace_write(
    tmp_path: Path,
) -> None:
    fp = tmp_path / "o.md"
    fp.write_text("a\nb\nc\n", encoding="utf-8")
    before = fp.read_bytes()
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="o.md",
        handler_id=HANDLER_TEXT,
        operation="replace",
        dry_run=False,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "replacements": [(1, 2, ["x"]), (2, 3, ["y"])],
        },
    )
    res = h.replace(req)
    assert res.success is False
    assert fp.read_bytes() == before


@pytest.mark.parametrize(
    ("suffix", "basename"),
    [
        (".json", "bad.json"),
        (".yaml", "bad.yaml"),
        (".yml", "bad.yml"),
        (".py", "bad.py"),
    ],
)
def test_text_handler_rejects_wrong_suffix(
    suffix: str,
    basename: str,
    tmp_path: Path,
) -> None:
    fp = tmp_path / basename
    (
        fp.write_text("{}", encoding="utf-8")
        if suffix == ".json"
        else fp.write_text("x\n", encoding="utf-8")
    )
    h = TextFileHandler()
    for operation, extras in (
        (
            "read",
            {"start_line": 1, "end_line": 1},
        ),
        (
            "save",
            {"content": "y"},
        ),
        (
            "replace",
            {"start_line": 1, "end_line": 1, "new_lines": ["z"]},
        ),
        (
            "delete",
            {"delete_full_file": True},
        ),
    ):
        req = FileHandlerRequest(
            project_id="p",
            file_path=basename,
            handler_id=HANDLER_TEXT,
            operation=operation,
            dry_run=True,
            diff=False,
            backup=False,
            extra={"absolute_path": fp, **extras},
        )
        meth = getattr(h, operation)
        res = meth(req)
        assert res.success is False, (operation, suffix)
        msg = str(res.message or "").lower()
        assert "suffix" in msg or "not a configured plain-text" in msg


def test_read_md_and_txt_return_lines(tmp_path: Path) -> None:
    h = TextFileHandler()
    for name in ("h.md", "h.txt"):
        fp = tmp_path / name
        fp.write_text("uno\ndos\ntres\n", encoding="utf-8")
        req = FileHandlerRequest(
            project_id="p",
            file_path=name,
            handler_id=HANDLER_TEXT,
            operation="read",
            dry_run=False,
            diff=False,
            backup=False,
            extra={
                "absolute_path": fp,
                "start_line": 1,
                "end_line": 2,
            },
        )
        out = h.read(req)
        assert out.success is True
        lines = list(out.data.get("lines") or [])
        assert lines == ["uno", "dos"]


def test_delete_range_dry_run_leaves_bytes_unchanged(tmp_path: Path) -> None:
    fp = tmp_path / "d.md"
    fp.write_text("a\nb\nc\n", encoding="utf-8")
    before = fp.read_bytes()
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="d.md",
        handler_id=HANDLER_TEXT,
        operation="delete",
        dry_run=True,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "start_line": 2,
            "end_line": 2,
        },
    )
    res = h.delete(req)
    assert res.success is True
    assert res.dry_run is True
    assert fp.read_bytes() == before


def test_delete_range_apply_writes(tmp_path: Path) -> None:
    fp = tmp_path / "d.md"
    fp.write_text("a\nb\nc\n", encoding="utf-8")
    h = TextFileHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="d.md",
        handler_id=HANDLER_TEXT,
        operation="delete",
        dry_run=False,
        diff=False,
        backup=False,
        extra={
            "absolute_path": fp,
            "start_line": 2,
            "end_line": 2,
        },
    )
    res = h.delete(req)
    assert res.success is True
    assert res.changed is True
    assert fp.read_text(encoding="utf-8") == "a\nc"
