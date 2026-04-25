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
async def test_ignore_exceptions_paths_listed_without_show_venv(tmp_path) -> None:
    """ignore_exceptions must appear in listing (parity with watcher / indexing)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    vdir = root / ".venv"
    vdir.mkdir()
    (vdir / "forced.py").write_text("x = 1\n", encoding="utf-8")

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
        "code_analysis.commands.ast.list_files.load_ignore_exceptions_from_config",
        return_value=[".venv/forced.py"],
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000099",
            show_venv=False,
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert "main.py" in rels
    assert ".venv/forced.py" in rels


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
    (root / "skip.txt").write_text("not py\n")

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


@pytest.mark.asyncio
async def test_lists_markdown_and_python_by_default(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "notes.md").write_text("# doc\n")

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
        result = await cmd.execute(project_id="00000000-0000-0000-0000-000000000010")

    assert result.data is not None
    rels = sorted(f["relative_path"] for f in result.data["files"])
    assert rels == ["a.py", "notes.md"]


@pytest.mark.asyncio
async def test_plan_directory_pattern_returns_steps_and_readme(tmp_path) -> None:
    root = tmp_path / "proj"
    plan = root / "docs" / "plans" / "db_retry_worker_coordination_100_qwen"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")
    (plan / "step_01_exceptions_contract.md").write_text("#\n")
    (plan / "step_02_postgres.md").write_text("#\n")
    (plan / "audit_steps.py").write_text("x=1\n")

    mock_db = MagicMock()
    mock_db.get_project_files.return_value = []
    mock_db.disconnect = MagicMock()

    pat = "docs/plans/db_retry_worker_coordination_100_qwen/*"
    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ), patch.object(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000011",
            file_pattern=pat,
        )

    assert result.data is not None
    rels = {f["relative_path"] for f in result.data["files"]}
    assert "docs/plans/db_retry_worker_coordination_100_qwen/README.md" in rels
    assert "docs/plans/db_retry_worker_coordination_100_qwen/step_01_exceptions_contract.md" in rels
    assert "docs/plans/db_retry_worker_coordination_100_qwen/audit_steps.py" in rels
    step_md = {r for r in rels if r.endswith(".md") and "step_" in r}
    assert len(step_md) >= 2


@pytest.mark.asyncio
async def test_python_only_restricts_to_py(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "b.md").write_text("#\n")

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
            project_id="00000000-0000-0000-0000-000000000012",
            python_only=True,
        )

    assert result.data is not None
    assert [f["relative_path"] for f in result.data["files"]] == ["a.py"]


@pytest.mark.asyncio
async def test_pagination_total_count_offset(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for name in ("m1.md", "m2.md", "m3.md"):
        (root / name).write_text("#\n")

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
            project_id="00000000-0000-0000-0000-000000000013",
            file_pattern="*.md",
            limit=1,
            offset=1,
        )

    assert result.data is not None
    assert result.data["total"] == 3
    assert result.data["count"] == 1
    assert result.data["offset"] == 1
    assert result.data["files"][0]["relative_path"] == "m2.md"


@pytest.mark.asyncio
async def test_nested_commands_pattern_fnmatch(tmp_path) -> None:
    """code_analysis/commands/* must include nested modules (POSIX fnmatch * matches /)."""
    root = tmp_path / "proj"
    deep = root / "code_analysis" / "commands" / "ast"
    deep.mkdir(parents=True)
    (deep / "x.py").write_text("#\n")

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
            project_id="00000000-0000-0000-0000-000000000014",
            file_pattern="code_analysis/commands/*",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "code_analysis/commands/ast/x.py"
