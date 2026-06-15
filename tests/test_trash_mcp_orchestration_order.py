"""
MCP trash orchestration: DB/FAISS cleanup must run before disk trash deletion.

Contract (resolvable project_id): ``_clear_project_data_impl`` (and optional FAISS
unlink) completes before ``ClearTrashCommand`` / ``PermanentlyDeleteFromTrashCommand``
run.

``clear_trash`` additionally runs DB/FAISS cleanup for soft-deleted projects
(``projects.deleted = 1``) that have no resolvable trash folder, still before
``ClearTrashCommand``.

When no project_id can be resolved (e.g. missing ``projectid`` and non-UUID folder
name), MCP code skips DB/FAISS and only the filesystem command runs — no DB cleanup
ordering applies.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_management_mcp_commands import (
    clear_trash as clear_trash_module,
)
from code_analysis.commands.project_management_mcp_commands.clear_trash import (
    ClearTrashMCPCommand,
)
from code_analysis.commands.project_management_mcp_commands.permanently_delete_from_trash import (
    PermanentlyDeleteFromTrashMCPCommand,
)
from code_analysis.core.storage_paths import StoragePaths


def _storage_paths(tmp_path: Path, trash_dir: Path) -> StoragePaths:
    return StoragePaths(
        sessions_root=tmp_path / "search_sessions",
        log_dir=tmp_path / "logs",
        db_path=tmp_path / "db.sqlite",
        faiss_dir=tmp_path / "faiss",
        locks_dir=tmp_path / "locks",
        queue_dir=None,
        backup_dir=tmp_path / "backups",
        trash_dir=trash_dir,
    )


@pytest.mark.asyncio
async def test_clear_trash_mcp_db_clear_before_disk_command(tmp_path: Path) -> None:
    """Resolvable UUID trash entry: _clear_project_data_impl then ClearTrashCommand."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    pid = str(uuid.uuid4())
    (trash_dir / pid).mkdir()

    storage = _storage_paths(tmp_path, trash_dir)
    call_order: list[object] = []

    async def track_db_clear(_db: object, project_id: str) -> None:
        call_order.append(("db_clear", project_id))

    class SpyClearTrashCommand:
        def __init__(self, trash_dir: str = "", dry_run: bool = False) -> None:
            self._trash_dir = trash_dir
            self._dry_run = dry_run

        def execute(self) -> dict:
            call_order.append("disk_clear")
            return {
                "success": True,
                "removed_count": 1,
                "removed": [pid],
                "dry_run": self._dry_run,
                "trash_dir": self._trash_dir,
            }

    with patch(
        "code_analysis.core.storage_paths.load_raw_config",
        return_value={},
    ), patch(
        "code_analysis.core.storage_paths.resolve_storage_paths",
        return_value=storage,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_config_path",
        return_value=tmp_path / "config.json",
    ), patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=MagicMock(disconnect=MagicMock()),
    ), patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new=AsyncMock(side_effect=track_db_clear),
    ), patch(
        "code_analysis.commands.trash_commands.ClearTrashCommand",
        SpyClearTrashCommand,
    ):
        cmd = ClearTrashMCPCommand()
        result = await cmd.execute(dry_run=False, trash_dir=str(trash_dir))

    assert isinstance(result, SuccessResult)
    assert call_order == [("db_clear", pid), "disk_clear"]


@pytest.mark.asyncio
async def test_clear_trash_mcp_faiss_unlink_after_db_before_disk(
    tmp_path: Path,
) -> None:
    """FAISS unlink (when index exists) occurs after DB clear and before disk command."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    pid = str(uuid.uuid4())
    (trash_dir / pid).mkdir()

    storage = _storage_paths(tmp_path, trash_dir)
    call_order: list[object] = []

    async def track_db_clear(_db: object, project_id: str) -> None:
        call_order.append(("db_clear", project_id))

    mock_faiss_path = MagicMock()
    mock_faiss_path.exists.return_value = True
    mock_faiss_path.unlink.side_effect = lambda: call_order.append("faiss_unlink")

    class SpyClearTrashCommand:
        def __init__(self, trash_dir: str = "", dry_run: bool = False) -> None:
            self._trash_dir = trash_dir
            self._dry_run = dry_run

        def execute(self) -> dict:
            call_order.append("disk_clear")
            return {
                "success": True,
                "removed_count": 1,
                "removed": [pid],
                "dry_run": self._dry_run,
                "trash_dir": self._trash_dir,
            }

    with patch(
        "code_analysis.core.storage_paths.load_raw_config",
        return_value={},
    ), patch(
        "code_analysis.core.storage_paths.resolve_storage_paths",
        return_value=storage,
    ), patch(
        "code_analysis.core.storage_paths.get_faiss_index_path",
        return_value=mock_faiss_path,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_config_path",
        return_value=tmp_path / "config.json",
    ), patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=MagicMock(disconnect=MagicMock()),
    ), patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new=AsyncMock(side_effect=track_db_clear),
    ), patch(
        "code_analysis.commands.trash_commands.ClearTrashCommand",
        SpyClearTrashCommand,
    ):
        cmd = ClearTrashMCPCommand()
        result = await cmd.execute(dry_run=False, trash_dir=str(trash_dir))

    assert isinstance(result, SuccessResult)
    assert call_order == [("db_clear", pid), "faiss_unlink", "disk_clear"]
    mock_faiss_path.unlink.assert_called_once_with()


@pytest.mark.asyncio
async def test_clear_trash_mcp_db_only_soft_deleted_orphan_before_disk(
    tmp_path: Path,
) -> None:
    """Soft-deleted project in DB with no resolvable trash folder: DB clear then disk."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    orphan_pid = str(uuid.uuid4())

    storage = _storage_paths(tmp_path, trash_dir)
    call_order: list[object] = []

    async def track_db_clear(_db: object, project_id: str) -> None:
        call_order.append(("db_clear", project_id))

    class SpyClearTrashCommand:
        def __init__(self, trash_dir: str = "", dry_run: bool = False) -> None:
            self._trash_dir = trash_dir
            self._dry_run = dry_run

        def execute(self) -> dict:
            call_order.append("disk_clear")
            return {
                "success": True,
                "removed_count": 0,
                "removed": [],
                "dry_run": self._dry_run,
                "trash_dir": self._trash_dir,
            }

    with patch(
        "code_analysis.core.storage_paths.load_raw_config",
        return_value={},
    ), patch(
        "code_analysis.core.storage_paths.resolve_storage_paths",
        return_value=storage,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_config_path",
        return_value=tmp_path / "config.json",
    ), patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=MagicMock(disconnect=MagicMock()),
    ), patch.object(
        clear_trash_module,
        "_soft_deleted_project_ids",
        return_value=[orphan_pid],
    ), patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new=AsyncMock(side_effect=track_db_clear),
    ), patch(
        "code_analysis.commands.trash_commands.ClearTrashCommand",
        SpyClearTrashCommand,
    ):
        cmd = ClearTrashMCPCommand()
        result = await cmd.execute(dry_run=False, trash_dir=str(trash_dir))

    assert isinstance(result, SuccessResult)
    assert call_order == [("db_clear", orphan_pid), "disk_clear"]


