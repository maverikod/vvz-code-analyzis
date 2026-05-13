"""
NavigationProcedure (C-006) for universal_file_preview.

Single three-phase function shared by all NodeKind values and all file
types: enumerate the focus node's block set, select a subset via
Selector (C-007), render each selected block via BlockHandler (C-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .base_handler import FileHandler
from .block_handlers import render_block
from .budget import PreviewBudget
from .errors import PreviewError
from .models import Block, NavigationResult, Node
from .selector import apply_selector
from .session import resolve_session


def navigate(
    handler: FileHandler,
    params: dict[str, Any],
    budget: PreviewBudget,
) -> NavigationResult | PreviewError:
    """
    Execute the three-phase NavigationProcedure (C-006) for one request.

    Phase 1 — enumerate: produce the focus node's ordered block set.
    Phase 2 — select: apply Selector (C-007) to the block set.
    Phase 3 — render: invoke BlockHandler (C-008) for each selected block.

    Args:
        handler: FileHandler resolved by HandlerDispatcher for the file.
        params: Validated parameter dict containing keys:
                'file_path' (str), 'node_ref' (str|None),
                'selector' (str|list|None), 'project_id' (str),
                'tree_id' (str|None).
        budget: PreviewBudget with preview_lines and value_preview_len.

    Returns:
        NavigationResult on success, or PreviewError on failure.
    """
    session_result = resolve_session(handler, params)
    if isinstance(session_result, PreviewError):
        return session_result
    session, session_origin, tree_id = session_result

    open_result = handler.open_root(params["file_path"], session)
    if isinstance(open_result, PreviewError):
        return open_result
    focus_node: Node = open_result
    if params.get("node_ref") is not None:
        resolve_result = handler.resolve_node_ref(params["node_ref"], session)
        if isinstance(resolve_result, PreviewError):
            return resolve_result
        focus_node = resolve_result
    block_set: list[Node] = focus_node.children
    total_blocks = len(block_set)

    selector_result = apply_selector(
        params.get("selector"), block_set, budget.preview_lines
    )
    if isinstance(selector_result, PreviewError):
        return selector_result
    selected_nodes = selector_result

    selected_blocks: list[Block] = []
    for node in selected_nodes:
        summary = render_block(node, budget.value_preview_len)
        selected_blocks.append(
            Block(
                node_kind=node.node_kind,
                node_ref=node.node_ref,
                summary=summary,
            )
        )

    return NavigationResult(
        focus_node=focus_node,
        total_blocks=total_blocks,
        selected_blocks=selected_blocks,
        tree_id=tree_id if session_origin == "command_created" else None,
    )
