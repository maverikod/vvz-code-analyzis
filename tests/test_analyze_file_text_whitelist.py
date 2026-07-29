"""
Tests for ``analyze_file``'s non-Python text-whitelist branch (bug cluster
688d2d01 / 13945588 / 597ea8c5 / fe1cf739): a whitelisted non-Python file gets
a ``files`` row (lockable ``file_id``) and ``code_content`` (fulltext-visible),
but must never enter the Python CST/AST/entity pipeline.

Follows the ``analyze_file`` mocking conventions of
``tests/test_last_modified_indexing_and_file_row.py`` (module-level function
patches via ``code_analysis.commands.update_indexes_analyzer.<name>``, a
minimal ``_Db`` stand-in with only the methods actually invoked).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

from code_analysis.commands.update_indexes_analyzer import analyze_file


class _RecordingDb:
    """Minimal DB double: records ``execute`` calls, no real storage."""

    def __init__(self) -> None:
        """Initialise the recorder."""
        self.executed: List[Tuple[str, Any]] = []
        self._driver_type = "sqlite"

    def get_file_by_path(self, p: str, pid: str) -> None:
        """Return get file by path (no existing row -> always None)."""
        return None

    def execute(self, sql: str, params: Any = None) -> Dict[str, Any]:
        """Record and no-op every statement (DELETE FROM code_content[_fts])."""
        self.executed.append((sql, params))
        return {"data": [], "affected_rows": 0}


def _patched(db: _RecordingDb, file_id: str):
    """Build the standard patch set analyze_file needs for a fresh-file run."""
    return (
        patch(
            "code_analysis.commands.update_indexes_analyzer.get_file_by_path",
            lambda driver, path, project_id, include_deleted=False: driver.get_file_by_path(
                path, project_id
            ),
        ),
        patch(
            "code_analysis.commands.update_indexes_analyzer.add_file",
            return_value=file_id,
        ),
        patch("code_analysis.commands.update_indexes_analyzer.add_code_content"),
        patch(
            "code_analysis.commands.update_indexes_analyzer.sync_file_to_db_atomic"
        ),
    )


def test_toml_file_gets_code_content_and_skips_python_pipeline() -> None:
    """A whitelisted .toml file: files row created, code_content mirrored, no CST."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "pyproject.toml"
        path.write_text('[tool.verify]\nname = "x"\n', encoding="utf-8")
        file_id = str(uuid.uuid4())

        db = _RecordingDb()
        p1, p2, p3, p4 = _patched(db, file_id)
        with p1, p2 as add_file_mock, p3 as add_code_content_mock, p4 as sync_mock:
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )

        assert out["status"] == "success"
        assert out.get("text_indexed") is True
        add_file_mock.assert_called_once()
        sync_mock.assert_not_called()  # never enters the Python CST/AST pipeline
        add_code_content_mock.assert_called_once()
        _, call_kwargs = add_code_content_mock.call_args
        # add_code_content(driver, file_id, entity_type, entity_name, content, docstring, entity_id=...)
        args = add_code_content_mock.call_args.args
        assert args[1] == file_id
        assert args[2] == "file"
        assert args[4] == '[tool.verify]\nname = "x"\n'


