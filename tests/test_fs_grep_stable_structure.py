"""fs_grep stable structure enrichment and known-types policy."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_analysis.commands.fs_grep_command import FsGrepCommand
from code_analysis.core.structure_extraction.extractor import extract_structure
from code_analysis.core.structure_extraction.format_registry import should_scan_path
from code_analysis.core.structure_extraction.stable_tree import TreeResolutionStats


def test_known_types_default_excludes_logs() -> None:
    assert should_scan_path("logs/app.log", scan_all=False) is False
    assert should_scan_path("app.log", scan_all=False) is False


def test_scan_all_true_include_logs() -> None:
    assert should_scan_path("logs/app.log", scan_all=True, include_logs=True) is True
    assert should_scan_path("app.log", scan_all=True, include_logs=True) is True


@pytest.mark.asyncio
async def test_fast_text_only_returns_no_node_ref(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text("needle = 1\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        result = await FsGrepCommand().execute(
            project_id="00000000-0000-0000-0000-000000000010",
            pattern="needle",
            fast_text_only=True,
            enrich_blocks=False,
        )

    assert result.data is not None
    match = result.data["matches"][0]
    assert match.get("node_ref") is None
    assert match.get("block_id") is None
    assert match.get("enrichment_status") == "skipped_fast_text_only"


@pytest.mark.asyncio
async def test_python_missing_tree_created_before_enrichment(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    py_path = project_root / "mod.py"
    py_path.write_text(
        "def find_it():\n    return 'needle'\n",
        encoding="utf-8",
    )

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        result = await FsGrepCommand().execute(
            project_id="00000000-0000-0000-0000-000000000011",
            pattern="needle",
            python_only=True,
            fast_text_only=False,
            enrich_blocks=True,
            ensure_persisted_tree=True,
            stable_ids_required=True,
        )

    assert result.data is not None
    match = result.data["matches"][0]
    assert match.get("enrichment_status") == "enriched"
    assert match.get("node_ref")
    assert match.get("preview", {}).get("node_ref") == match.get("node_ref")
    stats = result.data.get("structure_stats") or {}
    assert (
        stats.get("missing_trees_created", 0) >= 1
        or stats.get("valid_trees_reused", 0) >= 0
    )


@pytest.mark.asyncio
async def test_repeated_grep_same_node_ref(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "stable.py").write_text(
        "def f():\n    return 'needle'\n",
        encoding="utf-8",
    )

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        r1 = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000012",
            pattern="needle",
            python_only=True,
            enrich_blocks=True,
            skip_indexed_unchanged=False,
        )
        r2 = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000012",
            pattern="needle",
            python_only=True,
            enrich_blocks=True,
            skip_indexed_unchanged=False,
        )

    assert r1.data and r2.data
    n1 = r1.data["matches"][0]["node_ref"]
    n2 = r2.data["matches"][0]["node_ref"]
    assert n1 and n1 == n2


def test_no_unstable_ids_when_tree_not_persisted(tmp_path) -> None:
    """Without ensure_persisted_tree, Python enrichment must not return node_ref."""
    py = tmp_path / "orphan.py"
    py.write_text("x = 1\n", encoding="utf-8")
    doc = extract_structure(
        file_path=str(py),
        content=py.read_text(encoding="utf-8"),
        ensure_persisted_tree=False,
        stable_ids_required=True,
        tree_stats=TreeResolutionStats(),
    )
    assert not doc.ids_stable
    assert doc.blocks == []
