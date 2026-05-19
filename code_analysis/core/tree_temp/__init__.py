"""Tree-temp Sidecar domain package: TreeNode entity, Sidecar JSON helpers, `.trees/` path resolver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.tree_temp.sidecar_paths import (
    TREES_DIRECTORY_NAME,
    SidecarPathError,
    resolve_trees_sidecar_path,
)
from code_analysis.core.tree_temp.sidecar_payload import (
    SidecarParseError,
    parse_sidecar_json_bytes,
    parse_sidecar_json_text,
    serialize_sidecar_to_json_text,
    validate_sidecar_source_sha256_field,
)
from code_analysis.core.tree_temp.tree_node import (
    TreeNode,
    tree_node_from_json_dict,
    tree_node_to_json_dict,
    validate_node_constraints,
)

__all__ = [
    "TreeNode",
    "SidecarParseError",
    "SidecarPathError",
    "TREES_DIRECTORY_NAME",
    "parse_sidecar_json_bytes",
    "parse_sidecar_json_text",
    "serialize_sidecar_to_json_text",
    "resolve_trees_sidecar_path",
    "tree_node_from_json_dict",
    "tree_node_to_json_dict",
    "validate_node_constraints",
    "validate_sidecar_source_sha256_field",
]
