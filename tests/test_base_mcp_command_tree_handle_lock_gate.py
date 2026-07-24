"""
Tests for the tree-handle lock gate helpers on BaseMCPCommand (bug 88f06abc
enforcement-gap audit): ``_resolve_project_id_for_disk_path`` and
``_project_locked_error_for_path``.

These back-fill the coverage the whole-project exclusive lock's ``run()``
gate cannot reach: commands that identify their target file only via an
in-memory ``tree_id`` handle (the ``cst_*``/``json_*`` tree family), which
often carry no literal ``project_id`` kwarg at all.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand

_PID = "550e8400-e29b-41d4-a716-446655440000"
_LOCK_ROW = {
    "project_id": _PID,
    "locked_at": 1.0,
    "owner": "rename_project:abc",
    "reason": "renaming",
}


class TestResolveProjectIdForDiskPath:
    """``_resolve_project_id_for_disk_path`` walks up for a ``projectid`` marker."""

    def test_finds_marker_at_project_root(self, tmp_path: Path) -> None:
        """A projectid file at the walked-to root resolves its id field."""
        (tmp_path / "projectid").write_text(
            json.dumps({"id": _PID, "description": "x"}), encoding="utf-8"
        )
        nested = tmp_path / "src" / "pkg" / "module.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("x = 1\n", encoding="utf-8")

        found = BaseMCPCommand._resolve_project_id_for_disk_path(str(nested))

        assert found == _PID

    def test_no_marker_anywhere_returns_none(self, tmp_path: Path) -> None:
        """No projectid file on the walk up to the filesystem root -> None."""
        nested = tmp_path / "src" / "module.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("x = 1\n", encoding="utf-8")

        found = BaseMCPCommand._resolve_project_id_for_disk_path(str(nested))

        assert found is None

    def test_malformed_marker_fails_open(self, tmp_path: Path) -> None:
        """A corrupt projectid file returns None instead of raising."""
        (tmp_path / "projectid").write_text("not json", encoding="utf-8")
        nested = tmp_path / "module.py"
        nested.write_text("x = 1\n", encoding="utf-8")

        found = BaseMCPCommand._resolve_project_id_for_disk_path(str(nested))

        assert found is None

    def test_marker_without_id_field_returns_none(self, tmp_path: Path) -> None:
        """A projectid file present but missing 'id' fails open, not crashes."""
        (tmp_path / "projectid").write_text(
            json.dumps({"description": "no id here"}), encoding="utf-8"
        )
        nested = tmp_path / "module.py"
        nested.write_text("x = 1\n", encoding="utf-8")

        found = BaseMCPCommand._resolve_project_id_for_disk_path(str(nested))

        assert found is None


class TestProjectLockedErrorForPath:
    """``_project_locked_error_for_path`` mirrors ``run()``'s gate shape."""

    def test_locked_project_returns_project_locked_error(self, tmp_path: Path) -> None:
        """A resolvable, locked project yields a PROJECT_LOCKED ErrorResult."""
        (tmp_path / "projectid").write_text(
            json.dumps({"id": _PID}), encoding="utf-8"
        )
        target = tmp_path / "module.py"
        target.write_text("x = 1\n", encoding="utf-8")

        fake_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand, "_open_database_from_config", return_value=fake_db
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                return_value=_LOCK_ROW,
            ) as mock_get_lock,
        ):
            result = BaseMCPCommand._project_locked_error_for_path(str(target))

        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_LOCKED"
        assert result.details["project_id"] == _PID
        mock_get_lock.assert_called_once_with(fake_db, _PID)
        fake_db.disconnect.assert_called_once()

    def test_unlocked_project_returns_none(self, tmp_path: Path) -> None:
        """A resolvable, unlocked project is a no-op (None)."""
        (tmp_path / "projectid").write_text(
            json.dumps({"id": _PID}), encoding="utf-8"
        )
        target = tmp_path / "module.py"
        target.write_text("x = 1\n", encoding="utf-8")

        fake_db = MagicMock()
        with (
            patch.object(
                BaseMCPCommand, "_open_database_from_config", return_value=fake_db
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                return_value=None,
            ),
        ):
            result = BaseMCPCommand._project_locked_error_for_path(str(target))

        assert result is None

    def test_unresolvable_project_never_touches_db(self, tmp_path: Path) -> None:
        """When no owning project can be found, the lock table is not consulted
        at all (fail open without a DB round trip)."""
        target = tmp_path / "module.py"
        target.write_text("x = 1\n", encoding="utf-8")

        with patch(
            "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
        ) as mock_get_lock:
            result = BaseMCPCommand._project_locked_error_for_path(str(target))

        assert result is None
        mock_get_lock.assert_not_called()
