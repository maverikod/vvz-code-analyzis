"""
Tests for list_project_files filesystem-only listing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand
from code_analysis.commands.file_management.relative_path_list_pattern import (
    relative_path_matches_listing_pattern,
)


@pytest.fixture(autouse=True)
def _list_project_files_mock_db_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real DB in unit tests; default index has no file rows."""

    mock_db = MagicMock()
    mock_db.get_project_file_rows.return_value = []

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        """Return open."""
        return mock_db

    monkeypatch.setattr(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        _open,
    )
    # Route the domain get_project_file_rows call site (stage-2 layer collapse)
    # back to whatever db.get_project_file_rows mock the test installed, since
    # these bare MagicMock dbs do not model driver.select.
    monkeypatch.setattr(
        "code_analysis.commands.ast.list_files.get_project_file_rows",
        lambda driver, project_id, include_deleted=False: driver.get_project_file_rows(
            project_id, include_deleted=include_deleted
        ),
    )


@pytest.mark.asyncio
async def test_list_project_files_lists_file_on_disk(tmp_path) -> None:
    """Verify test list project files lists file on disk."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "src").mkdir()
    (proj / "src" / "app.py").write_text("x=1\n")

    pid = "00000000-0000-0000-0000-000000000001"

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    data = result.data
    assert data["total"] == 1
    assert data["files"][0]["relative_path"] == "src/app.py"
    assert data["files"][0].get("file_id") is None
    assert data["items"] == data["files"]
    assert data["has_more"] is False
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_list_project_files_fs_only_without_db_row(tmp_path) -> None:
    """Verify test list project files fs only without db row."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "only_fs.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-000000000002"

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    row = result.data["files"][0]
    assert row.get("file_id") is None
    assert row["relative_path"] == "only_fs.py"
    assert row["project_id"] == pid


@pytest.mark.asyncio
async def test_list_project_files_sets_file_id_from_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify test list project files sets file id from index."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "src").mkdir()
    (proj / "src" / "app.py").write_text("x=1\n")

    pid = "00000000-0000-0000-0000-0000000000aa"
    fid = "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee"

    mock_db = MagicMock()
    mock_db.get_project_file_rows.return_value = [
        {"id": fid, "relative_path": "src/app.py", "path": "src/app.py"},
    ]

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        """Return open."""
        return mock_db

    monkeypatch.setattr(
        ListProjectFilesMCPCommand,
        "_open_database_from_config",
        _open,
    )

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    row = result.data["files"][0]
    assert row["relative_path"] == "src/app.py"
    assert row["file_id"] == fid


@pytest.mark.asyncio
async def test_empty_project_lists_no_files(tmp_path) -> None:
    """Verify test empty project lists no files."""
    proj = tmp_path / "proj"
    proj.mkdir()

    pid = "00000000-0000-0000-0000-000000000003"

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=proj
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid)

    assert result.data is not None
    assert result.data["total"] == 0
    assert result.data["files"] == []


@pytest.mark.asyncio
async def test_default_skips_venv_tree(tmp_path) -> None:
    """Verify test default skips venv tree."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "a.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id="00000000-0000-0000-0000-000000000004")

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert rels == ["main.py"]
    assert not any(".venv" in r for r in rels)


@pytest.mark.asyncio
async def test_default_skips_cache_dir_show_hidden_lists_it(tmp_path) -> None:
    """Verify test default skips cache dir show hidden lists it."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("#\n")
    cache = root / ".pytest_cache" / "v" / "lastfailed"
    cache.parent.mkdir(parents=True)
    cache.write_text("{}", encoding="utf-8")

    pid = "00000000-0000-0000-0000-0000000000c1"

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        off = await cmd.execute(project_id=pid)
        on = await cmd.execute(project_id=pid, show_hidden=True)

    assert off.data is not None and on.data is not None
    off_rels = sorted(f["relative_path"] for f in off.data["files"])
    on_rels = sorted(f["relative_path"] for f in on.data["files"])
    assert off_rels == ["app.py"]
    assert ".pytest_cache/v/lastfailed" in on_rels
    assert "app.py" in on_rels


