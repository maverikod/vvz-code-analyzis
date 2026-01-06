"""
Module patcher implementation for CST module tools.

This is the core logic used by `compose_cst_module`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
from typing import Any, Optional

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from ...cst_query import query_source
from .blocks import list_cst_blocks
from .errors import CSTModulePatchError
from .models import BlockInfo, ReplaceOp, Selector
from .utils import move_module_imports_to_top


def _parse_snippet_as_module_body(snippet: str) -> list[cst.BaseStatement]:
    """Parse a snippet into a list of module-level statements."""
    if not snippet.strip():
        return []
    mod = cst.parse_module(snippet)
    return list(mod.body)


class _StatementListRewriter(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        stmt_by_span: dict[tuple[int, int, int, int], list[cst.BaseStatement]],
        stmt_by_lines: dict[tuple[int, int], list[cst.BaseStatement]],
        small_by_span: dict[tuple[int, int, int, int], list[cst.BaseSmallStatement]],
    ):
        self._stmt_by_span = stmt_by_span
        self._stmt_by_lines = stmt_by_lines
        self._small_by_span = small_by_span

    def _rewrite_body(
        self,
        original_body: list[cst.BaseStatement],
        updated_body: list[cst.BaseStatement],
    ) -> list[cst.BaseStatement]:
        new_body: list[cst.BaseStatement] = []
        for original_stmt, updated_stmt in zip(original_body, updated_body):
            pos = self.get_metadata(PositionProvider, original_stmt, None)
            if pos is None:
                new_body.append(updated_stmt)
                continue
            span_key = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)
            line_key = (pos.start.line, pos.end.line)
            if span_key in self._stmt_by_span:
                new_body.extend(self._stmt_by_span[span_key])
            elif line_key in self._stmt_by_lines:
                new_body.extend(self._stmt_by_lines[line_key])
            else:
                new_body.append(updated_stmt)
        return new_body

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        return updated_node.with_changes(
            body=self._rewrite_body(list(original_node.body), list(updated_node.body))
        )

    def leave_IndentedBlock(
        self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock
    ) -> cst.IndentedBlock:
        return updated_node.with_changes(
            body=self._rewrite_body(list(original_node.body), list(updated_node.body))
        )

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.SimpleStatementLine:
        new_small: list[cst.BaseSmallStatement] = []
        for original_s, updated_s in zip(original_node.body, updated_node.body):
            pos = self.get_metadata(PositionProvider, original_s, None)
            if pos is None:
                new_small.append(updated_s)
                continue
            span_key = (pos.start.line, pos.start.column, pos.end.line, pos.end.column)
            if span_key in self._small_by_span:
                new_small.extend(self._small_by_span[span_key])
            else:
                new_small.append(updated_s)

        if not new_small:
            raise CSTModulePatchError(
                "Cannot delete all small statements from a SimpleStatementLine; "
                "target the whole statement line instead."
            )
        return updated_node.with_changes(body=new_small)


_NODE_ID_RE = re.compile(
    r"^(?P<kind>[^:]+):(?P<qualname>[^:]*):(?P<type>[^:]+):"
    r"(?P<sl>\d+):(?P<sc>\d+)-(?P<el>\d+):(?P<ec>\d+)$"
)


def _parse_node_id(node_id: str) -> tuple[str, tuple[int, int, int, int]]:
    """
    Parse node_id returned by `query_cst`.

    Format:
        "{kind}:{qualname}:{node_type}:{sl}:{sc}-{el}:{ec}"
    """
    m = _NODE_ID_RE.match(node_id.strip())
    if not m:
        raise CSTModulePatchError(f"Invalid node_id: {node_id}")
    kind = m.group("kind")
    return kind, (
        int(m.group("sl")),
        int(m.group("sc")),
        int(m.group("el")),
        int(m.group("ec")),
    )


def _parse_small_stmt_snippet(snippet: str) -> list[cst.BaseSmallStatement]:
    if not snippet.strip():
        return []
    mod = cst.parse_module(snippet)
    if len(mod.body) != 1 or not isinstance(mod.body[0], cst.SimpleStatementLine):
        raise CSTModulePatchError(
            "Small-statement replacement must be a single SimpleStatementLine (e.g. 'return 1')"
        )
    return list(mod.body[0].body)


def apply_replace_ops(source: str, ops: list[ReplaceOp]) -> tuple[str, dict[str, Any]]:
    """
    Apply replace operations to blocks in `source`.

    If source is empty and there's a "module" selector, create module from scratch.

    Returns:
        (new_source, stats)
    """
    # Handle module creation from scratch
    for op in ops:
        if op.selector.kind == "module":
            # Validate required parameters - both must be present and non-empty
            if not op.file_docstring or not op.file_docstring.strip():
                raise CSTModulePatchError(
                    "file_docstring is required and must not be empty when creating module from scratch"
                )
            if not op.new_code or not op.new_code.strip():
                raise CSTModulePatchError(
                    "new_code (first node) is required and must not be empty when creating module from scratch"
                )

            # Parse first node
            first_node_module = cst.parse_module(op.new_code)
            if not first_node_module.body:
                raise CSTModulePatchError(
                    "new_code must contain at least one node (function or class)"
                )

            # Create module with docstring and first node
            # LibCST docstring format: triple-quoted string
            docstring_value = op.file_docstring.strip()
            # Ensure it's properly quoted (handle if already has quotes)
            if not (
                docstring_value.startswith('"""') or docstring_value.startswith("'''")
            ):
                docstring_value = f'"""{docstring_value}"""'

            docstring_stmt = cst.SimpleStatementLine(
                body=[cst.Expr(value=cst.SimpleString(value=docstring_value))]
            )

            # Build module body: docstring + first node
            module_body: list[cst.BaseStatement] = [docstring_stmt]
            module_body.extend(first_node_module.body)

            # Create module
            new_module = cst.Module(body=module_body)

            # Normalize imports (will move imports after docstring)
            new_module = move_module_imports_to_top(new_module)

            stats = {
                "replaced": 0,
                "removed": 0,
                "created": 1,
                "unmatched": [],
            }
            return (new_module.code, stats)

    # Normal path: apply replacements to existing source
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    blocks = list_cst_blocks(source)
    blocks_by_id = {b.block_id: b for b in blocks}
    blocks_by_kind_name: dict[tuple[str, str], BlockInfo] = {
        (b.kind, b.qualname): b for b in blocks
    }

    replaced = 0
    removed = 0
    unmatched: list[Selector] = []

    stmt_replacements_by_span: dict[
        tuple[int, int, int, int], list[cst.BaseStatement]
    ] = {}
    stmt_replacements_by_lines: dict[tuple[int, int], list[cst.BaseStatement]] = {}
    small_replacements_by_span: dict[
        tuple[int, int, int, int], list[cst.BaseSmallStatement]
    ] = {}

    for op in ops:
        sel = op.selector
        target: Optional[BlockInfo] = None

        if sel.kind == "block_id" and sel.block_id:
            target = blocks_by_id.get(sel.block_id)
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if sel.kind in ("function", "class") and sel.name:
            target = blocks_by_kind_name.get((sel.kind, sel.name))
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if sel.kind == "method" and sel.name:
            target = blocks_by_kind_name.get(("method", sel.name))
            if target is None:
                unmatched.append(sel)
                continue
            new_stmts = _parse_snippet_as_module_body(op.new_code)
            stmt_replacements_by_lines[(target.start_line, target.end_line)] = new_stmts
            replaced += 1 if new_stmts else 0
            removed += 0 if new_stmts else 1
            continue

        if (
            sel.kind == "range"
            and sel.start_line is not None
            and sel.end_line is not None
        ):
            if sel.start_col is not None and sel.end_col is not None:
                span_key = (sel.start_line, sel.start_col, sel.end_line, sel.end_col)
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_span[span_key] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            else:
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_lines[(sel.start_line, sel.end_line)] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            continue

        if sel.kind == "node_id" and sel.node_id:
            kind, span_key = _parse_node_id(sel.node_id)
            if kind in ("stmt", "function", "class", "method"):
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_span[span_key] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            elif kind == "smallstmt":
                new_small = _parse_small_stmt_snippet(op.new_code)
                small_replacements_by_span[span_key] = new_small
                replaced += 1 if new_small else 0
                removed += 0 if new_small else 1
            else:
                raise CSTModulePatchError(
                    f"node_id replacement supports only stmt/smallstmt/function/class/method nodes, got {kind}"
                )
            continue

        if sel.kind == "cst_query" and sel.query:
            matches = query_source(source, sel.query, include_code=False)
            if not matches:
                unmatched.append(sel)
                continue
            idx = sel.match_index
            if idx is None:
                if len(matches) != 1:
                    raise CSTModulePatchError(
                        f"Selector matched {len(matches)} nodes; use :nth() or match_index"
                    )
                idx = 0
            if idx < 0 or idx >= len(matches):
                raise CSTModulePatchError(
                    f"match_index {idx} out of bounds for {len(matches)} matches"
                )
            m = matches[idx]
            span_key = (m.start_line, m.start_col, m.end_line, m.end_col)
            if m.kind in ("stmt", "function", "class", "method"):
                new_stmts = _parse_snippet_as_module_body(op.new_code)
                stmt_replacements_by_span[span_key] = new_stmts
                replaced += 1 if new_stmts else 0
                removed += 0 if new_stmts else 1
            elif m.kind == "smallstmt":
                new_small = _parse_small_stmt_snippet(op.new_code)
                small_replacements_by_span[span_key] = new_small
                replaced += 1 if new_small else 0
                removed += 0 if new_small else 1
            else:
                raise CSTModulePatchError(
                    f"cst_query replacement supports only stmt/smallstmt/function/class/method matches, got {m.kind}"
                )
            continue

        raise CSTModulePatchError(f"Unsupported selector kind: {sel.kind}")

    patched = wrapper.visit(
        _StatementListRewriter(
            stmt_by_span=stmt_replacements_by_span,
            stmt_by_lines=stmt_replacements_by_lines,
            small_by_span=small_replacements_by_span,
        )
    )
    patched = move_module_imports_to_top(patched)
    new_source = patched.code

    stats = {
        "replaced": replaced,
        "removed": removed,
        "created": 0,
        "unmatched": [
            {
                "kind": s.kind,
                "name": s.name,
                "start_line": s.start_line,
                "start_col": s.start_col,
                "end_line": s.end_line,
                "end_col": s.end_col,
                "block_id": s.block_id,
                "node_id": s.node_id,
                "query": s.query,
                "match_index": s.match_index,
            }
            for s in unmatched
        ],
    }
    return new_source, stats
