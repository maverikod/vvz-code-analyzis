"""
Apply modify operations to an in-memory JSON tree and rebuild index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .json_pointer import (
    delete_at,
    get_value_at,
    insert_into_array,
    insert_into_object,
    set_value_at,
)
from .models import ROOT_POINTER, JSONTree
from .tree_builder import _build_index, get_tree

logger = logging.getLogger(__name__)


def _deep_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _pointer_for_node(tree: JSONTree, node_id: str) -> str:
    p = tree.pointer_by_id.get(node_id)
    if p is None:
        raise KeyError(f"Unknown node_id: {node_id}")
    return p


def modify_tree(tree_id: str, operations: List[Dict[str, Any]]) -> JSONTree:
    """
    Apply operations in order; rebuild index after each operation.

    Supported actions:
    - replace: node_id (optional if json_pointer set), json_pointer (optional), value
    - delete: node_id or json_pointer
    - insert: parent_node_id or parent_json_pointer, value, key (object) or index (array, optional)
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    for op in operations:
        action = (op.get("action") or "").lower()
        if action == "replace":
            _op_replace(tree, op)
        elif action == "delete":
            _op_delete(tree, op)
        elif action == "insert":
            _op_insert(tree, op)
        else:
            raise ValueError(f"Unknown action: {action!r}")

        _build_index(tree)

    return tree


def _resolve_pointer(tree: JSONTree, op: Dict[str, Any]) -> str:
    if "json_pointer" in op:
        return str(op["json_pointer"])
    if op.get("node_id"):
        return _pointer_for_node(tree, str(op["node_id"]))
    raise ValueError("Operation requires json_pointer or node_id")


def _resolve_parent_pointer(tree: JSONTree, op: Dict[str, Any]) -> str:
    if "parent_json_pointer" in op:
        return str(op["parent_json_pointer"])
    if op.get("parent_node_id"):
        return _pointer_for_node(tree, str(op["parent_node_id"]))
    raise ValueError("insert requires parent_node_id or parent_json_pointer")


def _op_replace(tree: JSONTree, op: Dict[str, Any]) -> None:
    pointer = _resolve_pointer(tree, op)
    if "value" not in op:
        raise ValueError("replace requires value")
    value = _deep_json_value(op["value"])
    if pointer == ROOT_POINTER:
        tree.root_data = value
        return
    set_value_at(tree.root_data, pointer, value)


def _op_delete(tree: JSONTree, op: Dict[str, Any]) -> None:
    pointer = _resolve_pointer(tree, op)
    if pointer == ROOT_POINTER:
        raise ValueError("Cannot delete root document")
    delete_at(tree.root_data, pointer)


def _op_insert(tree: JSONTree, op: Dict[str, Any]) -> None:
    parent_pointer = _resolve_parent_pointer(tree, op)
    if "value" not in op:
        raise ValueError("insert requires value")
    value = _deep_json_value(op["value"])
    parent_val = get_value_at(tree.root_data, parent_pointer)

    if isinstance(parent_val, dict):
        key = op.get("key")
        if key is None or not isinstance(key, str):
            raise ValueError("insert into object requires string key")
        insert_into_object(tree.root_data, parent_pointer, key, value)
        return

    if isinstance(parent_val, list):
        idx = op.get("index")
        if idx is None:
            insert_into_array(tree.root_data, parent_pointer, value, None)
        else:
            if not isinstance(idx, int):
                raise ValueError("insert into array requires integer index when set")
            insert_into_array(tree.root_data, parent_pointer, value, idx)
        return

    raise TypeError("insert parent must be object or array")