def test_shell_script_and_gitignore_get_file_rows_and_content() -> None:
    """Shell scripts and .gitignore (bugs 13945588 / 597ea8c5) take the same path."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        for name, content in (
            ("script.sh", '#!/bin/sh\necho "hi"\n'),
            (".gitignore", "*.pyc\n__pycache__/\n"),
        ):
            path = temp_dir / name
            path.write_text(content, encoding="utf-8")
            file_id = str(uuid.uuid4())
            db = _RecordingDb()
            p1, p2, p3, p4 = _patched(db, file_id)
            with p1, p2 as add_file_mock, p3 as add_code_content_mock, p4 as sync_mock:
                out = analyze_file(
                    database=db,
                    file_path=path,
                    project_id=project_id,
                    root_path=temp_dir,
                )
            assert out["status"] == "success", name
            assert out.get("text_indexed") is True, name
            add_file_mock.assert_called_once()
            sync_mock.assert_not_called()
            add_code_content_mock.assert_called_once()


def test_markdown_falls_back_to_lightweight_pipeline_without_docs_indexing() -> None:
    """A .md file with no docs_indexing snapshot supplied still gets code_content.

    Distinguishes the general text whitelist from the pre-existing, config-gated
    docs_indexing feature: today's only production caller of analyze_file that
    walks non-.py files (update_indexes) never supplies docs_indexing, so a
    plain notes.md must not hard-error (previous behavior) -- it must fall back
    to the same lightweight mirror as .toml/.sh/.gitignore.
    """
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "notes.md"
        path.write_text("# Notes\n\nhello\n", encoding="utf-8")
        file_id = str(uuid.uuid4())

        db = _RecordingDb()
        p1, p2, p3, p4 = _patched(db, file_id)
        with p1, p2, p3 as add_code_content_mock, p4 as sync_mock:
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
                docs_indexing=None,
            )

        assert out["status"] == "success"
        assert out.get("text_indexed") is True
        sync_mock.assert_not_called()
        add_code_content_mock.assert_called_once()


def test_python_file_still_uses_cst_pipeline_unchanged() -> None:
    """A .py file is never routed through the lightweight text branch."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "module.py"
        path.write_text("def f():\n    return 1\n", encoding="utf-8")
        file_id = str(uuid.uuid4())

        db = _RecordingDb()
        p1, p2, p3, p4 = _patched(db, file_id)
        with p1, p2, p3 as add_code_content_mock, p4 as sync_mock, patch(
            "code_analysis.commands.update_indexes_analyzer.mark_file_needs_chunking"
        ):
            sync_mock.return_value = {"success": True, "entities_updated": 0}
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )

        assert out["status"] == "success"
        assert "text_indexed" not in out
        sync_mock.assert_called_once()  # Python CST/AST pipeline still runs
        add_code_content_mock.assert_not_called()  # lightweight mirror never fires


def test_oversized_whitelisted_file_is_skipped_not_indexed() -> None:
    """Bug fe1cf739 hardening: files over the size bound are skipped, not partially indexed."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "big.toml"
        path.write_text("x = 1\n", encoding="utf-8")

        db = _RecordingDb()
        p1, p2, p3, p4 = _patched(db, str(uuid.uuid4()))
        with p1, p2 as add_file_mock, p3 as add_code_content_mock, p4:
            with patch(
                "code_analysis.commands.update_indexes_analyzer.TEXT_INDEX_MAX_BYTES",
                1,
            ):
                out = analyze_file(
                    database=db,
                    file_path=path,
                    project_id=project_id,
                    root_path=temp_dir,
                )

        assert out["status"] == "skipped"
        assert out["reason"] == "text_index_too_large"
        add_file_mock.assert_not_called()
        add_code_content_mock.assert_not_called()


def test_binary_content_whitelisted_extension_is_skipped() -> None:
    """A NUL byte in a whitelisted-extension file is treated as binary and skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        temp_dir = Path(tmp)
        project_id = str(uuid.uuid4())
        path = temp_dir / "weird.cfg"
        path.write_bytes(b"abc\x00def")

        db = _RecordingDb()
        p1, p2, p3, p4 = _patched(db, str(uuid.uuid4()))
        with p1, p2 as add_file_mock, p3 as add_code_content_mock, p4:
            out = analyze_file(
                database=db,
                file_path=path,
                project_id=project_id,
                root_path=temp_dir,
            )

        assert out["status"] == "skipped"
        assert out["reason"] == "text_index_binary_content"
        add_file_mock.assert_not_called()
        add_code_content_mock.assert_not_called()
