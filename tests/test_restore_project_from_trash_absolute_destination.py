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

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
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


def _fake_driver_for_uuid_watch_dir(
    *, watch_dir_id: str, absolute_path: str
) -> MagicMock:
    """Return a fake driver that answers the three SQL shapes this path needs.

    Routes on substrings of the SQL text (the same approach ``MagicMock``-based
    driver fakes in this file already use) to three distinct queries issued
    along the trash-restore fallback path once ``watch_dir_id`` is a proper
    ``str``: (1) the active-files ``COUNT(*)`` gate in
    ``restore_project_from_trash.py``, always 0 (project is fully trashed);
    (2) ``fetch_watch_dir_absolute_path``'s single-row lookup by
    ``watch_dir_id``; (3) ``fetch_all_watch_dir_absolute_paths``'s full-table
    scan. Both (2) and (3) resolve to the same on-disk ``absolute_path`` so the
    real (unmocked) ``resolve_project_root_absolute_str`` can walk all the way
    to a concrete destination once the UUID-vs-str bug is fixed.
    """

    def _execute(sql: str, params: tuple = (), **_kwargs: object) -> Dict[str, Any]:
        """Return a canned result keyed off which query ``sql`` is."""
        text = " ".join(sql.split())
        if "COUNT(*) as active" in text:
            return {"data": [{"active": 0}]}
        if "FROM watch_dir_paths" in text and "LIMIT 1" in text:
            if params and len(params) >= 2 and str(params[1]) == watch_dir_id:
                return {"data": [{"absolute_path": absolute_path}]}
            return {"data": []}
        if "FROM watch_dir_paths" in text:
            return {
                "data": [
                    {"watch_dir_id": watch_dir_id, "absolute_path": absolute_path}
                ]
            }
        return {"data": []}

    db = MagicMock()
    db.disconnect = MagicMock()
    db.execute = MagicMock(side_effect=_execute)
    # project_root_path.py prefers a `_fetchone`/`_fetchall` fast path over
    # `execute` when present; a bare MagicMock auto-vivifies both as truthy
    # callables that return an unconfigured MagicMock (not a dict), which
    # would short-circuit resolution to None before `execute` is ever
    # reached. Disable them so the fallback in
    # fetch_watch_dir_absolute_path/fetch_all_watch_dir_absolute_paths goes
    # through `execute` (the routing this fake actually implements).
    db._fetchone = None
    db._fetchall = None
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
async def test_restore_fallback_survives_uuid_typed_watch_dir_id_from_get_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test (bug c8ad0c21's own regression, commit 07a704ec).

    ``watch_dir_id`` is a native ``UUID`` column (see
    ``code_analysis.core.database.schema_definition_tables_core``). With the
    PostgreSQL driver, ``PostgreSQLOperations.select`` (``postgres_operations.py``)
    builds rows via plain ``dict(zip(cols, row))`` with no UUID-to-str coercion,
    and neither ``Project.from_dict`` (``objects/project.py``) nor
    ``enrich_project_dict_resolve_root_path`` (``core/project_root_path.py``,
    which only rewrites ``root_path``) coerce ``watch_dir_id`` either. So the
    real ``get_project()`` domain function hands back ``Project.watch_dir_id``
    as a ``uuid.UUID`` object, faithfully reproduced here instead of the plain
    ``str`` the earlier fixture tests used.

    Before the fix, feeding that ``UUID`` straight into
    ``resolve_project_root_absolute_str``'s ``watch_dir_id`` kwarg reaches
    ``resolve_projects_root_path_row_to_absolute_str``'s
    ``wd = (watch_dir_id or "").strip() or None`` (project_root_path.py:191)
    and raises ``AttributeError: 'UUID' object has no attribute 'strip'``,
    which ``RestoreProjectFromTrashMCPCommand.execute`` catches and reports as
    ``RESTORE_PROJECT_FROM_TRASH_ERROR`` instead of restoring the project.

    This test deliberately does NOT mock ``resolve_project_root_absolute_str``
    (unlike the sibling fallback test above) -- it exercises the real function
    so the UUID reaches the exact ``.strip()`` call that crashed live.
    """
    monkeypatch.setenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", "test-instance")

    project_id = "44444444-4444-4444-8444-444444444444"
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    trash_folder_name = "uuidproj_2026-07-23T10-00-00Z"
    source = trash_dir / trash_folder_name
    source.mkdir()

    watch_root = tmp_path / "watched"
    watch_root.mkdir()
    absolute_root = watch_root / "uuidproj"
    watch_dir_id = uuid.uuid4()

    # get_project()'s existence-gated resolution fails for a trashed folder
    # (it no longer exists at its watch-relative location) -> root_path == "".
    project = Project(
        id=project_id, root_path="", name="uuidproj", watch_dir_id=watch_dir_id
    )

    db = _fake_driver_for_uuid_watch_dir(
        watch_dir_id=str(watch_dir_id), absolute_path=str(watch_root)
    )
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