@pytest.mark.asyncio
async def test_show_venv_adds_only_allowlisted_record_files(tmp_path) -> None:
    """Verify test show venv adds only allowlisted record files."""
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

    with (
        patch.object(
            ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.project_fs_enumerate.load_venv_site_packages_index_allowlist_from_config",
            return_value=["mypkg"],
        ),
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
async def test_ignore_exceptions_under_venv_not_listed_by_default(tmp_path) -> None:
    """Broad ignore_exceptions under .venv must not flood listing (use diagnostic flag)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    vdir = root / ".venv"
    vdir.mkdir()
    (vdir / "forced.py").write_text("x = 1\n", encoding="utf-8")

    with (
        patch.object(
            ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
            return_value=[".venv/forced.py"],
        ),
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000099",
            show_venv=False,
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert "main.py" in rels
    assert ".venv/forced.py" not in rels


@pytest.mark.asyncio
async def test_include_venv_ignore_exceptions_lists_forced_venv_file(tmp_path) -> None:
    """Verify test include venv ignore exceptions lists forced venv file."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "main.py").write_text("#\n")
    vdir = root / ".venv"
    vdir.mkdir()
    (vdir / "forced.py").write_text("x = 1\n", encoding="utf-8")

    with (
        patch.object(
            ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
            return_value=[".venv/forced.py"],
        ),
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000098",
            show_venv=False,
            include_venv_ignore_exceptions=True,
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert "main.py" in rels
    assert ".venv/forced.py" in rels


@pytest.mark.asyncio
async def test_show_venv_empty_allowlist_adds_no_venv_files(tmp_path) -> None:
    """Verify test show venv empty allowlist adds no venv files."""
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

    with (
        patch.object(
            ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.project_fs_enumerate.load_venv_site_packages_index_allowlist_from_config",
            return_value=[],
        ),
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
    """Verify test pagination stable sort."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "c.py").write_text("#\n")
    (root / "a.py").write_text("#\n")
    (root / "b.py").write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
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
    """Verify test file pattern filter."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "keep.py").write_text("#\n")
    (root / "skip.txt").write_text("not py\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
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
    """Verify test lists markdown and python by default."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "notes.md").write_text("# doc\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id="00000000-0000-0000-0000-000000000010")

    assert result.data is not None
    rels = sorted(f["relative_path"] for f in result.data["files"])
    assert rels == ["a.py", "notes.md"]


@pytest.mark.asyncio
async def test_plan_directory_pattern_returns_steps_and_readme(tmp_path) -> None:
    """Verify test plan directory pattern returns steps and readme."""
    root = tmp_path / "proj"
    plan = root / "docs" / "plans" / "db_retry_worker_coordination_100_qwen"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")
    (plan / "step_01_exceptions_contract.md").write_text("#\n")
    (plan / "step_02_postgres.md").write_text("#\n")
    (plan / "audit_steps.py").write_text("x=1\n")

    pat = "docs/plans/db_retry_worker_coordination_100_qwen/*"
    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000011",
            file_pattern=pat,
        )

    assert result.data is not None
    rels = {f["relative_path"] for f in result.data["files"]}
    assert "docs/plans/db_retry_worker_coordination_100_qwen/README.md" in rels
    assert (
        "docs/plans/db_retry_worker_coordination_100_qwen/step_01_exceptions_contract.md"
        in rels
    )
    assert "docs/plans/db_retry_worker_coordination_100_qwen/audit_steps.py" in rels
    step_md = {r for r in rels if r.endswith(".md") and "step_" in r}
    assert len(step_md) >= 2


@pytest.mark.asyncio
async def test_python_only_restricts_to_py(tmp_path) -> None:
    """Verify test python only restricts to py."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "b.md").write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
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
    """Verify test pagination total count offset."""
    root = tmp_path / "proj"
    root.mkdir()
    for name in ("m1.md", "m2.md", "m3.md"):
        (root / name).write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
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

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000014",
            file_pattern="code_analysis/commands/*",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "code_analysis/commands/ast/x.py"


def test_relative_path_matches_directory_prefix_without_wildcards() -> None:
    """Verify test relative path matches directory prefix without wildcards."""
    assert relative_path_matches_listing_pattern(
        "docs/plans/foo/README.md", "docs/plans/foo"
    )
    assert relative_path_matches_listing_pattern(
        "docs/plans/foo/README.md", "docs/plans/foo/"
    )
    assert not relative_path_matches_listing_pattern(
        "docs/plans/foobar/x.md", "docs/plans/foo"
    )
    assert not relative_path_matches_listing_pattern(
        "docs/plans/foobar/x.md", "docs/plans/foo/"
    )
    assert relative_path_matches_listing_pattern("docs/plans/foo", "docs/plans/foo")


@pytest.mark.asyncio
async def test_plan_directory_literal_prefix_without_star(tmp_path) -> None:
    """Directory path without * should match all files under that prefix."""
    root = tmp_path / "proj"
    plan = root / "docs" / "plans" / "db_retry_worker_coordination_100_qwen"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")
    (plan / "step_01.md").write_text("#\n")

    prefix = "docs/plans/db_retry_worker_coordination_100_qwen"
    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000015",
            file_pattern=prefix,
        )

    assert result.data is not None
    rels = {f["relative_path"] for f in result.data["files"]}
    assert rels == {
        "docs/plans/db_retry_worker_coordination_100_qwen/README.md",
        "docs/plans/db_retry_worker_coordination_100_qwen/step_01.md",
    }


@pytest.mark.asyncio
async def test_plan_directory_literal_prefix_with_trailing_slash(tmp_path) -> None:
    """``file_pattern`` ending in ``/`` must behave like a directory prefix."""
    root = tmp_path / "proj"
    plan = root / "docs" / "plans" / "db_retry_worker_coordination_100_qwen"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")
    (plan / "step_01.md").write_text("#\n")

    prefix = "docs/plans/db_retry_worker_coordination_100_qwen/"
    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000015",
            file_pattern=prefix,
        )

    assert result.data is not None
    rels = {f["relative_path"] for f in result.data["files"]}
    assert rels == {
        "docs/plans/db_retry_worker_coordination_100_qwen/README.md",
        "docs/plans/db_retry_worker_coordination_100_qwen/step_01.md",
    }


@pytest.mark.asyncio
async def test_glob_param_alias(tmp_path) -> None:
    """Verify test glob param alias."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "b.txt").write_text("x\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000016",
            glob="*.py",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "a.py"


@pytest.mark.asyncio
async def test_file_pattern_wins_over_glob(tmp_path) -> None:
    """Verify test file pattern wins over glob."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "b.md").write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000017",
            file_pattern="*.py",
            glob="*.md",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "a.py"


@pytest.mark.asyncio
async def test_backslashes_in_pattern_normalized(tmp_path) -> None:
    """Verify test backslashes in pattern normalized."""
    root = tmp_path / "proj"
    sub = root / "pkg" / "mod"
    sub.mkdir(parents=True)
    (sub / "z.py").write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000018",
            file_pattern=r"pkg\mod\*.py",
        )

    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "pkg/mod/z.py"
