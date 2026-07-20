"""
Regression test for the restore-scan project resolution call site.

``RestoreDatabaseFromConfigMCPCommand`` (database_restore_mcp_commands.py) used to
call ``BaseMCPCommand._get_or_create_project(db, str(scan_root), scan_root.name)``,
a classmethod that never existed anywhere in the codebase (dead reference —
planner todo 268ba0e5's sibling defect 3ab77825). The call site now uses the
existing ``BaseMCPCommand._get_project_id(db, root_path)`` resolve-or-create
helper instead, exactly as the restore-scan loop invokes it (positional
``db``, ``scan_root`` — a ``Path``, no ``project_id``). This exercises that
exact call shape against a stub ``DatabaseClient``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from code_analysis.commands.base_mcp_command import BaseMCPCommand


def test_base_mcp_command_has_no_dead_get_or_create_project_classmethod() -> None:
    """Guard against reintroducing the dead ``_get_or_create_project`` reference."""
    assert not hasattr(BaseMCPCommand, "_get_or_create_project")


def test_get_project_id_existing_root_path_returns_existing_id_no_insert() -> None:
    """restore-scan call shape: root already registered -> existing id, no insert."""
    scan_root = Path("/watched/some_project")
    mock_db = MagicMock()

    with patch.object(
        BaseMCPCommand,
        "_get_project_id_by_root_path",
        return_value="existing-project-id",
    ):
        result = BaseMCPCommand._get_project_id(mock_db, scan_root)

    assert result == "existing-project-id"
    mock_db.insert_project_row.assert_not_called()


def test_get_project_id_creates_new_project_when_none_exists() -> None:
    """restore-scan call shape: no existing row -> a new project id is created."""
    scan_root = Path("/watched/brand_new_project")
    mock_db = MagicMock()
    mock_db.resolve_watch_dir_id_for_project_root.return_value = None

    with (
        patch.object(BaseMCPCommand, "_get_project_id_by_root_path", return_value=None),
        patch(
            "code_analysis.core.project_root_path.persist_projects_root_path_stored_value",
            return_value="brand_new_project",
        ),
    ):
        result = BaseMCPCommand._get_project_id(mock_db, scan_root)

    assert isinstance(result, str) and result
    mock_db.insert_project_row.assert_called_once()
    call_args = mock_db.insert_project_row.call_args
    assert call_args.args == (result, "brand_new_project", "brand_new_project")
    assert call_args.kwargs == {"watch_dir_id": None}
