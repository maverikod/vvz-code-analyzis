"""
Author Vasiliy Zdanovskiy, vasilyvz@gmail.com — Markdown FormatHandler (C-007).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from markdown_it import MarkdownIt

from code_analysis.tree.contracts import NodeId, UnknownNodeIdError
from code_analysis.tree.format_handler import FormatHandler, ShortIdAllocator
from code_analysis.tree.tree_node import TreeNode

_MARKER_RE = re.compile(r"^<!-- id:(\d+) -->\n", re.MULTILINE)
_MD = MarkdownIt()
_TOKEN_TO_KIND = {
    "heading_open": "heading",
    "paragraph_open": "paragraph",
    "fence": "code_block",
    "code_block": "code_block",
    "blockquote_open": "blockquote",
    "list_item_open": "list_item",
}
_LEAF_KINDS = frozenset({"paragraph", "code_block"})
_VALID_POSITIONS = frozenset({"before", "after", "first_child", "last_child"})


def _classify_block_content(content: str) -> tuple[str, Dict[str, Any]]:
    """Infer the tree node kind and attributes for one Markdown block."""
    stripped = content.strip()
    if not stripped:
        return "paragraph", {"level": 0}
    tokens = _MD.parse(stripped)
    for tok in tokens:
        kind = _TOKEN_TO_KIND.get(tok.type)
        if kind is None:
            continue
        level = 0
        if kind == "heading" and tok.tag and tok.tag[1:].isdigit():
            level = int(tok.tag[1:])
        return kind, {"level": level}
    return "paragraph", {"level": 0}


def _validate_block_content(content: str) -> None:
    """Reject empty or unparsable Markdown block content."""
    if not content.strip():
        raise ValueError("new_content must not be empty or whitespace-only")
    tokens = _MD.parse(content)
    for tok in tokens:
        if tok.type in _TOKEN_TO_KIND:
            return
    raise ValueError("new_content is not a valid markdown block for this format")


def _parse_blocks(marked_text: str) -> List[TreeNode]:
    """Parse marker-delimited Markdown text into flat tree nodes."""
    matches = list(_MARKER_RE.finditer(marked_text))
    if not matches:
        return []
    nodes: List[TreeNode] = []
    for idx, match in enumerate(matches):
        sid = int(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(marked_text)
        block_content = marked_text[start:end]
        kind, attributes = _classify_block_content(block_content)
        nodes.append(
            TreeNode(
                short_id=NodeId(sid),
                kind=kind,
                content=block_content,
                attributes=attributes,
            )
        )
    return nodes


def _serialize_blocks(nodes: List[TreeNode]) -> str:
    """Serialize flat Markdown tree nodes back to marked source text."""
    if not nodes:
        return ""
    parts: List[str] = []
    for idx, node in enumerate(nodes):
        content = node.content
        if idx < len(nodes) - 1 and content and not content.endswith("\n\n"):
            if not content.endswith("\n"):
                content = content + "\n"
            content = content + "\n"
        parts.append(f"<!-- id:{node.short_id} -->\n{content}")
    return "".join(parts)


def _find_short_id(nodes: List[TreeNode], short_id: NodeId) -> TreeNode:
    """Return the node with short_id or raise UnknownNodeIdError."""
    for node in nodes:
        if node.short_id == short_id:
            return node
    raise UnknownNodeIdError(short_id)


def _find_index(nodes: List[TreeNode], short_id: NodeId) -> int:
    """Return the list index for short_id or raise UnknownNodeIdError."""
    for idx, node in enumerate(nodes):
        if node.short_id == short_id:
            return idx
    raise UnknownNodeIdError(short_id)


def _resolve_insert_index(
    nodes: List[TreeNode], anchor_short_id: NodeId, position: str
) -> int:
    """Resolve an insert position around an anchor block."""
    if position not in _VALID_POSITIONS:
        raise ValueError(f"invalid position: {position!r}")
    anchor_idx = _find_index(nodes, anchor_short_id)
    if position in ("before", "first_child"):
        return anchor_idx
    return anchor_idx + 1


def _resolve_move_insert_index(
    nodes: List[TreeNode], anchor_short_id: NodeId, position: str
) -> int:
    """Resolve the destination index for a move operation."""
    if position not in _VALID_POSITIONS:
        raise ValueError(f"invalid position: {position!r}")
    anchor_idx = _find_index(nodes, anchor_short_id)
    if position in ("before", "first_child"):
        return anchor_idx
    return anchor_idx + 1


class MarkdownHandler(FormatHandler):
    """Format handler for marker-based Markdown block editing."""

    def parse_content(self, file_path: Path, content: str) -> List[TreeNode]:
        """Parse Markdown source into editable block nodes."""
        if content == "":
            return []
        allocator = ShortIdAllocator(1)
        tokens = _MD.parse(content)
        lines = content.splitlines()
        nodes: List[TreeNode] = []
        for tok in tokens:
            kind = _TOKEN_TO_KIND.get(tok.type)
            if kind is None:
                continue
            sid = allocator.allocate()
            level = (
                int(tok.tag[1:])
                if kind == "heading" and tok.tag and tok.tag[1:].isdigit()
                else 0
            )
            start, end = tok.map or (0, 1)
            block_content = "\n".join(lines[start:end])
            nodes.append(
                TreeNode(
                    short_id=NodeId(sid),
                    kind=kind,
                    content=block_content,
                    attributes={
                        "level": level,
                        "start_line": start + 1,
                        "end_line": end,
                    },
                )
            )
        return nodes

    def mark(self, content: str) -> str:
        """Insert stable short-id comments before editable Markdown blocks."""
        allocator = ShortIdAllocator(1)
        tokens = _MD.parse(content)
        lines = content.splitlines(keepends=True)
        inserts: Dict[int, str] = {}
        for tok in tokens:
            if tok.type not in _TOKEN_TO_KIND:
                continue
            if tok.map:
                line_no = tok.map[0]
                if line_no not in inserts:
                    inserts[line_no] = f"<!-- id:{allocator.allocate()} -->\n"
        result: List[str] = []
        for i, line in enumerate(lines):
            if i in inserts:
                result.append(inserts[i])
            result.append(line)
        return "".join(result)

    def unmark(self, marked_text: str) -> str:
        """Remove short-id marker comments from Markdown source text."""
        return _MARKER_RE.sub("", marked_text)

    def sidecar_path(self, source_abs: Path) -> Path:
        """Return the sidecar path used for this source file."""
        return source_abs.parent / (source_abs.name + ".tree")

    def op_insert(
        self,
        marked_text: str,
        anchor_short_id: NodeId,
        position: str,
        new_content: str,
        next_free: int,
    ) -> str:
        """Insert a new Markdown block relative to an anchor block."""
        if next_free < 1:
            raise ValueError("next_free must be >= 1")
        _validate_block_content(new_content)
        nodes = _parse_blocks(marked_text)
        insert_idx = _resolve_insert_index(nodes, anchor_short_id, position)
        kind, attributes = _classify_block_content(new_content)
        trailing_blank = insert_idx < len(nodes)
        block_content = new_content.rstrip("\n")
        if trailing_blank:
            block_content = block_content + "\n\n"
        elif not block_content.endswith("\n"):
            block_content = block_content + "\n"
        new_node = TreeNode(
            short_id=NodeId(next_free),
            kind=kind,
            content=block_content,
            attributes=attributes,
        )
        nodes.insert(insert_idx, new_node)
        return _serialize_blocks(nodes)

    def op_delete(self, marked_text: str, short_id: NodeId) -> str:
        """Delete the block identified by short_id."""
        nodes = _parse_blocks(marked_text)
        idx = _find_index(nodes, short_id)
        nodes.pop(idx)
        return _serialize_blocks(nodes)

    def op_replace(self, marked_text: str, short_id: NodeId, new_content: str) -> str:
        """Replace the full Markdown block identified by short_id."""
        _validate_block_content(new_content)
        nodes = _parse_blocks(marked_text)
        node = _find_short_id(nodes, short_id)
        idx = _find_index(nodes, short_id)
        kind, attributes = _classify_block_content(new_content)
        trailing_blank = idx < len(nodes) - 1
        block_content = new_content.rstrip("\n")
        if trailing_blank:
            block_content = block_content + "\n\n"
        elif not block_content.endswith("\n"):
            block_content = block_content + "\n"
        node.content = block_content
        node.kind = kind
        node.attributes = attributes
        return _serialize_blocks(nodes)

    def extract_move_payload(self, marked_text: str, short_id: NodeId) -> str:
        """Return the block text used as payload for move operations."""
        nodes = _parse_blocks(marked_text)
        node = _find_short_id(nodes, short_id)
        return node.content.rstrip("\n")

    def op_move(
        self,
        marked_text: str,
        short_id: NodeId,
        anchor_short_id: NodeId,
        position: str,
    ) -> str:
        """Move one Markdown block relative to another block."""
        next_free = self.peak_short_id_in_marked(marked_text) + 1
        return self.op_move_via_delete_insert(
            marked_text,
            short_id,
            anchor_short_id,
            position,
            next_free,
        )

    def op_edit_attributes(
        self, marked_text: str, short_id: NodeId, attributes: Dict[str, Any]
    ) -> str:
        """Merge updated attributes into the selected Markdown block node."""
        nodes = _parse_blocks(marked_text)
        node = _find_short_id(nodes, short_id)
        node.attributes.update(attributes)
        return _serialize_blocks(nodes)

    def op_edit_content(
        self, marked_text: str, short_id: NodeId, new_content: str
    ) -> str:
        """Edit the content of a leaf Markdown block in place."""
        nodes = _parse_blocks(marked_text)
        node = _find_short_id(nodes, short_id)
        if node.kind not in _LEAF_KINDS:
            raise ValueError("edit-content requires leaf block")
        idx = _find_index(nodes, short_id)
        trailing_blank = idx < len(nodes) - 1
        block_content = new_content.rstrip("\n")
        if trailing_blank:
            block_content = block_content + "\n\n"
        elif block_content and not block_content.endswith("\n"):
            block_content = block_content + "\n"
        node.content = block_content
        return _serialize_blocks(nodes)
