"""
MarkdownFileHandler -- FileHandler for .md files (C-017 extension).

Builds a section tree from the Markdown AST via markdown-it-py.
Root NodeKind is 'mapping' (document root).
Each heading creates a section Node whose children are nested
sub-sections and scalar blocks for paragraphs, code fences, etc.

node_ref format: dot-separated slug path from root,
e.g. '2.etapy-pajplajjna.2-3-vektorizacija'.
Document root has node_ref ''.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from ..models import Node, NodeKind

logger = logging.getLogger(__name__)

_md = MarkdownIt()

_UUID_PREFIX_WIDTH = 39  # "[" + 36-char UUID + "] "
_MD_SKIP_TOKEN_TYPES = frozenset({"inline"})


def _source_line_count(raw: str) -> int:
    if not raw:
        return 0
    return raw.count("\n") + (1 if not raw.endswith("\n") else 0)


def _read_markdown_source(file_path: str) -> str:
    """Read UTF-8 source; fall back from empty ``*.draft`` to the original file."""
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        source = ""
    if source or not file_path.endswith(".draft"):
        return source
    original_path = file_path[: -len(".draft")]
    try:
        return Path(original_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return source


def _iter_md_block_tokens(tokens: list[Any]) -> Any:
    for token in tokens:
        if token.map is None or token.type in _MD_SKIP_TOKEN_TYPES:
            continue
        if token.type.endswith("_close"):
            continue
        yield token


def _md_block_node_ref(file_path: str, token: Any) -> str:
    start = token.map[0]
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{token.type}:{start}"))


def _build_line_to_node_ref(tokens: list[Any], file_path: str) -> dict[int, str]:
    line_to_ref: dict[int, str] = {}
    level_at_line: dict[int, int] = {}
    for token in tokens:
        start = token.map[0]
        if start in line_to_ref and token.level <= level_at_line[start]:
            continue
        line_to_ref[start] = _md_block_node_ref(file_path, token)
        level_at_line[start] = token.level
    return line_to_ref


def _block_token_to_node(file_path: str, token: Any) -> Node:
    assert token.map is not None
    return Node(
        node_kind=NodeKind.TREE_NODE,
        node_ref=_md_block_node_ref(file_path, token),
        type_label=token.type,
        attributes={
            "start_line": token.map[0] + 1,
            "end_line": token.map[1],
        },
    )


def _annotated_full_text(
    source: str,
    file_path: str,
    budget: PreviewBudget,
) -> tuple[str, list[Node], dict[str, Any]] | None:
    """Annotated source and top-level block nodes when file < ``full_text_max_lines``."""
    if budget.full_text_max_lines <= 0:
        return None
    if _source_line_count(source) >= budget.full_text_max_lines:
        return None
    lines = source.splitlines()
    block_tokens = list(_iter_md_block_tokens(_md.parse(source)))
    line_to_ref = _build_line_to_node_ref(block_tokens, file_path)
    token_by_ref = {_md_block_node_ref(file_path, t): t for t in block_tokens}
    blank = " " * _UUID_PREFIX_WIDTH
    out_lines = [
        (f"[{line_to_ref[i]}] {line}" if i in line_to_ref else blank + line)
        for i, line in enumerate(lines)
    ]
    top_blocks = [
        _block_token_to_node(file_path, t) for t in block_tokens if t.level == 0
    ]
    return "\n".join(out_lines), top_blocks, token_by_ref


def _slugify(text: str) -> str:
    """Lowercase slug with hyphens for heading node_ref paths."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _token_text(token: Any) -> str:
    """Plain text from a markdown-it token subtree."""
    parts: list[str] = []
    if token.children:
        for child in token.children:
            if child.type in ("text", "code_inline"):
                parts.append(child.content)
            elif child.type == "softbreak":
                parts.append(" ")
    elif token.content:
        parts.append(token.content)
    return "".join(parts)


class _Section:
    """One Markdown section (heading level, slug path, nested children)."""

    def __init__(
        self,
        level: int,
        title: str,
        slug: str,
        node_ref: str,
    ) -> None:
        self.level = level
        self.title = title
        self.slug = slug
        self.node_ref = node_ref
        self.content_lines: list[str] = []
        self.children: list[_Section] = []

    def to_node(self) -> Node:
        """Mapping Node for this section and descendants."""
        child_nodes: list[Node] = []
        if self.content_lines:
            content_text = "\n".join(self.content_lines).strip()
            if content_text:
                content_ref = (
                    self.node_ref + "/__content" if self.node_ref else "__content"
                )
                child_nodes.append(
                    Node(
                        node_kind=NodeKind.SCALAR,
                        node_ref=content_ref,
                        attributes={"value": content_text},
                    )
                )
        for child in self.children:
            child_nodes.append(child.to_node())
        title_attr = self.title if self.title else "(document root)"
        return Node(
            node_kind=NodeKind.MAPPING,
            node_ref=self.node_ref,
            attributes={
                "title": title_attr,
                "level": str(self.level),
                "slug": self.slug,
            },
            _children=child_nodes,
        )