@pytest.mark.asyncio
async def test_permanently_delete_from_trash_mcp_db_clear_before_disk_command(
    tmp_path: Path,
) -> None:
    """Resolvable trash entry: _clear_project_data_impl then PermanentlyDeleteFromTrashCommand."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    pid = str(uuid.uuid4())
    (trash_dir / pid).mkdir()

    storage = _storage_paths(tmp_path, trash_dir)
    call_order: list[object] = []

    async def track_db_clear(_db: object, project_id: str) -> None:
        call_order.append(("db_clear", project_id))

    class SpyPermanentlyDeleteFromTrashCommand:
        def __init__(self, trash_dir: str = "", trash_folder_name: str = "") -> None:
            self.trash_folder_name = trash_folder_name

        def execute(self) -> dict:
            call_order.append("disk_clear")
            return {
                "success": True,
                "message": "ok",
                "trash_folder_name": self.trash_folder_name,
            }

    with patch(
        "code_analysis.core.storage_paths.load_raw_config",
        return_value={},
    ), patch(
        "code_analysis.core.storage_paths.resolve_storage_paths",
        return_value=storage,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_config_path",
        return_value=tmp_path / "config.json",
    ), patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=MagicMock(disconnect=MagicMock()),
    ), patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new=AsyncMock(side_effect=track_db_clear),
    ), patch(
        "code_analysis.commands.trash_commands.PermanentlyDeleteFromTrashCommand",
        SpyPermanentlyDeleteFromTrashCommand,
    ):
        cmd = PermanentlyDeleteFromTrashMCPCommand()
        result = await cmd.execute(trash_folder_name=pid, trash_dir=str(trash_dir))

    assert isinstance(result, SuccessResult)
    assert call_order == [("db_clear", pid), "disk_clear"]


@pytest.mark.asyncio
async def test_permanently_delete_from_trash_mcp_no_project_id_skips_db_only_disk(
    tmp_path: Path,
) -> None:
    """No resolvable project_id: DB clear is skipped; only filesystem command runs."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()
    folder_name = "legacy_no_projectid_folder"
    (trash_dir / folder_name).mkdir()

    storage = _storage_paths(tmp_path, trash_dir)
    call_order: list[object] = []

    async def track_db_clear(_db: object, project_id: str) -> None:
        call_order.append(("db_clear", project_id))

    class SpyPermanentlyDeleteFromTrashCommand:
        def __init__(self, trash_dir: str = "", trash_folder_name: str = "") -> None:
            self.trash_folder_name = trash_folder_name

        def execute(self) -> dict:
            call_order.append("disk_clear")
            return {
                "success": True,
                "message": "ok",
                "trash_folder_name": self.trash_folder_name,
            }

    mock_open_db = MagicMock(return_value=MagicMock(disconnect=MagicMock()))

    with patch(
        "code_analysis.core.storage_paths.load_raw_config",
        return_value={},
    ), patch(
        "code_analysis.core.storage_paths.resolve_storage_paths",
        return_value=storage,
    ), patch.object(
        BaseMCPCommand,
        "_resolve_config_path",
        return_value=tmp_path / "config.json",
    ), patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        mock_open_db,
    ), patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new=AsyncMock(side_effect=track_db_clear),
    ), patch(
        "code_analysis.commands.trash_commands.PermanentlyDeleteFromTrashCommand",
        SpyPermanentlyDeleteFromTrashCommand,
    ):
        cmd = PermanentlyDeleteFromTrashMCPCommand()
        result = await cmd.execute(
            trash_folder_name=folder_name, trash_dir=str(trash_dir)
        )

    assert isinstance(result, SuccessResult)
    assert call_order == ["disk_clear"]
    mock_open_db.assert_not_called()
