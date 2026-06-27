"""
Regression: full-file overwrite of an existing Python file must persist bytes.

A whole-file save builds a single ``range 1..N`` op (see
``_ops_for_save_new_or_overwrite``). That range spans every top-level statement,
which the per-statement CST rewriter cannot match -- it used to drop the op and
write the *original* bytes back while still reporting ``file_written=True``
(commit said ``uploaded=true`` but canonical bytes never changed).
``run_ops_mode`` now routes such a save as a direct content replacement.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.compose_cst_ops_flow import (
    _is_full_file_overwrite,
    _ops_matched_nothing,
    run_ops_mode,
)
from code_analysis.commands.compose_cst_validation import ops_from_params
from code_analysis.core.file_handlers.python_handler import (
    _ops_for_save_new_or_overwrite,
)

_ORIGINAL = (
    "import os\n"
    "\n"
    "\n"
    "def value():\n"
    '    """:return: the integer one."""\n'
    "    return 1\n"
)

_UPDATED = (
    "import os\n"
    "\n"
    "\n"
    "def value():\n"
    '    """:return: the integer forty two."""\n'
    "    return 42\n"
)


def test_full_overwrite_detection_multi_statement_file(tmp_path: Path) -> None:
    """The synthetic whole-file range op is recognised as a full overwrite."""
    rel = "m.py"
    (tmp_path / rel).write_text(_ORIGINAL, encoding="utf-8")
    ops = _ops_for_save_new_or_overwrite(_UPDATED, root=tmp_path, relative_file=rel)
    parsed = ops_from_params(ops)
    assert _is_full_file_overwrite(parsed, _ORIGINAL) is True


def test_full_overwrite_preview_shows_real_diff(tmp_path: Path) -> None:
    """Preview of a full overwrite reflects the new content (was an empty diff)."""
    rel = "m.py"
    (tmp_path / rel).write_text(_ORIGINAL, encoding="utf-8")
    ops = _ops_for_save_new_or_overwrite(_UPDATED, root=tmp_path, relative_file=rel)
    res = run_ops_mode(
        project_id="p",
        file_path=rel,
        root_path=tmp_path,
        ops=ops,
        apply=False,
        create_backup=False,
        return_diff=True,
        commit_message=None,
        t_start=0.0,
        t_prev=0.0,
        validate_syntax_only=True,
    )
    assert "return 42" in res.data["diff"]
    assert res.data["stats"].get("full_overwrite") is True


def test_full_overwrite_rejects_invalid_python(tmp_path: Path) -> None:
    """A full overwrite with unparseable content fails instead of silently passing."""
    rel = "m.py"
    (tmp_path / rel).write_text(_ORIGINAL, encoding="utf-8")
    ops = _ops_for_save_new_or_overwrite("def (:\n", root=tmp_path, relative_file=rel)
    res = run_ops_mode(
        project_id="p",
        file_path=rel,
        root_path=tmp_path,
        ops=ops,
        apply=False,
        create_backup=False,
        return_diff=False,
        commit_message=None,
        t_start=0.0,
        t_prev=0.0,
        validate_syntax_only=True,
    )
    assert res.code == "CST_REPLACE_ERROR"


def test_ops_matched_nothing_helper() -> None:
    """Guard fires only when nothing was touched yet selectors stayed unmatched."""
    assert _ops_matched_nothing(
        {"replaced": 0, "removed": 0, "created": 0, "unmatched": [{"kind": "function"}]}
    )
    assert not _ops_matched_nothing(
        {"replaced": 1, "removed": 0, "created": 0, "unmatched": []}
    )


def test_full_overwrite_new_source_replaces_whole_file(tmp_path: Path) -> None:
    """The bytes that would be written equal the new content, not the original.

    Before the fix the whole-file range op was dropped and ``run_ops_mode``
    produced ``new_source == source`` (empty diff, original bytes persisted).
    A non-empty diff that both removes the old body and adds the new one proves
    the replacement source is now the full update.
    """
    rel = "m.py"
    (tmp_path / rel).write_text(_ORIGINAL, encoding="utf-8")
    ops = _ops_for_save_new_or_overwrite(_UPDATED, root=tmp_path, relative_file=rel)
    res = run_ops_mode(
        project_id="p",
        file_path=rel,
        root_path=tmp_path,
        ops=ops,
        apply=False,
        create_backup=False,
        return_diff=True,
        commit_message=None,
        t_start=0.0,
        t_prev=0.0,
        validate_syntax_only=True,
    )
    diff = res.data["diff"]
    assert diff.strip(), "full overwrite must not yield an empty (no-op) diff"
    assert "-    return 1" in diff
    assert "+    return 42" in diff
