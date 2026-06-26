"""
Tests for DeleteUnwatchedProjectsCommand: success vs discovery, watch-dir classification.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.delete_unwatched_projects_command import (
    DeleteUnwatchedProjectsCommand,
)


def _write_projectid(project_dir: Path, pid: str) -> None:
    """Return write projectid."""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "projectid").write_text(
        json.dumps({"id": pid, "description": "t"}), encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_success_true_when_duplicate_ids_in_watch_dir(tmp_path: Path) -> None:
    """Duplicate discovery yields warnings but watched DB rows are kept, not misclassified."""
    watch = tmp_path / "watch"
    watch.mkdir()
    pid = str(uuid.uuid4())
    p1 = watch / "a"
    p2 = watch / "b"
    _write_projectid(p1, pid)
    _write_projectid(p2, pid)

    db = MagicMock()
    db.execute.return_value = [
        {"id": pid, "root_path": str(p1.resolve()), "name": "one"},
    ]

    cmd = DeleteUnwatchedProjectsCommand(
        database=db,
        watched_dirs=[str(watch.resolve())],
        dry_run=True,
        server_root_dir=None,
    )
    result = await cmd.execute()
    assert result["success"] is True
    assert result["discovery_warnings"]
    assert "Duplicate project_id" in result["discovery_warnings"][0]
    assert result.get("discovery_errors") in (None, [])
    kept = result["projects_kept"]
    assert len(kept) == 1
    assert kept[0]["reason"] == "under_watch_dir_project_root"


@pytest.mark.asyncio
async def test_invalid_sibling_projectid_skipped_discovery_ok(tmp_path: Path) -> None:
    """Invalid projectid under another immediate child does not break discovery or success."""
    watch = tmp_path / "watch"
    watch.mkdir()
    pid = str(uuid.uuid4())
    good = watch / "good"
    bad = watch / "bad"
    _write_projectid(good, pid)
    bad.mkdir()
    (bad / "projectid").write_text(json.dumps({"id": "not-a-uuid"}), encoding="utf-8")

    db = MagicMock()
    db.execute.return_value = [
        {"id": pid, "root_path": str(good.resolve()), "name": "g"},
    ]

    cmd = DeleteUnwatchedProjectsCommand(
        database=db,
        watched_dirs=[str(watch.resolve())],
        dry_run=True,
        server_root_dir=None,
    )
    result = await cmd.execute()
    assert result["success"] is True
    assert not result.get("discovery_errors")
    assert not result.get("discovery_warnings")
    assert result["projects_kept"][0]["reason"] == "discovered_in_watch_dirs"


@pytest.mark.asyncio
async def test_deletion_success_true_despite_discovery_warnings(
    tmp_path: Path,
) -> None:
    """success follows deletion errors only; discovery_warnings do not set success=False."""
    watch = tmp_path / "watch"
    watch.mkdir()
    pid_dup = str(uuid.uuid4())
    p1 = watch / "a"
    p2 = watch / "b"
    _write_projectid(p1, pid_dup)
    _write_projectid(p2, pid_dup)

    orphan_id = str(uuid.uuid4())
    db = MagicMock()
    db.execute.return_value = [
        {"id": pid_dup, "root_path": str(p1.resolve()), "name": "w"},
        {
            "id": orphan_id,
            "root_path": str(tmp_path / "gone" / "nope"),
            "name": "gone",
        },
    ]

    cmd = DeleteUnwatchedProjectsCommand(
        database=db,
        watched_dirs=[str(watch.resolve())],
        dry_run=False,
        server_root_dir=None,
    )
    with patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new_callable=AsyncMock,
        return_value=None,
    ) as clear_mock:
        result = await cmd.execute()

    assert result["success"] is True
    assert result["discovery_warnings"]
    clear_mock.assert_awaited_once()
    assert result["deleted_count"] == 1
    assert result["projects_deleted"][0]["project_id"] == orphan_id


@pytest.mark.asyncio
async def test_success_false_when_clear_raises(tmp_path: Path) -> None:
    """Verify test success false when clear raises."""
    watch = tmp_path / "watch"
    watch.mkdir()

    orphan_id = str(uuid.uuid4())
    db = MagicMock()
    db.execute.return_value = [
        {
            "id": orphan_id,
            "root_path": str(tmp_path / "missing" / "root"),
            "name": "gone",
        },
    ]

    cmd = DeleteUnwatchedProjectsCommand(
        database=db,
        watched_dirs=[str(watch.resolve())],
        dry_run=False,
        server_root_dir=None,
    )
    with patch(
        "code_analysis.commands.clear_project_data_impl._clear_project_data_impl",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db locked"),
    ):
        result = await cmd.execute()

    assert result["success"] is False
    assert result["errors"]


@pytest.mark.asyncio
async def test_disk_outside_watch_dirs_reason(tmp_path: Path) -> None:
    """Project on disk but not watch_dir/<subdir>/ keeps exists_on_disk_but_not_in_watch_dirs."""
    watch = tmp_path / "watch"
    watch.mkdir()
    outside = tmp_path / "outside" / "proj"
    pid = str(uuid.uuid4())
    _write_projectid(outside, pid)

    db = MagicMock()
    db.execute.return_value = [
        {"id": pid, "root_path": str(outside.resolve()), "name": "o"},
    ]

    cmd = DeleteUnwatchedProjectsCommand(
        database=db,
        watched_dirs=[str(watch.resolve())],
        dry_run=True,
        server_root_dir=None,
    )
    result = await cmd.execute()
    assert (
        result["projects_kept"][0]["reason"] == "exists_on_disk_but_not_in_watch_dirs"
    )
