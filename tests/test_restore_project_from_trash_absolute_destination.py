"""
Tests for restore_project_from_trash absolute move destination (bug c8ad0c21).

``RestoreProjectFromTrashMCPCommand`` used to fetch the project row via a raw
``database.select("projects", ...)`` call and treat the stored ``root_path``
column as if it were already an absolute filesystem path. Since stage-2
migration, ``projects.root_path`` under a ``watch_dir_id`` stores only the
folder-name segment under that watch directory (see
``code_analysis.core.project_root_path`` module docstring), so the raw value
fed straight into ``shutil.move`` produced a bogus (often relative) target
and could raise ``PermissionError``. The fix routes the fetch through the
domain function ``get_project`` (which resolves ``root_path`` to a canonical
absolute path via ``enrich_project_dict_resolve_root_path``), with a
``require_exists=False`` re-resolution fallback for the case where the
project's folder currently lives under ``trash_dir`` (so it no longer exists
at its watch-relative location and the existence-gated resolution baked into
``get_project`` returns "").

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.project_management_mcp_commands.restore_project_from_trash import (
    RestoreProjectFromTrashMCPCommand,
)
from code_analysis.core.database_client.objects.project import Project
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


def _no_active_files_db() -> MagicMock:
    """Return a fake driver whose active-files COUNT(*) query is always 0."""
    db = MagicMock()
    db.disconnect = MagicMock()
    db.execute = MagicMock(return_value={"data": [{"active": 0}]})
    return db


@pytest.mark.asyncio
async def test_restore_uses_get_project_and_moves_to_absolute_destination(
    tmp_path: Path,
) -> None:
    """shutil.move destination is the absolute root_path from get_project()."""
    project_id = "11111111-1111-4111-8111-111111111111"
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash_folder_name = "myproj_2026-07-22T10-00-00Z"
    source = trash_dir / trash_folder_name
    source.mkdir()

    absolute_root = tmp_path / "watched" / "myproj"
    project = Project(id=project_id, root_path=str(absolute_root), name="myproj")

    db = _no_active_files_db()
    cmd = RestoreProjectFromTrashMCPCommand()

    with (
        patch.object(cmd, "_resolve_config_path", return_value=tmp_path / "config.json"),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(trash_dir=trash_dir),
        ),
        patch(
            "code_analysis.core.trash_utils.get_project_id_from_trash_folder",
            return_value=project_id,
        ),
        patch.object(
            RestoreProjectFromTrashMCPCommand,
            "_open_database_from_config",
            return_value=db,
        ),
        patch(
            "code_analysis.core.database_driver_pkg.domain.projects.get_project",
            return_value=project,
        ),
        patch(
            "code_analysis.commands.clear_project_data_impl.unmark_project_deleted_impl",
            new=AsyncMock(return_value=None),
        ),
        patch("shutil.move") as mock_move,
    ):
        result = await cmd.execute(trash_folder_name=trash_folder_name)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    mock_move.assert_called_once_with(str(source), str(absolute_root))
    assert result.data["root_path"] == str(absolute_root)
    assert Path(result.data["root_path"]).is_absolute()


@pytest.mark.asyncio
async def test_restore_falls_back_to_require_exists_false_when_root_path_empty(
    tmp_path: Path,
) -> None:
    """When get_project() resolves root_path to "" (trashed folder no longer at
    its watch-relative location), the command re-resolves without requiring
    on-disk existence rather than treating "" as the destination."""
    project_id = "22222222-2222-4222-8222-222222222222"
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash_folder_name = "otherproj_2026-07-22T10-00-00Z"
    source = trash_dir / trash_folder_name
    source.mkdir()

    absolute_root = tmp_path / "watched" / "otherproj"
    # get_project()'s existence-gated resolution failed -> root_path == "".
    project = Project(
        id=project_id, root_path="", name="otherproj", watch_dir_id="wd1"
    )

    db = _no_active_files_db()
    cmd = RestoreProjectFromTrashMCPCommand()

    with (
        patch.object(cmd, "_resolve_config_path", return_value=tmp_path / "config.json"),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(trash_dir=trash_dir),
        ),
        patch(
            "code_analysis.core.trash_utils.get_project_id_from_trash_folder",
            return_value=project_id,
        ),
        patch.object(
            RestoreProjectFromTrashMCPCommand,
            "_open_database_from_config",
            return_value=db,
        ),
        patch(
            "code_analysis.core.database_driver_pkg.domain.projects.get_project",
            return_value=project,
        ),
        patch(
            "code_analysis.core.project_root_path.resolve_project_root_absolute_str",
            return_value=str(absolute_root),
        ) as mock_resolve,
        patch(
            "code_analysis.commands.clear_project_data_impl.unmark_project_deleted_impl",
            new=AsyncMock(return_value=None),
        ),
        patch("shutil.move") as mock_move,
    ):
        result = await cmd.execute(trash_folder_name=trash_folder_name)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    mock_resolve.assert_called_once()
    assert mock_resolve.call_args.kwargs["require_exists"] is False
    mock_move.assert_called_once_with(str(source), str(absolute_root))


@pytest.mark.asyncio
async def test_restore_returns_error_when_root_path_unresolvable(
    tmp_path: Path,
) -> None:
    """Neither get_project() nor the require_exists=False fallback resolve a
    root path -> a clear error is returned instead of moving to cwd."""
    project_id = "33333333-3333-4333-8333-333333333333"
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash_folder_name = "gone_2026-07-22T10-00-00Z"
    source = trash_dir / trash_folder_name
    source.mkdir()

    project = Project(id=project_id, root_path="", name="gone", watch_dir_id=None)

    db = _no_active_files_db()
    cmd = RestoreProjectFromTrashMCPCommand()

    with (
        patch.object(cmd, "_resolve_config_path", return_value=tmp_path / "config.json"),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(trash_dir=trash_dir),
        ),
        patch(
            "code_analysis.core.trash_utils.get_project_id_from_trash_folder",
            return_value=project_id,
        ),
        patch.object(
            RestoreProjectFromTrashMCPCommand,
            "_open_database_from_config",
            return_value=db,
        ),
        patch(
            "code_analysis.core.database_driver_pkg.domain.projects.get_project",
            return_value=project,
        ),
        patch(
            "code_analysis.core.project_root_path.resolve_project_root_absolute_str",
            return_value="",
        ),
        patch("shutil.move") as mock_move,
    ):
        result = await cmd.execute(trash_folder_name=trash_folder_name)

    # ValidationError hardcodes its own .code == "VALIDATION_ERROR" (see
    # core.exceptions.ValidationError); _handle_error prefers error.code over
    # the passed error_code argument, so all ValidationError branches in this
    # module (PROJECT_NOT_FOUND, NOT_IN_TRASH, TARGET_EXISTS, and this one)
    # surface as "VALIDATION_ERROR" -- pre-existing behavior, not in scope here.
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "Cannot resolve original root path" in result.message
    mock_move.assert_not_called()


def test_module_no_longer_selects_projects_table_directly() -> None:
    """Regression guard: the raw `database.select("projects", ...)` fetch that
    caused bug c8ad0c21 (relative root_path fed straight to shutil.move) must
    not be reintroduced; the module must fetch via the get_project domain
    function instead."""
    import inspect

    import code_analysis.commands.project_management_mcp_commands.restore_project_from_trash as module

    source = inspect.getsource(module)
    assert 'database.select("projects"' not in source
    assert "from ...core.database_driver_pkg.domain.projects import get_project" in source
