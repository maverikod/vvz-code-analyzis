from __future__ import annotations

from pathlib import Path

from code_analysis.commands.grep_block_resolver import GrepBlockResolver
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree, remove_tree


def test_python_sidecar_lookup_smallest_span(tmp_path: Path) -> None:
    py_path = tmp_path / "sample.py"
    py_path.write_text(
        "class Outer:\n    def hello(self):\n        return 'needle'\n",
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(py_path))
    remove_tree(tree.tree_id)

    resolver = GrepBlockResolver()
    block_id, block_type = resolver.resolve(py_path, 2)
    assert block_id is not None
    assert block_type == "FunctionDef"

    inner_id, inner_type = resolver.resolve(py_path, 3)
    assert inner_id is not None
    assert inner_type in {"Return", "SimpleStatementLine", "SimpleString"}


def test_python_without_sidecar_returns_null(tmp_path: Path) -> None:
    py_path = tmp_path / "bare.py"
    py_path.write_text("x = 1\n", encoding="utf-8")
    resolver = GrepBlockResolver()
    block_id, block_type = resolver.resolve(py_path, 1)
    assert block_id is None
    assert block_type is None


def test_json_line_map_nearest_node(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    json_path.write_text(
        '{\n  "outer": {\n    "inner": "needle"\n  }\n}\n',
        encoding="utf-8",
    )
    resolver = GrepBlockResolver()
    block_id, block_type = resolver.resolve(json_path, 4)
    assert block_id is not None
    assert block_type in {"object", "string"}


def test_markdown_token_lookup(tmp_path: Path) -> None:
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nneedle paragraph\n", encoding="utf-8")
    resolver = GrepBlockResolver()
    block_id, block_type = resolver.resolve(md_path, 3)
    assert block_id is not None
    assert block_type is not None
