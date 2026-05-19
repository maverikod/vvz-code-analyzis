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


def _slugify(text: str) -> str:
    """Convert heading text to a URL-safe slug for use in node_ref.

    Args:
        text: Raw heading text.

    Returns:
        Lowercase alphanumeric slug with hyphens replacing non-word chars.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _token_text(token: Any) -> str:
    """Extract plain text from a markdown-it token and its children.

    Args:
        token: A markdown-it Token object.

    Returns:
        Concatenated text content from the token tree.
    """
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
    """Internal mutable representation of one Markdown section.

    Attributes:
        level: Heading level (1-6). 0 means the document root.
        title: Raw heading text (empty string for root).
        slug: URL-safe slug derived from title.
        node_ref: Dot-separated path from the root.
        content_lines: Accumulated non-heading content lines.
        children: Ordered child _Section objects.
    """

    def __init__(
        self,
        level: int,
        title: str,
        slug: str,
        node_ref: str,
    ) -> None:
        """Initialise a section node.

        Args:
            level: Heading level (0 = root, 1-6 = headings).
            title: Raw heading text.
            slug: URL-safe slug for the section.
            node_ref: Dot-separated path from root to this section.
        """
        self.level = level
        self.title = title
        self.slug = slug
        self.node_ref = node_ref
        self.content_lines: list[str] = []
        self.children: list[_Section] = []

    def to_node(self) -> Node:
        """Convert this section and its subtree to a Node.

        Returns:
            A Node of kind MAPPING with child Nodes for content
            blocks and nested sections.
        """
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
    """Parse Markdown source into a section tree.

    Uses markdown-it-py to tokenise the source, then assembles a tree
    of _Section objects from heading tokens, collecting all non-heading
    content tokens as text lines under the nearest parent section.

    Args:
        source: Raw Markdown text.

    Returns:
        A _Section representing the document root (level 0).
    """
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
    """Locate a _Section by its node_ref via depth-first search.

    Args:
        root: The root _Section to search from.
        node_ref: Dot-separated path to the target section.

    Returns:
        The matching _Section, or None if not found.
    """
    if root.node_ref == node_ref:
        return root
    for child in root.children:
        found = _find_section(child, node_ref)
        if found is not None:
            return found
    return None


class MarkdownFileHandler(FileHandler):
    """FileHandler for Markdown files (.md) (C-017 extension).

    Parses the file into a section tree using markdown-it-py.
    Root NodeKind: mapping (document root).
    Children: nested sections (mapping) and content blocks (scalar).
    node_ref: dot-separated slug path, e.g. '2.etapy-pajplajjna'.
    Empty string refers to the document root.

    Attributes:
        supported_extensions: Frozenset containing '.md'.
    """

    def __init__(self) -> None:
        """Initialise MarkdownFileHandler state."""
        self._last_file_path: str | None = None
        self._last_tree: _Section | None = None

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports.

        Returns:
            Frozenset containing the single extension '.md'.
        """
        return frozenset({".md"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """Parse the Markdown file and return the document root Node.

        When *budget* is provided and ``budget.full_text_max_lines`` is a positive
        integer, and the file has fewer lines than that threshold, returns a
        ``NodeKind.SCALAR`` node whose ``value`` attribute holds the entire file
        source.  This mirrors the C-023 full-text fallback implemented for the
        Python handler and lets callers read small Markdown files in one step.

        Args:
            file_path: Absolute or project-relative path to the .md file.
            session: Ignored for Markdown files.
            budget: Optional PreviewBudget; when provided, full_text_max_lines
                    is honoured.

        Returns:
            Scalar Node with full text when file is below the line threshold,
            otherwise a mapping root Node representing the document.
        """
        self._last_file_path = file_path
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        if (
            budget is not None
            and budget.full_text_max_lines > 0
            and source.count("\n") + (1 if source and not source.endswith("\n") else 0)
            < budget.full_text_max_lines
        ):
            return Node(
                node_kind=NodeKind.SCALAR,
                node_ref="",
                attributes={"value": source, "full_text": True},
            )
        tree = _build_section_tree(source)
        self._last_tree = tree
        return tree.to_node()

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """Resolve a dot-separated slug path to the corresponding section Node.

        Navigates the section tree built during the most recent open_root
        call. If open_root has not been called, attempts a re-parse from
        the last known file path.

        Args:
            node_ref: Dot-separated slug path from the document root.
                      Empty string returns the document root.
            session: Ignored for Markdown files.

        Returns:
            Mapping Node for the addressed section, or PreviewError.
        """
        if self._last_tree is None:
            fp = self._last_file_path or ""
            try:
                source = (
                    Path(fp).read_text(encoding="utf-8", errors="replace") if fp else ""
                )
            except OSError:
                source = ""
            self._last_tree = _build_section_tree(source)
        section = _find_section(self._last_tree, node_ref)
        if section is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Markdown node_ref {node_ref!r} not found in document.",
                details={"node_ref": node_ref},
            )
        return section.to_node()
