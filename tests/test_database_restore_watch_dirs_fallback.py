"""
Tests for the watch_dirs-table fallback in restore_database (bug b9b36e13).

``RestoreDatabaseFromConfigMCPCommand`` used to fail with ``NO_DIRS`` whenever
the config file had no ``code_analysis.dirs`` / ``code_analysis.worker.watch_dirs``
entries, even when the database already has registered watch directories that
could be used to rebuild the restore plan. The fix adds
``extract_restore_dirs_from_watch_dirs_table`` (sourced from
``list_watch_dir_path_pairs``) as a fallback, applied before the ``dry_run``
gate so a dry run previews the DB-sourced directories too. ``NO_DIRS`` is now
only returned when *both* sources (config and watch_dirs table) are empty.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.database_restore_mcp_commands import (
    RestoreDatabaseFromConfigMCPCommand,
)
from code_analysis.commands.database_restore_mcp_commands_helpers import (
    extract_restore_dirs_from_watch_dirs_table,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


class _FakeWatchDirsDB:
    """Minimal driver stub for ``list_watch_dir_path_pairs`` (``_fetchall`` path)."""

    def __init__(self, rows: list[dict]) -> None:
        """Initialize with canned watch_dir_paths join rows."""
        self._rows = rows

    def _fetchall(self, sql: str, params: tuple) -> list[dict]:
        """Return the canned rows regardless of the exact SQL text."""
        return self._rows

    def disconnect(self) -> None:
        """No-op disconnect to satisfy callers that always disconnect."""


def test_extract_restore_dirs_from_watch_dirs_table_dedupes(tmp_path: Path) -> None:
    """Dedup by absolute_path, preserve first-seen order, drop nonexistent dirs."""
    w1 = tmp_path / "w1"
    w2 = tmp_path / "w2"
    w1.mkdir()
    w2.mkdir()
    db = _FakeWatchDirsDB(
        [
            {"watch_dir_id": "wd1", "absolute_path": str(w1)},
            {"watch_dir_id": "wd2", "absolute_path": str(w2)},
            {"watch_dir_id": "wd3", "absolute_path": str(w1)},  # duplicate
        ]
    )

    result = extract_restore_dirs_from_watch_dirs_table(db)

    assert result == [str(w1), str(w2)]


def test_extract_restore_dirs_from_watch_dirs_table_empty_when_no_rows() -> None:
    """No registered watch dirs -> empty list."""
    db = _FakeWatchDirsDB([])
    assert extract_restore_dirs_from_watch_dirs_table(db) == []


@pytest.mark.asyncio
async def test_restore_database_dry_run_falls_back_to_watch_dirs_table(
    tmp_path: Path,
) -> None:
    """Empty config dirs + stubbed DB watch dirs -> plan.dirs populated, no NO_DIRS."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")

    cmd = RestoreDatabaseFromConfigMCPCommand()
    fallback_db = MagicMock()
    fallback_db.disconnect = MagicMock()

    watched_dirs = [str(tmp_path / "one"), str(tmp_path / "two")]

    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=cfg_path),
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=fallback_db
        ),
        patch.object(BaseMCPCommand, "_get_shared_storage", return_value=MagicMock()),
        patch(
            "code_analysis.commands.database_restore_mcp_commands."
            "extract_restore_dirs_from_watch_dirs_table",
            return_value=watched_dirs,
        ) as mock_fallback,
        patch(
            "code_analysis.commands.database_restore_mcp_commands.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.commands.database_restore_mcp_commands.get_driver_config",
            return_value={"type": "postgres"},
        ),
    ):
        result = await cmd.execute(config_file="config.json", dry_run=True)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    mock_fallback.assert_called_once_with(fallback_db)
    fallback_db.disconnect.assert_called_once()
    plan = result.data["plan"]
    assert plan["dirs"] == watched_dirs
    assert plan["dirs_source"] == "watch_dirs_table"


@pytest.mark.asyncio
async def test_restore_database_config_dirs_present_skips_db_fallback(
    tmp_path: Path,
) -> None:
    """Config already has dirs configured -> watch_dirs-table fallback is not touched."""
    configured_dir = tmp_path / "configured"
    configured_dir.mkdir()
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        '{"code_analysis": {"dirs": ["' + str(configured_dir) + '"]}}',
        encoding="utf-8",
    )

    cmd = RestoreDatabaseFromConfigMCPCommand()

    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=cfg_path),
        patch.object(BaseMCPCommand, "_get_shared_storage", return_value=MagicMock()),
        patch(
            "code_analysis.commands.database_restore_mcp_commands."
            "extract_restore_dirs_from_watch_dirs_table",
        ) as mock_fallback,
        patch(
            "code_analysis.commands.database_restore_mcp_commands.load_raw_config",
            return_value={},
        ),
        patch(
            "code_analysis.commands.database_restore_mcp_commands.get_driver_config",
            return_value={"type": "postgres"},
        ),
    ):
        result = await cmd.execute(config_file="config.json", dry_run=True)

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    mock_fallback.assert_not_called()
    plan = result.data["plan"]
    assert plan["dirs"] == [str(configured_dir)]
    assert plan["dirs_source"] == "config"


@pytest.mark.asyncio
async def test_restore_database_no_dirs_when_both_sources_empty(
    tmp_path: Path,
) -> None:
    """Config has no dirs AND the watch_dirs table has none -> NO_DIRS naming both."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")

    cmd = RestoreDatabaseFromConfigMCPCommand()
    fallback_db = MagicMock()
    fallback_db.disconnect = MagicMock()

    with (
        patch.object(BaseMCPCommand, "_resolve_config_path", return_value=cfg_path),
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=fallback_db
        ),
        patch(
            "code_analysis.commands.database_restore_mcp_commands."
            "extract_restore_dirs_from_watch_dirs_table",
            return_value=[],
        ),
    ):
        result = await cmd.execute(config_file="config.json", dry_run=True)

    assert isinstance(result, ErrorResult)
    assert result.code == "NO_DIRS"
    assert "watch_dirs table" in result.message
    assert "code_analysis.dirs" in result.message
    fallback_db.disconnect.assert_called_once()
