"""
Tests for project trash commands (list, permanently delete, clear).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from code_analysis.commands.trash_commands import (
    ClearTrashCommand,
    ListTrashedProjectsCommand,
    PermanentlyDeleteFromTrashCommand,
)


@pytest.fixture
def trash_dir(tmp_path):
    """Create a temporary trash directory."""
    d = tmp_path / "trash"
    d.mkdir()
    return str(d)


class TestListTrashedProjectsCommand:
    """Tests for ListTrashedProjectsCommand."""

    def test_empty_trash_returns_empty_list(self, trash_dir):
        """Empty trash dir returns success with empty items."""
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()
        assert result["success"] is True
        assert result["items"] == []
        assert result["count"] == 0
        assert result["trash_dir"] == str(Path(trash_dir).resolve())

    def test_list_parses_standard_folder_names(self, trash_dir):
        """Folders matching {name}_{YYYY-MM-DDThh-mm-ss}Z are parsed."""
        path = Path(trash_dir)
        (path / "MyProject_2025-01-29T14-30-00Z").mkdir()
        (path / "Other_2025-01-28T09-00-00Z").mkdir()
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()
        assert result["success"] is True
        assert result["count"] == 2
        items = {item["folder_name"]: item for item in result["items"]}
        assert items["MyProject_2025-01-29T14-30-00Z"]["original_name"] == "MyProject"
        assert (
            items["MyProject_2025-01-29T14-30-00Z"]["deleted_at"]
            == "2025-01-29T14-30-00Z"
        )
        assert items["Other_2025-01-28T09-00-00Z"]["original_name"] == "Other"
        assert (
            items["Other_2025-01-28T09-00-00Z"]["deleted_at"] == "2025-01-28T09-00-00Z"
        )

    def test_list_skips_non_directories(self, trash_dir):
        """Non-directory children are skipped."""
        path = Path(trash_dir)
        (path / "file.txt").write_text("x")
        (path / "Project_2025-01-29T12-00-00Z").mkdir()
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()
        assert result["success"] is True
        assert result["count"] == 1
        assert result["items"][0]["folder_name"] == "Project_2025-01-29T12-00-00Z"

    def test_list_non_matching_name_returns_folder_name_and_none_date(self, trash_dir):
        """Folders not matching pattern get original_name=folder_name, deleted_at=None."""
        path = Path(trash_dir)
        (path / "ManualBackup").mkdir()
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()
        assert result["success"] is True
        assert result["count"] == 1
        assert result["items"][0]["folder_name"] == "ManualBackup"
        assert result["items"][0]["original_name"] == "ManualBackup"
        assert result["items"][0]["deleted_at"] is None

    def test_list_nonexistent_trash_returns_empty(self, tmp_path):
        """Nonexistent trash dir returns success with empty items."""
        cmd = ListTrashedProjectsCommand(trash_dir=str(tmp_path / "nonexistent"))
        result = cmd.execute()
        assert result["success"] is True
        assert result["items"] == []
        assert result["count"] == 0


class TestPermanentlyDeleteFromTrashCommand:
    """Tests for PermanentlyDeleteFromTrashCommand."""

    def test_deletes_folder(self, trash_dir):
        """Permanently deletes the given folder under trash_dir."""
        path = Path(trash_dir)
        folder = path / "MyProject_2025-01-29T14-30-00Z"
        folder.mkdir()
        (folder / "file.txt").write_text("x")
        cmd = PermanentlyDeleteFromTrashCommand(
            trash_dir=trash_dir, trash_folder_name="MyProject_2025-01-29T14-30-00Z"
        )
        result = cmd.execute()
        assert result["success"] is True
        assert not folder.exists()

    def test_rejects_path_separators(self, trash_dir):
        """Rejects trash_folder_name containing path separators."""
        cmd = PermanentlyDeleteFromTrashCommand(
            trash_dir=trash_dir, trash_folder_name="sub/../evil"
        )
        result = cmd.execute()
        assert result["success"] is False
        assert result["error"] == "INVALID_PATH"

    def test_rejects_dot_dot(self, trash_dir):
        """Rejects trash_folder_name containing '..'."""
        cmd = PermanentlyDeleteFromTrashCommand(
            trash_dir=trash_dir, trash_folder_name=".."
        )
        result = cmd.execute()
        assert result["success"] is False
        assert (
            "path" in result["message"].lower() or "escape" in result["message"].lower()
        )

    def test_not_found_returns_error(self, trash_dir):
        """Nonexistent folder returns NOT_FOUND error."""
        cmd = PermanentlyDeleteFromTrashCommand(
            trash_dir=trash_dir, trash_folder_name="Nonexistent_2025-01-29T00-00-00Z"
        )
        result = cmd.execute()
        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"


class TestClearTrashCommand:
    """Tests for ClearTrashCommand."""

    def test_clear_removes_all_directories(self, trash_dir):
        """Clear removes all direct child directories."""
        path = Path(trash_dir)
        (path / "A_2025-01-29T10-00-00Z").mkdir()
        (path / "B_2025-01-29T11-00-00Z").mkdir()
        cmd = ClearTrashCommand(trash_dir=trash_dir, dry_run=False)
        result = cmd.execute()
        assert result["success"] is True
        assert result["removed_count"] == 2
        assert set(result["removed"]) == {
            "A_2025-01-29T10-00-00Z",
            "B_2025-01-29T11-00-00Z",
        }
        assert not (path / "A_2025-01-29T10-00-00Z").exists()
        assert not (path / "B_2025-01-29T11-00-00Z").exists()

    def test_clear_dry_run_does_not_remove(self, trash_dir):
        """Dry run lists what would be removed but does not delete."""
        path = Path(trash_dir)
        (path / "Only_2025-01-29T12-00-00Z").mkdir()
        cmd = ClearTrashCommand(trash_dir=trash_dir, dry_run=True)
        result = cmd.execute()
        assert result["success"] is True
        assert result["removed_count"] == 1
        assert result["dry_run"] is True
        assert (path / "Only_2025-01-29T12-00-00Z").exists()

    def test_clear_empty_returns_zero_removed(self, trash_dir):
        """Clear on empty trash returns removed_count 0."""
        cmd = ClearTrashCommand(trash_dir=trash_dir, dry_run=False)
        result = cmd.execute()
        assert result["success"] is True
        assert result["removed_count"] == 0
        assert result["removed"] == []

    def test_clear_skips_files(self, trash_dir):
        """Clear only removes directories; files are left (not in removed list)."""
        path = Path(trash_dir)
        (path / "Dir_2025-01-29T12-00-00Z").mkdir()
        (path / "readme.txt").write_text("x")
        cmd = ClearTrashCommand(trash_dir=trash_dir, dry_run=False)
        result = cmd.execute()
        assert result["success"] is True
        assert result["removed_count"] == 1
        assert (path / "readme.txt").exists()
