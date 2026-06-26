"""
Regression tests for filesystem listing commands: file_pattern / glob filters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.backup_mcp_commands.list_backup_files import (
    ListBackupFilesMCPCommand,
)
from code_analysis.commands.code_mapper_mcp_commands import ListLongFilesMCPCommand
from code_analysis.commands.file_management_mcp_commands.list_deleted_files import (
    ListDeletedFilesMCPCommand,
    _deleted_entry_rel_posix,
)
from code_analysis.commands.log_viewer_mcp_commands.list_worker_logs import (
    ListWorkerLogsMCPCommand,
)


@pytest.mark.asyncio
async def test_list_backup_files_filters_by_file_pattern(tmp_path) -> None:
    """Verify test list backup files filters by file pattern."""
    root = tmp_path / "proj"
    root.mkdir()
    mock_mgr = MagicMock()
    mock_mgr.list_files.return_value = [
        {"file_path": "src/keep.py"},
        {"file_path": "docs/skip.md"},
    ]
    mock_mgr.list_versions.return_value = [{"uuid": "u1", "timestamp": "t"}]
    mock_mgr._load_index.return_value = {"u1": {"command": "x", "related_files": ""}}

    mock_db = MagicMock()

    with (
        patch.object(
            ListBackupFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.backup_mcp_commands.list_backup_files.BackupManager",
            return_value=mock_mgr,
        ),
    ):
        cmd = ListBackupFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000001",
            file_pattern="src/*",
        )

    assert result.data is not None
    assert result.data["count"] == 1
    assert result.data["files"][0]["file_path"] == "src/keep.py"


@pytest.mark.asyncio
async def test_list_backup_files_glob_alias_and_prefix(tmp_path) -> None:
    """Verify test list backup files glob alias and prefix."""
    root = tmp_path / "proj"
    root.mkdir()
    mock_mgr = MagicMock()
    mock_mgr.list_files.return_value = [
        {"file_path": "plan/a.md"},
        {"file_path": "plan/sub/b.md"},
        {"file_path": "other/c.md"},
    ]
    mock_mgr.list_versions.return_value = [{"uuid": "u1"}]
    mock_mgr._load_index.return_value = {"u1": {}}

    with (
        patch.object(
            ListBackupFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.backup_mcp_commands.list_backup_files.BackupManager",
            return_value=mock_mgr,
        ),
    ):
        cmd = ListBackupFilesMCPCommand()
        r1 = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000002",
            glob="plan",
        )
        r2 = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000002",
            file_pattern="*.md",
            glob="plan",
        )

    assert r1.data["count"] == 2
    paths = {f["file_path"] for f in r1.data["files"]}
    assert paths == {"plan/a.md", "plan/sub/b.md"}

    assert r2.data["count"] == 3


@pytest.mark.asyncio
async def test_list_deleted_files_pattern_on_original_path(tmp_path) -> None:
    """Verify test list deleted files pattern on original path."""
    root = tmp_path / "proj"
    root.mkdir()
    rows = [
        {
            "id": 1,
            "path": str(root / "trash" / "x.py"),
            "original_path": "src/x.py",
            "version_dir": "v1",
            "updated_at": None,
        },
        {
            "id": 2,
            "path": str(root / "other"),
            "original_path": "lib/y.py",
            "version_dir": None,
            "updated_at": None,
        },
    ]
    mock_db = MagicMock()
    mock_db.get_deleted_files.return_value = rows
    mock_db.disconnect = MagicMock()

    with (
        patch.object(
            ListDeletedFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch.object(
            ListDeletedFilesMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
    ):
        cmd = ListDeletedFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000003",
            file_pattern="src/*",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["deleted_files"][0]["original_path"] == "src/x.py"


def test_deleted_entry_rel_posix_prefers_original_relative(tmp_path) -> None:
    """Verify test deleted entry rel posix prefers original relative."""
    root = tmp_path / "proj"
    root.mkdir()
    item = {"original_path": "a/b.py", "path": str(root / "elsewhere")}
    assert _deleted_entry_rel_posix(root, item) == "a/b.py"


@pytest.mark.asyncio
async def test_list_long_files_filters_after_query(tmp_path) -> None:
    """Verify test list long files filters after query."""
    root = tmp_path / "proj"
    root.mkdir()
    pid = "00000000-0000-0000-0000-000000000004"
    abs_py = (root / "pkg" / "long.py").resolve()
    abs_md = (root / "long.md").resolve()
    abs_py.parent.mkdir(parents=True)
    abs_py.write_text("#\n" * 500)
    abs_md.write_text("#\n" * 500)

    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()

    async def fake_execute() -> dict:
        """Return fake execute."""
        return {
            "files": [
                {"path": str(abs_py), "lines": 900},
                {"path": str(abs_md), "lines": 800},
            ],
            "count": 2,
            "max_lines": 400,
            "project_id": pid,
        }

    with (
        patch.object(
            ListLongFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch.object(
            ListLongFilesMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.code_mapper_mcp_commands.ListLongFilesCommand"
        ) as LC,
    ):
        inst = LC.return_value
        inst.execute = AsyncMock(side_effect=fake_execute)
        cmd = ListLongFilesMCPCommand()
        result = await cmd.execute(
            project_id=pid,
            max_lines=400,
            file_pattern="pkg/*.py",
        )

    assert result.data is not None
    assert result.data["count"] == 1
    assert result.data["files"][0]["path"] == str(abs_py)


@pytest.mark.asyncio
async def test_list_long_files_glob_alias(tmp_path) -> None:
    """Verify test list long files glob alias."""
    root = tmp_path / "proj"
    root.mkdir()
    pid = "00000000-0000-0000-0000-000000000005"
    p = (root / "a.py").resolve()
    p.write_text("#\n" * 500)
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()

    async def fake_execute() -> dict:
        """Return fake execute."""
        return {
            "files": [{"path": str(p), "lines": 500}],
            "count": 1,
            "max_lines": 400,
            "project_id": pid,
        }

    with (
        patch.object(
            ListLongFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch.object(
            ListLongFilesMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.code_mapper_mcp_commands.ListLongFilesCommand"
        ) as LC,
    ):
        LC.return_value.execute = AsyncMock(side_effect=fake_execute)
        cmd = ListLongFilesMCPCommand()
        result = await cmd.execute(project_id=pid, glob="*.py")

    assert result.data["count"] == 1


@pytest.mark.asyncio
async def test_list_worker_logs_file_pattern_on_absolute_path(tmp_path) -> None:
    """Verify test list worker logs file pattern on absolute path."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fw = log_dir / "file_watcher.log"
    fw.write_text("x\n")
    vz = log_dir / "vectorization_worker.log"
    vz.write_text("y\n")

    cmd = ListWorkerLogsMCPCommand()
    result = await cmd.execute(
        log_dirs=[str(log_dir)],
        worker_type="file_watcher",
        file_pattern="*file_watcher*",
    )

    assert result.data is not None
    paths = [x["path"] for x in result.data.get("log_files", [])]
    assert len(paths) >= 1
    assert all("file_watcher" in Path(p).name for p in paths)


@pytest.mark.asyncio
async def test_list_worker_logs_prefix_directory_on_absolute(tmp_path) -> None:
    """Literal pattern without wildcards: prefix on full absolute path."""
    d = tmp_path / "logs2"
    d.mkdir()
    p = d / "app.log"
    p.write_text("z\n")

    cmd = ListWorkerLogsMCPCommand()
    prefix = str(d).replace("\\", "/")
    result = await cmd.execute(
        log_dirs=[str(d)], worker_type="server", file_pattern=prefix
    )

    assert result.data is not None
    names = {Path(x["path"]).name for x in result.data.get("log_files", [])}
    assert "app.log" in names
