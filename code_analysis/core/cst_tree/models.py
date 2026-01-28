"""
Data models for CST tree management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import libcst as cst


class TreeOperationType(str, Enum):
    """Type of tree operation."""

    REPLACE = "replace"
    REPLACE_RANGE = "replace_range"
    INSERT = "insert"
    DELETE = "delete"


@dataclass(frozen=True)
class TreeNodeMetadata:
    """
    Metadata for a CST node.

    This is a lightweight representation of a node that can be sent to clients
    without the full CST tree structure.
    """

    node_id: str
    type: str  # LibCST node type (e.g., "FunctionDef", "ClassDef")
    kind: str  # Node kind (e.g., "function", "class", "method", "stmt", "smallstmt")
    name: Optional[str] = None
    qualname: Optional[str] = None
    start_line: int = 1
    start_col: int = 0
    end_line: int = 1
    end_col: int = 0
    children_count: int = 0
    children_ids: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "node_id": self.node_id,
            "type": self.type,
            "kind": self.kind,
            "start_line": self.start_line,
            "start_col": self.start_col,
            "end_line": self.end_line,
            "end_col": self.end_col,
            "children_count": self.children_count,
        }
        if self.name is not None:
            result["name"] = self.name
        if self.qualname is not None:
            result["qualname"] = self.qualname
        if self.children_ids:
            result["children_ids"] = self.children_ids
        if self.parent_id is not None:
            result["parent_id"] = self.parent_id
        if self.code is not None:
            result["code"] = self.code
        return result


@dataclass
class TreeOperation:
    """
    Operation to modify a CST tree.

    Operations are validated before being applied. All operations in a batch
    are applied atomically (either all succeed or all fail).
    """

    action: TreeOperationType
    node_id: str = ""  # Node ID for replace/delete operations (empty for insert with target_node_id)
    code: Optional[str] = None  # New code for replace/insert (single string)
    code_lines: Optional[List[str]] = (
        None  # New code as list of lines (alternative to code)
    )
    position: Optional[str] = None  # "before" or "after" for insert
    parent_node_id: Optional[str] = None  # Parent node for insert
    target_node_id: Optional[str] = (
        None  # Target node for insert (alternative to parent_node_id)
    )
    start_node_id: Optional[str] = None  # Start node for replace_range
    end_node_id: Optional[str] = None  # End node for replace_range


@dataclass
class CSTTree:
    """
    CST tree with metadata.

    The full CST tree is stored in memory on the server.
    Clients receive only metadata about nodes.
    """

    tree_id: str
    file_path: str
    module: cst.Module
    node_map: Dict[str, cst.CSTNode] = field(default_factory=dict)
    metadata_map: Dict[str, TreeNodeMetadata] = field(default_factory=dict)
    parent_map: Dict[str, Optional[str]] = field(default_factory=dict)

    @classmethod
    def create(cls, file_path: str, module: cst.Module) -> CSTTree:
        """Create a new CSTTree with generated tree_id."""
        tree_id = str(uuid.uuid4())
        return cls(
            tree_id=tree_id,
            file_path=file_path,
            module=module,
        )
