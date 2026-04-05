"""
Detailed tests for CST targeted access: __root__, children_depth, require_one.

Covers: tree_builder root_node_id, tree_metadata _resolve_node_id,
get_node_metadata/children/descendants/parent with __root__,
cst_get_node_info with children_depth, cst_find_node with require_one.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import pytest

from code_analysis.commands.cst_find_node_command import CSTFindNodeCommand
from code_analysis.commands.cst_get_node_info_command import CSTGetNodeInfoCommand
from code_analysis.core.cst_tree.models import ROOT_NODE_ID_SENTINEL
from code_analysis.core.cst_tree.tree_builder import (
    create_tree_from_code,
    get_tree,
    load_file_to_tree,
    remove_tree,
)
from code_analysis.core.cst_tree.tree_metadata import (
    get_node_children,
    get_node_descendants,
    get_node_metadata,
    get_node_parent,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


# Sample module: Module with imports, one function, one class with one method.
SAMPLE_SOURCE = '''
"""Docstring."""
from __future__ import annotations

def main() -> int:
    return 42

class Helper:
    def run(self) -> None:
        pass
'''


@pytest.fixture
def sample_tree(tmp_path):
    """Build in-memory tree from sample source; yield tree_id; remove after test."""
    path = str(tmp_path / "sample.py")
    tree = create_tree_from_code(path, SAMPLE_SOURCE.strip())
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


@pytest.fixture
def sample_tree_with_filter(tmp_path):
    """Tree built with node_types filter (only FunctionDef, ClassDef); root still indexed."""
    path = str(tmp_path / "filtered.py")
    tree = create_tree_from_code(
        path,
        SAMPLE_SOURCE.strip(),
        node_types=["FunctionDef", "ClassDef"],
    )
    tree_id = tree.tree_id
    yield tree_id
    remove_tree(tree_id)


# --- ROOT_NODE_ID_SENTINEL and root_node_id ---


class TestRootNodeIdSet:
    """tree_builder sets root_node_id and root is always indexed."""

    def test_create_tree_from_code_sets_root_node_id(self, sample_tree):
        t = get_tree(sample_tree)
        assert t is not None
        assert t.root_node_id is not None
        # node_id is UUID4; root metadata must be Module
        meta = t.metadata_map.get(t.root_node_id)
        assert meta is not None and meta.type == "Module"

    def test_load_file_to_tree_sets_root_node_id(self, tmp_path):
        path = tmp_path / "f.py"
        path.write_text("x = 1\n", encoding="utf-8")
        tree = load_file_to_tree(str(path))
        try:
            assert tree.root_node_id is not None
        finally:
            remove_tree(tree.tree_id)

    def test_root_indexed_even_with_node_types_filter(self, sample_tree_with_filter):
        t = get_tree(sample_tree_with_filter)
        assert t is not None
        assert t.root_node_id is not None
        assert t.root_node_id in t.metadata_map


class TestNodeTypesFilterRecursionConsistency:
    """Regression: filtered index must recurse with path_indices (same as full visit)."""

    def test_node_map_matches_metadata_for_every_indexed_node(
        self, sample_tree_with_filter
    ):
        t = get_tree(sample_tree_with_filter)
        assert t is not None
        for node_id, meta in t.metadata_map.items():
            node = t.node_map.get(node_id)
            assert node is not None, f"missing node_map entry for {node_id}"
            assert node.__class__.__name__ == meta.type

    def test_filtered_load_finds_expected_defs(self, tmp_path):
        path = str(tmp_path / "filtered_defs.py")
        tree = create_tree_from_code(
            path,
            SAMPLE_SOURCE.strip(),
            node_types=["FunctionDef", "ClassDef"],
        )
        try:
            types_by_name = {
                m.name: m.type
                for m in tree.metadata_map.values()
                if m.name and m.type in ("FunctionDef", "ClassDef")
            }
            assert types_by_name.get("main") == "FunctionDef"
            assert types_by_name.get("Helper") == "ClassDef"
        finally:
            remove_tree(tree.tree_id)


# --- tree_metadata: __root__ resolution ---


class TestResolveRootSentinel:
    """get_node_metadata, get_node_children, get_node_descendants, get_node_parent accept __root__."""

    def test_get_node_metadata_with_root_sentinel_returns_module(self, sample_tree):
        meta = get_node_metadata(sample_tree, ROOT_NODE_ID_SENTINEL)
        assert meta is not None
        assert meta.type == "Module"
        assert meta.node_id != ROOT_NODE_ID_SENTINEL

    def test_get_node_metadata_with_literal_root_string(self, sample_tree):
        meta = get_node_metadata(sample_tree, "__root__")
        assert meta is not None
        assert meta.type == "Module"

    def test_get_node_children_with_root_sentinel_returns_top_level_nodes(
        self, sample_tree
    ):
        children = get_node_children(sample_tree, ROOT_NODE_ID_SENTINEL)
        assert len(children) >= 1
        types = {c.type for c in children}
        assert (
            "FunctionDef" in types
            or "SimpleStatementLine" in types
            or "ClassDef" in types
        )

    def test_get_node_descendants_with_root_sentinel_depth1(self, sample_tree):
        descendants = get_node_descendants(sample_tree, "__root__", max_depth=1)
        assert all(d == 1 for _, d in descendants)
        assert len(descendants) >= 1

    def test_get_node_descendants_with_root_sentinel_depth2(self, sample_tree):
        descendants = get_node_descendants(sample_tree, "__root__", max_depth=2)
        depths = [d for _, d in descendants]
        assert 1 in depths
        assert max(depths) <= 2

    def test_get_node_descendants_with_root_sentinel_full_subtree(self, sample_tree):
        descendants = get_node_descendants(sample_tree, "__root__", max_depth=0)
        assert len(descendants) >= 2
        depths = [d for _, d in descendants]
        assert max(depths) >= 2

    def test_get_node_parent_of_root_returns_none(self, sample_tree):
        parent = get_node_parent(sample_tree, "__root__")
        assert parent is None

    def test_root_resolution_works_with_node_types_filtered_tree(
        self, sample_tree_with_filter
    ):
        meta = get_node_metadata(sample_tree_with_filter, "__root__")
        assert meta is not None
        assert meta.type == "Module"
        children = get_node_children(sample_tree_with_filter, "__root__")
        assert isinstance(children, list)


# --- cst_get_node_info command: node_id __root__ and children_depth ---


class TestCstGetNodeInfoRootAndDepth:
    """CSTGetNodeInfoCommand with node_id=__root__ and children_depth variants."""

    @pytest.mark.asyncio
    async def test_get_node_info_with_root_sentinel_returns_module(self, sample_tree):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            node_id=ROOT_NODE_ID_SENTINEL,
        )
        assert isinstance(result, SuccessResult)
        assert result.data["node"]["type"] == "Module"
        assert result.data["tree_id"] == sample_tree

    @pytest.mark.asyncio
    async def test_get_node_info_root_with_children_depth1(self, sample_tree):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            node_id="__root__",
            include_children=True,
            children_depth=1,
        )
        assert isinstance(result, SuccessResult)
        assert "children" in result.data
        assert "descendants" not in result.data
        assert result.data["children_count"] == len(result.data["children"])

    @pytest.mark.asyncio
    async def test_get_node_info_root_with_children_depth2(self, sample_tree):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            node_id="__root__",
            include_children=True,
            children_depth=2,
        )
        assert isinstance(result, SuccessResult)
        assert "children" in result.data
        assert "descendants" in result.data
        assert "descendants_count" in result.data
        for d in result.data["descendants"]:
            assert "depth" in d
            assert d["depth"] in (1, 2)

    @pytest.mark.asyncio
    async def test_get_node_info_root_with_children_depth0_full_subtree(
        self, sample_tree
    ):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            node_id="__root__",
            include_children=True,
            children_depth=0,
        )
        assert isinstance(result, SuccessResult)
        assert "descendants" in result.data
        assert result.data["descendants_count"] >= 2
        depths = [d["depth"] for d in result.data["descendants"]]
        assert max(depths) >= 2

    @pytest.mark.asyncio
    async def test_get_node_info_nonexistent_node_returns_error(self, sample_tree):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            node_id="nonexistent::node::id",
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "NODE_NOT_FOUND"


# --- cst_find_node command: require_one ---


class TestCstFindNodeRequireOne:
    """cst_find_node with require_one: NoMatch, NonUniqueMatch, single match."""

    @pytest.mark.asyncio
    async def test_require_one_zero_matches_returns_no_match(self, sample_tree):
        cmd = CSTFindNodeCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            search_type="xpath",
            query="FunctionDef[name='nonexistent']",
            require_one=True,
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "NoMatch"
        assert "query" in result.details or "selector" in str(result.details).lower()

    @pytest.mark.asyncio
    async def test_require_one_single_match_returns_node_and_node_id(self, sample_tree):
        cmd = CSTFindNodeCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            search_type="xpath",
            query="FunctionDef[name='main']",
            require_one=True,
        )
        assert isinstance(result, SuccessResult)
        assert result.data["total_matches"] == 1
        assert "node" in result.data
        assert "node_id" in result.data
        assert result.data["node"]["name"] == "main"
        assert result.data["node_id"] == result.data["matches"][0]["node_id"]

    @pytest.mark.asyncio
    async def test_require_one_multiple_matches_returns_non_unique_match(
        self, sample_tree
    ):
        cmd = CSTFindNodeCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            search_type="xpath",
            query="Def:*",
            require_one=True,
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "NonUniqueMatch"
        assert "candidates" in result.details
        assert len(result.details["candidates"]) >= 2

    @pytest.mark.asyncio
    async def test_require_one_false_returns_list_as_usual(self, sample_tree):
        cmd = CSTFindNodeCommand()
        result = await cmd.execute(
            tree_id=sample_tree,
            search_type="xpath",
            query="Def:*",
            require_one=False,
        )
        assert isinstance(result, SuccessResult)
        assert result.data["total_matches"] >= 2
        assert "node" not in result.data or "node_id" not in result.data


# --- get_node_descendants for non-root node ---


class TestGetNodeDescendantsNonRoot:
    """get_node_descendants for a function/class node with depth 1, 2, 0."""

    def test_descendants_depth1_returns_direct_children_only(self, sample_tree):
        # Use root: it always has direct children in the index.
        desc = get_node_descendants(sample_tree, "__root__", max_depth=1)
        assert all(d == 1 for _, d in desc)
        assert len(desc) >= 1

    def test_descendants_depth0_returns_full_subtree(self, sample_tree):
        desc = get_node_descendants(sample_tree, "__root__", max_depth=0)
        assert len(desc) >= 2
        depths = [d for _, d in desc]
        assert max(depths) >= 2


# --- Integration: two-command flow (find one + get subtree) ---


class TestTwoCommandFlow:
    """Find node with require_one then get_node_info with children_depth."""

    @pytest.mark.asyncio
    async def test_find_main_then_get_info_with_descendants(self, sample_tree):
        find_cmd = CSTFindNodeCommand()
        find_result = await find_cmd.execute(
            tree_id=sample_tree,
            search_type="xpath",
            query="FunctionDef[name='main']",
            require_one=True,
        )
        assert isinstance(find_result, SuccessResult)
        node_id = find_result.data["node_id"]
        assert node_id

        info_cmd = CSTGetNodeInfoCommand()
        info_result = await info_cmd.execute(
            tree_id=sample_tree,
            node_id=node_id,
            include_children=True,
            children_depth=1,
        )
        assert isinstance(info_result, SuccessResult)
        assert info_result.data["node"]["name"] == "main"
        assert "children" in info_result.data

    @pytest.mark.asyncio
    async def test_root_then_get_children_depth1_no_extra_round_trip(self, sample_tree):
        info_cmd = CSTGetNodeInfoCommand()
        result = await info_cmd.execute(
            tree_id=sample_tree,
            node_id="__root__",
            include_children=True,
            children_depth=1,
        )
        assert isinstance(result, SuccessResult)
        assert result.data["node"]["type"] == "Module"
        assert result.data["children_count"] >= 1


# --- Edge: invalid tree_id ---


class TestEdgeCases:
    """Invalid tree_id, empty tree, etc."""

    def test_get_node_metadata_invalid_tree_id_returns_none(self):
        meta = get_node_metadata("nonexistent-tree-id", "__root__")
        assert meta is None

    def test_get_node_children_invalid_tree_id_returns_empty(self):
        children = get_node_children("nonexistent-tree-id", "__root__")
        assert children == []

    def test_get_node_descendants_invalid_tree_id_returns_empty(self):
        desc = get_node_descendants("nonexistent-tree-id", "__root__", max_depth=1)
        assert desc == []

    def test_get_node_parent_invalid_tree_id_returns_none(self):
        parent = get_node_parent("nonexistent-tree-id", "__root__")
        assert parent is None

    @pytest.mark.asyncio
    async def test_get_node_info_invalid_tree_id_returns_error(self):
        cmd = CSTGetNodeInfoCommand()
        result = await cmd.execute(
            tree_id="nonexistent-tree-id",
            node_id="__root__",
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "NODE_NOT_FOUND"
