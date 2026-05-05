"""
Data models for CST tree management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import libcst as cst
# @node-id: 2755b7c6-b880-41e3-a847-8a9b18a19c92


class TreeOperationType(str, Enum):
    """Type of tree operation."""

    REPLACE = "replace"
    REPLACE_RANGE = "replace_range"
    INSERT = "insert"
    DELETE = "delete"
    MOVE = "move"
# @node-id: 0caef3d7-2202-42f7-bbcc-5e4468d668d1


@dataclass(frozen=True)
class TreeNodeMetadata:
    """
    Metadata for a CST node.

    This is a lightweight representation of a node that can be sent to clients
    without the full CST tree structure.

    stable_id is assigned once at node creation and never changes across rebuilds.
    node_id may be reassigned after index rebuild; stable_id always points back
    to the original UUID so callers can use it as a durable handle.
    """

    node_id: str
    stable_id: str  # Original UUID assigned at creation, never changes on rebuild
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
    # @node-id: 35484752-a42e-44fd-b7c3-1a6e9b337ce6

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {
            "node_id": self.node_id,
            "stable_id": self.stable_id,
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
    # @node-id: 59cd5cd2-4ab4-4a45-aae6-0214f845e944

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TreeNodeMetadata:
        """Build metadata from :meth:`to_dict` / sidecar JSON."""
        children_ids = data.get("children_ids")
        if children_ids is not None and not isinstance(children_ids, list):
            children_ids = []
        return cls(
            node_id=str(data["node_id"]),
            stable_id=str(data.get("stable_id") or data["node_id"]),
            type=str(data["type"]),
            kind=str(data["kind"]),
            name=data.get("name"),
            qualname=data.get("qualname"),
            start_line=int(data.get("start_line", 1)),
            start_col=int(data.get("start_col", 0)),
            end_line=int(data.get("end_line", 1)),
            end_col=int(data.get("end_col", 0)),
            children_count=int(data.get("children_count", 0)),
            children_ids=[str(x) for x in (children_ids or [])],
            parent_id=(
                str(data["parent_id"]) if data.get("parent_id") is not None else None
            ),
            code=data.get("code"),
        )
# @node-id: 088d4371-27fa-4418-b3aa-0a5cc3f0baca


@dataclass
class TreeOperation:
    """
    Operation to modify a CST tree.

    Operations are validated before being applied. All operations in a batch
    are applied atomically (either all succeed or all fail).
    """

    action: TreeOperationType
    node_id: str = (
        ""  # Node ID for replace/delete operations (empty for insert with target_node_id)
    )
    code: Optional[str] = None  # New code for replace/insert (single string)
    code_lines: Optional[List[str]] = (
        None  # New code as list of lines (alternative to code)
    )
    position: Optional[str] = (
        None  # "before"|"after"|"first"|"last"|"end" for insert; "first"|"last"|"after" for move
    )
    position_after_index: Optional[int] = (
        None  # 0-based sibling index for position "after" (insert/move after this child)
    )
    parent_node_id: Optional[str] = (
        None  # Parent node for insert/move (use __root__ for module level)
    )
    target_node_id: Optional[str] = (
        None  # Target node for insert (alternative to parent_node_id)
    )
    start_node_id: Optional[str] = None  # Start node for replace_range
    end_node_id: Optional[str] = None  # End node for replace_range


# Reserved node_id: denotes the Module (root) node of the tree.
ROOT_NODE_ID_SENTINEL = "__root__"
# @node-id: 59046bff-9e30-4c51-b544-6093cd25a219


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
    node_id_aliases: Dict[str, str] = field(default_factory=dict)
    # node_id_aliases: old_node_id -> current_node_id (transitive closure).
    # Populated after each _build_tree_index call so that stale UUIDs from
    # previous cst_modify_tree calls are automatically resolved to current ones.
    # Cleared on reload_tree_from_file (full UUID reset from disk).
    root_node_id: Optional[str] = (
        None  # Set at index build; used to resolve ROOT_NODE_ID_SENTINEL
    )
    loaded_at: float = field(default_factory=time.monotonic)
    last_accessed_at: float = field(default_factory=time.monotonic)
    # Snapshot of UTF-8 file text at last disk sync (load/reload); None/0 = no snapshot.
    disk_source_sha256_hex: Optional[str] = None
    disk_source_length: int = 0
    module_source_sha256_hex: Optional[str] = None
    # @node-id: a26289ef-ea9e-4aac-987a-6366cb4f8041

    @classmethod
    def create(cls, file_path: str, module: cst.Module) -> CSTTree:
        """Create a new CSTTree with generated tree_id."""
        tree_id = str(uuid.uuid4())
        return cls(
            tree_id=tree_id,
            file_path=file_path,
            module=module,
        )
    # @node-id: 31856faa-ff2c-4600-8339-b2f7f02794c3

    def find_by_stable_id(self, stable_id: str) -> Optional[TreeNodeMetadata]:
        """Find node metadata by stable_id.

        stable_id is assigned once at node creation and never changes,
        even after tree rebuilds caused by insert/delete operations.

        Args:
            stable_id: The stable user-facing node identifier

        Returns:
            TreeNodeMetadata if found, None otherwise
        """
        for meta in self.metadata_map.values():
            if meta.stable_id == stable_id:
                return meta
        return None
