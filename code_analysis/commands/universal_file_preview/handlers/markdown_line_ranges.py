"""
Markdown section line ranges (1-based inclusive) for preview and text edit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt

from ..errors import PreviewError, input_error, INPUT_ERROR_UNKNOWN_NODE_REF

_md = MarkdownIt()

_CONTENT_SUFFIX = "/__content"


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _source_line_count(raw: str) -> int:
    if not raw:
        return 0
    return raw.count("\n") + (1 if not raw.endswith("\n") else 0)


def _heading_sections(source: str) -> list[dict[str, Any]]:
    """Collect heading sections with 1-based line spans and slug node_refs."""
    tokens = _md.parse(source)
    total_lines = _source_line_count(source)
    entries: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = [
        {"level": 0, "node_ref": "", "slug": "", "start_line": 1}
    ]
    slug_counter: dict[str, int] = {}

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "heading_open":
            level = int(token.tag[1:])
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            title = ""
            if inline is not None:
                if inline.children:
                    title = "".join(
                        c.content
                        for c in inline.children
                        if c.type in ("text", "code_inline")
                    )
                elif inline.content:
                    title = inline.content
            raw_slug = _slugify(title)
            slug_counter[raw_slug] = slug_counter.get(raw_slug, 0) + 1
            slug = (
                raw_slug
                if slug_counter[raw_slug] == 1
                else f"{raw_slug}-{slug_counter[raw_slug]}"
            )
            while len(stack) > 1 and stack[-1]["level"] >= level:
                stack.pop()
            parent_ref = stack[-1]["node_ref"]
            node_ref = f"{parent_ref}.{slug}" if parent_ref else slug
            start_line = token.map[0] + 1 if token.map else 1
            entry = {
                "level": level,
                "title": title,
                "slug": slug,
                "node_ref": node_ref,
                "start_line": start_line,
            }
            entries.append(entry)
            stack.append(entry)
            i += 3
            continue
        i += 1

    for idx, entry in enumerate(entries):
        level = entry["level"]
        start = entry["start_line"]
        end_line = total_lines
        for later in entries[idx + 1 :]:
            if later["level"] <= level:
                end_line = later["start_line"] - 1
                break
        entry["end_line"] = max(start, end_line)
    return entries


def _body_line_range(
    source: str,
    heading_start: int,
    section_end: int,
) -> tuple[int, int] | None:
    """First/last 1-based lines of non-empty body before a child heading."""
    lines = source.splitlines()
    if heading_start > len(lines):
        return None
    body_start = heading_start + 1
    if body_start > section_end:
        return None
    first = None
    last = None
    for ln in range(body_start, section_end + 1):
        if ln > len(lines):
            break
        if lines[ln - 1].strip():
            if first is None:
                first = ln
            last = ln
    if first is None or last is None:
        return None
    return first, last


def resolve_markdown_line_range(
    source: str,
    node_ref: str,
) -> tuple[int, int] | PreviewError:
    """Resolve a markdown preview node_ref to inclusive 1-based line bounds."""
    if node_ref == "__content" or node_ref.endswith(_CONTENT_SUFFIX):
        parent_ref = (
            "" if node_ref == "__content" else node_ref[: -len(_CONTENT_SUFFIX)]
        )
        entries = _heading_sections(source)
        parent = next((e for e in entries if e["node_ref"] == parent_ref), None)
        if parent is None and parent_ref:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Markdown node_ref {node_ref!r} not found in document.",
                details={"node_ref": node_ref},
            )
        if parent is None:
            body = _body_line_range(source, 1, _source_line_count(source))
            if body is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Markdown node_ref {node_ref!r} has no content lines.",
                    details={"node_ref": node_ref},
                )
            return body
        body = _body_line_range(source, parent["start_line"], parent["end_line"])
        if body is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Markdown node_ref {node_ref!r} has no content lines.",
                details={"node_ref": node_ref},
            )
        return body

    entries = _heading_sections(source)
    if node_ref == "":
        total = _source_line_count(source)
        if not entries:
            return 1, max(1, total)
        return 1, max(1, entries[0]["start_line"] - 1) if entries else (1, total)

    match = next((e for e in entries if e["node_ref"] == node_ref), None)
    if match is None:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            f"Markdown node_ref {node_ref!r} not found in document.",
            details={"node_ref": node_ref},
        )
    # Section range includes the heading line (``start_line``) through ``end_line``.
    # Body-only edits use the ``/__content`` suffix (see branch above).
    return match["start_line"], match["end_line"]
