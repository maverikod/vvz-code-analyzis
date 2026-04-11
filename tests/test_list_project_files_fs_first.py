"""
Tests for list_project_files filesystem-first listing and DB enrichment.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand
from code_analysis.core.database_client.objects.file import File


@pytest.mark.asyncio
async def test_list_project_files_enriches_when_db_row_matches(tmp_path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "src").mkdir()
    (proj / "src" / "app.py").write_text("x=1\n")

    pid = "00000000-0000-0000-0000-000000000001"
    db_file = File(
        id=42,
        project_id=pid,
        path=str((proj / "src" / "app.py").resolve()),
        relative_path="src/app.py",
        deleted=False,
    )

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = [db_file]
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    data = result.data
    assert data["total"] == 1
    assert data["files"][0].get("id") == 42


@pytest.mark.asyncio
async def test_list_project_files_fs_only_without_db_row(tmp_path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "only_fs.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-000000000002"
    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    row = result.data["files"][0]
    assert row.get("id") is None
    assert row["relative_path"] == "only_fs.py"
    assert row["project_id"] == pid


@pytest.mark.asyncio
async def test_db_row_without_fs_file_is_omitted(tmp_path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()

    pid = "00000000-0000-0000-0000-000000000003"
    db_file = File(
        id=99,
        project_id=pid,
        path=str((proj / "missing.py").resolve()),
        relative_path="missing.py",
        deleted=False,
    )
    mock_db = MagicMock()
    mock_db.get_project_files.return_value = [db_file]
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    assert result.data["total"] == 0
    assert result.data["files"] == []


@pytest.mark.asyncio
async def test_default_skips_venv_tree(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "a.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("#\n")

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id="00000000-0000-0000-0000-000000000004")

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert rels == ["main.py"]
    assert not any(".venv" in r for r in rels)


@pytest.mark.asyncio
async def test_show_venv_adds_only_allowlisted_record_files(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pkg_dir = sp / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "mod.py").write_text("x = 1\n", encoding="utf-8")
    dist = sp / "mypkg-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: mypkg\nVersion: 1.0\n")
    (dist / "RECORD").write_text("mypkg/mod.py,sha256=abc,12\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch(
        "code_analysis.commands.ast.list_files.load_venv_site_packages_index_allowlist_from_config",
        return_value=["mypkg"],
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000005",
            show_venv=True,
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert "main.py" in rels
    assert any(r.endswith("mypkg/mod.py") for r in rels)
    assert sum(1 for r in rels if "site-packages" in r) == 1


@pytest.mark.asyncio
async def test_show_venv_empty_allowlist_adds_no_venv_files(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pkg_dir = sp / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "mod.py").write_text("x = 1\n", encoding="utf-8")
    dist = sp / "mypkg-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: mypkg\nVersion: 1.0\n")
    (dist / "RECORD").write_text("mypkg/mod.py,sha256=abc,12\n", encoding="utf-8")

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ), patch(
        "code_analysis.commands.ast.list_files.load_venv_site_packages_index_allowlist_from_config",
        return_value=[],
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000006",
            show_venv=True,
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert rels == ["main.py"]


@pytest.mark.asyncio
async def test_pagination_stable_sort(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "c.py").write_text("#\n")
    (root / "a.py").write_text("#\n")
    (root / "b.py").write_text("#\n")

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000007",
            limit=1,
            offset=1,
        )

    assert result.data is not None
    assert result.data["total"] == 3
    assert len(result.data["files"]) == 1
    assert result.data["files"][0]["relative_path"] == "b.py"


@pytest.mark.asyncio
async def test_file_pattern_filter(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "keep.py").write_text("#\n")
    (root / "skip.txt").write_text("not py\n")  # not collected (py only)

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000008",
            file_pattern="k*.py",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "keep.py"