def _build_section_tree(source: str) -> _Section:
    """Section tree from markdown-it heading and content tokens."""
    tokens = _md.parse(source)
    root = _Section(level=0, title="", slug="", node_ref="")
    stack: list[_Section] = [root]
    slug_counter: dict[str, int] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "heading_open":
            level = int(token.tag[1:])
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            title = _token_text(inline) if inline else ""
            raw_slug = _slugify(title)
            slug_counter[raw_slug] = slug_counter.get(raw_slug, 0) + 1
            slug = (
                raw_slug
                if slug_counter[raw_slug] == 1
                else f"{raw_slug}-{slug_counter[raw_slug]}"
            )
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1]
            parent_ref = parent.node_ref
            node_ref = f"{parent_ref}.{slug}" if parent_ref else slug
            section = _Section(level=level, title=title, slug=slug, node_ref=node_ref)
            parent.children.append(section)
            stack.append(section)
            i += 3
            continue
        if token.type not in ("heading_close", "inline"):
            current = stack[-1]
            if token.content:
                current.content_lines.append(token.content)
            elif token.type in (
                "fence",
                "code_block",
                "html_block",
                "bullet_list_open",
                "ordered_list_open",
                "blockquote_open",
                "table_open",
                "hr",
            ):
                current.content_lines.append(f"[{token.type}]")
        i += 1
    return root


def _find_section(root: _Section, node_ref: str) -> _Section | None:
    """DFS lookup of a section by dot-separated slug path."""
    if root.node_ref == node_ref:
        return root
    for child in root.children:
        found = _find_section(child, node_ref)
        if found is not None:
            return found
    return None


class MarkdownFileHandler(FileHandler):
    """FileHandler for .md: section tree or annotated full-text (C-017)."""

    def __init__(self) -> None:
        self._last_file_path: str | None = None
        self._last_tree: _Section | None = None
        self._last_block_tokens: dict[str, Any] = {}

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".md"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """Root Node: annotated TREE_NODE below full_text_max_lines, else section mapping."""
        self._last_file_path = file_path
        source = _read_markdown_source(file_path)
        effective_budget = (
            budget
            if budget is not None
            else PreviewBudget(preview_lines=20, value_preview_len=120)
        )
        full = _annotated_full_text(source, file_path, effective_budget)
        if full is not None:
            annotated, block_nodes, token_by_ref = full
            self._last_block_tokens = token_by_ref
            self._last_tree = None
            return Node(
                node_kind=NodeKind.TREE_NODE,
                node_ref="",
                type_label="markdown_document",
                attributes={"text": annotated, "full_text": True},
                _children=block_nodes,
            )
        tree = _build_section_tree(source)
        self._last_tree = tree
        self._last_block_tokens = {}
        return tree.to_node()

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """Resolve uuid5 block id, slug path, or ``/__content`` section body."""
        token = self._last_block_tokens.get(node_ref)
        if token is not None:
            fp = self._last_file_path or ""
            return _block_token_to_node(fp, token)

        if self._last_tree is None:
            fp = self._last_file_path or ""
            source = _read_markdown_source(fp) if fp else ""
            self._last_tree = _build_section_tree(source)

        # Handle /__content suffix: the scalar body child of a section.
        _CONTENT_SUFFIX = "/__content"
        if node_ref == "__content" or node_ref.endswith(_CONTENT_SUFFIX):
            if node_ref == "__content":
                parent_ref = ""
            else:
                parent_ref = node_ref[: -len(_CONTENT_SUFFIX)]
            parent_section = _find_section(self._last_tree, parent_ref)
            if parent_section is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Markdown node_ref {node_ref!r} not found in document.",
                    details={"node_ref": node_ref},
                )
            parent_node = parent_section.to_node()
            for child in parent_node.children:
                if child.node_ref == node_ref:
                    return child
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Markdown node_ref {node_ref!r} not found: section has no content block.",
                details={"node_ref": node_ref},
            )

        # Regular section slug path.
        section = _find_section(self._last_tree, node_ref)
        if section is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Markdown node_ref {node_ref!r} not found in document.",
                details={"node_ref": node_ref},
            )
        return section.to_node()
