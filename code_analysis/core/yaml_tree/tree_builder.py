"""
YAML document tree builder — load file, index nodes, session registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import copy
from pathlib import Path

from typing import Any, Dict, List, Optional

import yaml

from ..json_tree.models import stable_node_id_for_pointer
from .models import ROOT_POINTER, YamlNodeMetadata, YamlTree
from .yaml_pointer import join_pointer

_trees: Dict[str, YamlTree] = {}


def _yaml_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _build_index(tree: YamlTree) -> None:
    tree.metadata_map.clear()
    tree.parent_map.clear()
    tree.pointer_by_id.clear()
    tree.root_node_id = None

    def visit(
        value: Any,
        pointer: str,
        parent_id: Optional[str],
        key: Optional[str],
        index: Optional[int],
    ) -> str:
        node_id = stable_node_id_for_pointer(pointer)
        tree.pointer_by_id[node_id] = pointer
        tree.parent_map[node_id] = parent_id

        children_ids: List[str] = []
        kind = _yaml_kind(value)

        if isinstance(value, dict):
            for k in value.keys():
                child_pointer = join_pointer(pointer, str(k))
                cid = visit(value[k], child_pointer, node_id, str(k), None)
                children_ids.append(cid)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                child_pointer = join_pointer(pointer, str(i))
                cid = visit(item, child_pointer, node_id, None, i)
                children_ids.append(cid)

        meta = YamlNodeMetadata(
            node_id=node_id,
            yaml_pointer=pointer,
            kind=kind,
            parent_id=parent_id,
            key=key,
            index=index,
            children_ids=children_ids,
        )
        tree.metadata_map[node_id] = meta
        if pointer == ROOT_POINTER:
            tree.root_node_id = node_id
        return node_id

    visit(tree.root_data, ROOT_POINTER, None, None, None)


def load_file_to_tree(file_path: str) -> YamlTree:
    """Load a .yaml/.yml file, parse, index, register session."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    suf = path.suffix.lower()
    if suf not in (".yaml", ".yml"):
        raise ValueError(f"File must be .yaml or .yml: {file_path}")

    raw = path.read_text(encoding="utf-8")
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e
    if loaded is None:
        loaded = {}
    return build_yaml_tree_from_data(str(path.resolve()), loaded, register=True)


def build_yaml_tree_from_data(
    file_path: str, data: Any, *, register: bool = False
) -> YamlTree:
    """
    Index YAML value; optionally register session.

    When register is False (e.g. list_yaml_blocks one-shot), tree_id is still unique
    but the session is not stored in ``_trees``.
    """
    tree = YamlTree.create(file_path, copy.deepcopy(data))
    _build_index(tree)
    if register:
        _trees[tree.tree_id] = tree
    return tree


def get_tree(tree_id: str) -> Optional[YamlTree]:
    return _trees.get(tree_id)


def remove_tree(tree_id: str) -> bool:
    if tree_id in _trees:
        del _trees[tree_id]
        return True
    return False
