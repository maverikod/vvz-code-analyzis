"""
Tests for the project-exclusive-lock gate on ``clear_trash`` and
``permanently_delete_from_trash`` (bug 88f06abc enforcement-gap audit).

Both commands discover their target ``project_id``(s) internally (from
``projectid`` markers inside trash folders, plus soft-deleted DB rows for
``clear_trash``) rather than taking ``project_id`` as a literal kwarg, so
``BaseMCPCommand.run()``'s fast-fail gate never sees them. ``clear_trash``
now skips any exclusively-locked project on both its DB-clear and its
disk-clear phase instead of processing the whole trash batch blindly;
``permanently_delete_from_trash`` fails fast with ``PROJECT_LOCKED`` for its
single target.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.project_management_mcp_commands.clear_trash import (
    ClearTrashMCPCommand,
)
from code_analysis.commands.project_management_mcp_commands.permanently_delete_from_trash import (
    PermanentlyDeleteFromTrashMCPCommand,
)

_LOCKED_ID = "11111111-1111-4111-8111-111111111111"
_UNLOCKED_ID = "22222222-2222-4222-8222-222222222222"


def _no_soft_deleted_db() -> MagicMock:
    """Return a fake driver whose soft-deleted-projects query is always empty."""
    db = MagicMock()
    db.disconnect = MagicMock()
    db.execute = MagicMock(return_value={"data": []})
    return db


def _make_trash_layout(tmp_path: Path) -> Path:
    """Create a trash_dir with one locked-project folder and one unlocked one."""
    trash_dir = tmp_path / "trash"
    trash_dir.mkdir()

    locked_folder = trash_dir / "locked_2026-07-24T10-00-00Z"
    locked_folder.mkdir()
    (locked_folder / "projectid").write_text(
        json.dumps({"id": _LOCKED_ID}), encoding="utf-8"
    )

    unlocked_folder = trash_dir / "unlocked_2026-07-24T10-00-00Z"
    unlocked_folder.mkdir()
    (unlocked_folder / "projectid").write_text(
        json.dumps({"id": _UNLOCKED_ID}), encoding="utf-8"
    )

    return trash_dir


@pytest.mark.asyncio
async def test_clear_trash_skips_locked_project_among_several(
    tmp_path: Path,
) -> None:
    """clear_trash skips the locked project's DB clear + disk folder, but
    still clears the unlocked project's DB rows and disk folder."""
    trash_dir = _make_trash_layout(tmp_path)
    db = _no_soft_deleted_db()
    cmd = ClearTrashMCPCommand()
    cleared_ids: list[str] = []

    async def _fake_clear(database: object, project_id: str) -> None:
        """Record which project_id the DB-clear phase actually touched."""
        cleared_ids.append(project_id)

    def _fake_is_locked(database: object, project_id: str) -> bool:
        """Only the designated project reports as locked."""
        return project_id == _LOCKED_ID

    with (
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch("code_analysis.core.storage_paths.load_raw_config", return_value={}),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(
                trash_dir=trash_dir, faiss_dir=tmp_path / "faiss"
            ),
        ),
        patch.object(
            ClearTrashMCPCommand, "_open_database_from_config", return_value=db
        ),
        patch(
            "code_analysis.core.project_exclusive_lock.is_project_exclusively_locked",
            side_effect=_fake_is_locked,
        ),
        patch(
            "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
            new=_fake_clear,
        ),
    ):
        result = await cmd.execute(dry_run=False)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert cleared_ids == [_UNLOCKED_ID]
    assert result.data["skipped_locked_project_ids"] == [_LOCKED_ID]

    locked_folder = trash_dir / "locked_2026-07-24T10-00-00Z"
    unlocked_folder = trash_dir / "unlocked_2026-07-24T10-00-00Z"
    assert locked_folder.exists(), "locked project's trash folder must survive"
    assert not unlocked_folder.exists(), "unlocked project's trash folder must be removed"
    assert unlocked_folder.name in result.data["removed"]
    assert locked_folder.name in result.data["skipped_locked"]


@pytest.mark.asyncio
async def test_clear_trash_all_unlocked_removes_everything(tmp_path: Path) -> None:
    """Sanity: with nothing locked, clear_trash behaves exactly as before the
    gap fix (both folders removed, both projects cleared)."""
    trash_dir = _make_trash_layout(tmp_path)
    db = _no_soft_deleted_db()
    cmd = ClearTrashMCPCommand()
    cleared_ids: list[str] = []

    async def _fake_clear(database: object, project_id: str) -> None:
        """Record every project_id the DB-clear phase touched."""
        cleared_ids.append(project_id)

    with (
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch("code_analysis.core.storage_paths.load_raw_config", return_value={}),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(
                trash_dir=trash_dir, faiss_dir=tmp_path / "faiss"
            ),
        ),
        patch.object(
            ClearTrashMCPCommand, "_open_database_from_config", return_value=db
        ),
        patch(
            "code_analysis.core.project_exclusive_lock.is_project_exclusively_locked",
            return_value=False,
        ),
        patch(
            "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
            new=_fake_clear,
        ),
    ):
        result = await cmd.execute(dry_run=False)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert set(cleared_ids) == {_LOCKED_ID, _UNLOCKED_ID}
    assert result.data["skipped_locked_project_ids"] == []
    assert not trash_dir.exists() or list(trash_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_permanently_delete_from_trash_fails_fast_when_locked(
    tmp_path: Path,
) -> None:
    """permanently_delete_from_trash refuses a locked target with PROJECT_LOCKED
    and does not touch DB or disk."""
    trash_dir = _make_trash_layout(tmp_path)
    db = _no_soft_deleted_db()
    cmd = PermanentlyDeleteFromTrashMCPCommand()

    with (
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch("code_analysis.core.storage_paths.load_raw_config", return_value={}),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(
                trash_dir=trash_dir, faiss_dir=tmp_path / "faiss"
            ),
        ),
        patch.object(
            PermanentlyDeleteFromTrashMCPCommand,
            "_open_database_from_config",
            return_value=db,
        ),
        patch(
            "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            return_value={
                "project_id": _LOCKED_ID,
                "locked_at": 1.0,
                "owner": "rename_project:abc",
                "reason": "renaming",
            },
        ),
    ):
        result = await cmd.execute(
            trash_folder_name="locked_2026-07-24T10-00-00Z"
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "PROJECT_LOCKED"
    assert (trash_dir / "locked_2026-07-24T10-00-00Z").exists()


@pytest.mark.asyncio
async def test_permanently_delete_from_trash_unlocked_still_deletes(
    tmp_path: Path,
) -> None:
    """Sanity: an unlocked target is still deleted as before the gap fix."""
    trash_dir = _make_trash_layout(tmp_path)
    db = _no_soft_deleted_db()
    cmd = PermanentlyDeleteFromTrashMCPCommand()

    with (
        patch.object(
            cmd, "_resolve_config_path", return_value=tmp_path / "config.json"
        ),
        patch("code_analysis.core.storage_paths.load_raw_config", return_value={}),
        patch(
            "code_analysis.core.storage_paths.resolve_storage_paths",
            return_value=SimpleNamespace(
                trash_dir=trash_dir, faiss_dir=tmp_path / "faiss"
            ),
        ),
        patch.object(
            PermanentlyDeleteFromTrashMCPCommand,
            "_open_database_from_config",
            return_value=db,
        ),
        patch(
            "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            return_value=None,
        ),
        patch(
            "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await cmd.execute(
            trash_folder_name="unlocked_2026-07-24T10-00-00Z"
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert not (trash_dir / "unlocked_2026-07-24T10-00-00Z").exists()
