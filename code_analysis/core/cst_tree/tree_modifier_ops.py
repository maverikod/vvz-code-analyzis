"""
CST tree modifier operations: replace, delete, insert helpers.

Extracted from tree_modifier for size limit. Used only by tree_modifier.
Facade re-exports from tree_modifier_ops_parse, _find, _replace, _insert.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .tree_modifier_ops_find import (
    delete_node,
    find_node_in_module_by_position,
    find_parent_in_module_by_position,
)
from .tree_modifier_ops_insert import (
    insert_node,
    insert_node_at_position,
    insert_node_relative,
)
from .tree_modifier_ops_parse import (
    parse_code_snippet,
    parse_code_snippet_or_comment,
)
from .tree_modifier_ops_replace import replace_node, replace_range

__all__ = [
    "parse_code_snippet",
    "parse_code_snippet_or_comment",
    "delete_node",
    "find_node_in_module_by_position",
    "find_parent_in_module_by_position",
    "replace_node",
    "replace_range",
    "insert_node_at_position",
    "insert_node",
    "insert_node_relative",
]
