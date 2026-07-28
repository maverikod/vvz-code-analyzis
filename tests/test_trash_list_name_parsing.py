"""
Tests for trash folder name parsing with the optional unique-suffix group
(recovered from casmgr:1.6.87 image, built from an uncommitted tree).

``ensure_unique_trash_path()`` appends ``_1``, ``_2``, ... to a trash folder
name when the timestamped name collides with an existing one. Before this
fix, ``_TRASH_FOLDER_PATTERN`` had no optional suffix group, so a
disambiguated folder name failed to match at all and
``list_trashed_projects`` fell back to reporting the whole folder name
(including the ``_YYYY-MM-DDThh-mm-ssZ_N`` tail) as ``original_name`` with
``deleted_at=None``, instead of the real project name and timestamp.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.commands.trash_commands import (
    ListTrashedProjectsCommand,
    _parse_trash_folder_name,
)


@pytest.fixture
def trash_dir(tmp_path: Path) -> str:
    """Create a temporary trash directory."""
    d = tmp_path / "trash"
    d.mkdir()
    return str(d)


class TestParseTrashFolderNameUniqueSuffix:
    """_parse_trash_folder_name: optional ``_N`` unique-disambiguation suffix."""

    def test_no_suffix_still_parses_as_before(self) -> None:
        """Plain timestamped names (no collision) are unaffected."""
        original, deleted_at = _parse_trash_folder_name(
            "MyProject_2025-01-29T14-30-00Z"
        )
        assert original == "MyProject"
        assert deleted_at == "2025-01-29T14-30-00Z"

    def test_single_digit_suffix_parses_original_name(self) -> None:
        """A '_1' disambiguation suffix no longer breaks the match."""
        original, deleted_at = _parse_trash_folder_name(
            "MyProject_2025-01-29T14-30-00Z_1"
        )
        assert original == "MyProject"
        assert deleted_at == "2025-01-29T14-30-00Z"

    def test_multi_digit_suffix_parses_original_name(self) -> None:
        """A multi-digit suffix (many collisions) is also accepted."""
        original, deleted_at = _parse_trash_folder_name(
            "MyProject_2025-01-29T14-30-00Z_23"
        )
        assert original == "MyProject"
        assert deleted_at == "2025-01-29T14-30-00Z"

    def test_non_numeric_trailing_segment_is_not_treated_as_suffix(self) -> None:
        """A trailing non-numeric segment does not match the optional group,
        so the whole name falls back to the no-match branch (unchanged
        behavior for genuinely unrecognized folder names)."""
        original, deleted_at = _parse_trash_folder_name(
            "MyProject_2025-01-29T14-30-00Z_final"
        )
        assert original == "MyProject_2025-01-29T14-30-00Z_final"
        assert deleted_at is None


class TestListTrashedProjectsCommandUniqueSuffix:
    """End-to-end: list_trashed_projects on disambiguated trash folders."""

    def test_list_preserves_original_name_for_suffixed_folder(
        self, trash_dir: str
    ) -> None:
        """A '_1' suffixed folder still reports the real original_name/deleted_at."""
        path = Path(trash_dir)
        (path / "MyProject_2025-01-29T14-30-00Z").mkdir()
        (path / "MyProject_2025-01-29T14-30-00Z_1").mkdir()
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()

        assert result["success"] is True
        assert result["count"] == 2
        items = {item["folder_name"]: item for item in result["items"]}
        assert items["MyProject_2025-01-29T14-30-00Z"]["original_name"] == "MyProject"
        assert (
            items["MyProject_2025-01-29T14-30-00Z_1"]["original_name"] == "MyProject"
        )
        assert (
            items["MyProject_2025-01-29T14-30-00Z_1"]["deleted_at"]
            == "2025-01-29T14-30-00Z"
        )

    def test_list_multiple_collisions_all_resolve_same_original_name(
        self, trash_dir: str
    ) -> None:
        """Repeated collisions (_1, _2, ...) all resolve back to the same project name."""
        path = Path(trash_dir)
        for suffix in ("", "_1", "_2"):
            (path / f"Dup_2025-02-01T00-00-00Z{suffix}").mkdir()
        cmd = ListTrashedProjectsCommand(trash_dir=trash_dir)
        result = cmd.execute()

        assert result["success"] is True
        assert result["count"] == 3
        for item in result["items"]:
            assert item["original_name"] == "Dup"
            assert item["deleted_at"] == "2025-02-01T00-00-00Z"
