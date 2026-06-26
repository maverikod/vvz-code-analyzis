"""Marked-tree PreviewNavigation wiring for universal_file_preview (G-004)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.universal_file_preview.budget import PreviewBudget
from code_analysis.commands.universal_file_preview.dispatcher import HandlerDispatcher
from code_analysis.commands.universal_file_preview.errors import PreviewError
from code_analysis.commands.universal_file_preview.marked_tree_loader import (
    make_preview_tree_loader,
    parse_focus_short_id,
)
from code_analysis.commands.universal_file_preview.marked_tree_navigation import (
    navigate_marked_tree,
    should_use_marked_tree_navigation,
)
from code_analysis.commands.universal_file_preview.navigation import navigate
from code_analysis.commands.universal_file_preview.navigation import navigate
from code_analysis.commands.universal_file_preview.response import build_envelope
from code_analysis.core.search_session.tree_representation import TreeValidityState


@pytest.fixture
def json_project(tmp_path: Path) -> tuple[Path, Path, str]:
    """Return json project."""
    root = tmp_path
    rel = "data/sample.json"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
    return root, path, rel


def test_make_preview_tree_loader_calls_tree_lifecycle(
    json_project: tuple[Path, Path, str],
) -> None:
    """Verify test make preview tree loader calls tree lifecycle."""
    root, path, rel = json_project
    loader = make_preview_tree_loader(
        project_root=root,
        rel_file_path=rel,
        preview_abs_path=path,
        bound_session_id=None,
    )
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path"
    ) as from_path:
        from_path.return_value = (MagicMock(), TreeValidityState.reused)
        tree = loader(path, None)
    from_path.assert_called_once_with(project_root=root, file_path=rel)
    assert tree.nodes
    assert all(isinstance(n.short_id, int) for n in tree.nodes)


def test_parse_focus_short_id_root_and_explicit(
    json_project: tuple[Path, Path, str],
) -> None:
    """Verify test parse focus short id root and explicit."""
    root, path, rel = json_project
    loader = make_preview_tree_loader(
        project_root=root,
        rel_file_path=rel,
        preview_abs_path=path,
        bound_session_id=None,
    )
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        nodes = loader(path, None).nodes
    root_id = parse_focus_short_id(None, nodes)
    assert isinstance(root_id, int)
    assert root_id >= 1
    key_node = next(n for n in nodes if n.attributes.get("json_pointer") == "/a")
    assert parse_focus_short_id(str(key_node.short_id), nodes) == key_node.short_id


def test_navigate_marked_tree_returns_short_id_int_refs(
    json_project: tuple[Path, Path, str],
) -> None:
    """Verify test navigate marked tree returns short id int refs."""
    root, path, rel = json_project
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=0
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    envelope = build_envelope(result, None, "none")
    assert isinstance(envelope["focus"]["node_ref"], int)
    assert envelope["focus"]["node_ref"] >= 1
    assert envelope["total_blocks"] == 2
    assert envelope["blocks"]
    for block in envelope["blocks"]:
        assert isinstance(block["node_ref"], int)


def test_navigation_branches_to_marked_tree_for_json(
    json_project: tuple[Path, Path, str],
) -> None:
    """Verify test navigation branches to marked tree for json."""
    root, path, rel = json_project
    handler = HandlerDispatcher().dispatch(rel)
    assert handler is not None and not isinstance(handler, PreviewError)
    budget = PreviewBudget(
        preview_lines=5, value_preview_len=80, full_text_max_lines=200
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
        "project_id": "test-proj",
    }
    assert should_use_marked_tree_navigation(handler, params)
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.recreated),
    ):
        result = navigate(handler, params, budget)
    assert not isinstance(result, PreviewError)
    assert result.short_id_refs is True


def test_should_use_marked_tree_true_for_jsonl(tmp_path: Path) -> None:
    """Verify test should use marked tree true for jsonl."""
    path = tmp_path / "lines.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    handler = HandlerDispatcher().dispatch("lines.jsonl")
    assert handler is not None and not isinstance(handler, PreviewError)
    params = {
        "project_root": tmp_path,
        "rel_file_path": "lines.jsonl",
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
    }
    assert should_use_marked_tree_navigation(handler, params) is True


def test_navigate_marked_tree_python_root_lists_top_level_blocks(
    tmp_path: Path,
) -> None:
    """Root view on .py must list module-level nodes, not inner expr children."""
    root = tmp_path
    rel = "pkg/mod.py"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '"""Module doc."""\n\nimport os\n\n\nclass Widget:\n    pass\n',
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=80, full_text_max_lines=200
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    assert result.total_blocks >= 3
    texts = " ".join((b.text or "") for b in result.selected_blocks)
    assert "Module doc" in texts or "import os" in texts
    assert "class Widget" in texts


def test_invalid_json_skips_marked_tree_uses_plain_text_fallback(
    tmp_path: Path,
) -> None:
    """Broken JSON must not enter marked-tree navigation; legacy handler returns raw text."""
    root = tmp_path
    rel = "broken.json"
    path = root / rel
    broken = '{"key": "value", broken'
    path.write_text(broken, encoding="utf-8")
    handler = HandlerDispatcher().dispatch(rel)
    assert handler is not None and not isinstance(handler, PreviewError)
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
        "project_id": "test-proj",
    }
    assert should_use_marked_tree_navigation(handler, params) is False
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=200
    )
    result = navigate(handler, params, budget)
    assert not isinstance(result, PreviewError)
    assert result.focus_node.is_invalid is True
    assert broken in (result.focus_node.attributes.get("text") or "")
    assert result.short_id_refs is True
    assert result.total_blocks >= 1
    assert result.selected_blocks
    assert all(
        isinstance(b.node_ref, str) and b.node_ref.isdigit()
        for b in result.selected_blocks
    )


def test_invalid_python_marked_tree_returns_plain_text_fallback(
    tmp_path: Path,
) -> None:
    """Broken Python uses marked-tree entry but surfaces raw source on parse failure."""
    root = tmp_path
    rel = "broken.py"
    path = root / rel
    path.write_text("def f(\n", encoding="utf-8")
    handler = HandlerDispatcher().dispatch(rel)
    assert handler is not None and not isinstance(handler, PreviewError)
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
        "project_id": "test-proj",
    }
    assert should_use_marked_tree_navigation(handler, params) is True
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=200
    )
    result = navigate(handler, params, budget)
    assert not isinstance(result, PreviewError)
    assert result.focus_node.is_invalid is True
    assert "def f(" in (result.focus_node.attributes.get("text") or "")
    assert result.short_id_refs is True
    assert result.total_blocks >= 1


def test_navigate_degraded_large_json_respects_text_threshold(
    tmp_path: Path,
) -> None:
    """Broken JSON above full_text_max_lines: text tree, preview_lines cap, no full_text."""
    root = tmp_path
    rel = "broken.json"
    path = root / rel
    lines = ['{"bad": ' + str(i) + "}" for i in range(30)]
    path.write_text("\n\n".join(lines), encoding="utf-8")
    handler = HandlerDispatcher().dispatch(rel)
    assert handler is not None and not isinstance(handler, PreviewError)
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    budget = PreviewBudget(
        preview_lines=3,
        value_preview_len=80,
        full_text_max_lines=10,
    )
    result = navigate(
        handler,
        params,
        budget,
    )
    assert not isinstance(result, PreviewError)
    assert result.focus_node.is_invalid is True
    assert result.focus_node.attributes.get("full_text") is not True
    assert result.total_blocks == 30
    assert len(result.selected_blocks) == 3


def test_text_handler_parse_builds_paragraph_line_hierarchy() -> None:
    """Verify test text handler parse builds paragraph line hierarchy."""
    from code_analysis.tree.handlers.text_handler import TextHandler

    handler = TextHandler()
    nodes = handler.parse_content(
        Path("note.txt"),
        "Alpha one\nAlpha two\n\nBeta only\n",
    )
    by_kind = [n for n in nodes if n.kind == "paragraph"]
    assert len(by_kind) == 2
    first_para = next(n for n in nodes if n.content == "Alpha one")
    assert first_para.kind == "paragraph"
    assert first_para.parent_short_id is None
    assert first_para.attributes["start_line"] == 1
    assert first_para.attributes["end_line"] == 2
    second_line = next(n for n in nodes if n.content == "Alpha two")
    assert second_line.kind == "line"
    assert second_line.parent_short_id == first_para.short_id


def test_navigate_marked_tree_small_txt_returns_full_tree_and_annotated_focus(
    tmp_path: Path,
) -> None:
    """Verify test navigate marked tree small txt returns full tree and annotated focus."""
    root = tmp_path
    rel = "notes/readme.txt"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "First paragraph line.\nStill first.\n\nSecond paragraph.\n",
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=2,
        value_preview_len=80,
        full_text_max_lines=50,
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    envelope = build_envelope(result, None, "none")
    assert envelope["focus"]["attributes"].get("full_text") is True
    assert "First paragraph line." in envelope["focus"]["text"]
    assert envelope["total_blocks"] == 3
    assert len(envelope["blocks"]) == 3
    kinds = {b["summary"]["type"] for b in envelope["blocks"]}
    assert kinds == {"paragraph", "line"}
    for block in envelope["blocks"]:
        assert isinstance(block["node_ref"], int)


def test_navigate_marked_tree_large_txt_respects_preview_lines_cap(
    tmp_path: Path,
) -> None:
    """Verify test navigate marked tree large txt respects preview lines cap."""
    root = tmp_path
    rel = "notes/long.txt"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n\n".join(f"Line {i}" for i in range(30)) + "\n", encoding="utf-8"
    )
    budget = PreviewBudget(
        preview_lines=3,
        value_preview_len=80,
        full_text_max_lines=10,
    )
    params = {
        "project_root": root,
        "rel_file_path": rel,
        "file_path": str(path),
        "node_ref": None,
        "selector": None,
        "session_id": None,
    }
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(params, budget)
    assert not isinstance(result, PreviewError)
    assert result.total_blocks == 30
    assert len(result.selected_blocks) == 3
    assert result.focus_node.attributes.get("full_text") is not True
