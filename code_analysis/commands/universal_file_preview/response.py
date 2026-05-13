"""
Response envelope assembly for universal_file_preview.

Builds the uniform top-level ResponseEnvelope (C-012) returned by
UniversalFilePreviewCommand on every successful request.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

from .models import Node, Block, NavigationResult


def build_envelope(
    navigation_result: NavigationResult,
    raw_selector: str | list | None,
    session_origin: str | None,
) -> dict[str, Any]:
    """
    Build the ResponseEnvelope (C-012) from a NavigationResult.

    The envelope shape is constant regardless of NodeKind and selector form.
    Fields always present:
      focus            - dict with node_kind, node_ref, type, name, attributes
      selector_applied - normalised selector or None
      total_blocks     - int: total count of blocks in focus block set
      blocks           - list of rendered block dicts
    Field present only when session_origin == 'command_created' and
    navigation_result.tree_id is not None:
      tree_id          - str: UUID for reuse by the caller

    Args:
        navigation_result: Output of the NavigationProcedure.
        raw_selector: Original selector value from the caller (for echo-back).
        session_origin: One of 'caller_owned', 'command_created', 'none', or None.

    Returns:
        Dict conforming to ResponseEnvelope (C-012).
    """
    focus = navigation_result.focus_node
    focus_dict = {
        "node_kind": focus.node_kind.value,
        "node_ref": focus.node_ref,
        "type": focus.type_label,
        "name": focus.name,
        "attributes": focus.attributes or {},
    }

    # Normalise selector for echo-back: keep as-is if already str or list;
    # set to None if raw_selector is None.
    selector_applied: str | list | None = raw_selector

    blocks_list = [
        {
            "node_kind": b.node_kind.value,
            "node_ref": b.node_ref,
            "summary": b.summary,
        }
        for b in navigation_result.selected_blocks
    ]

    envelope: dict[str, Any] = {
        "focus": focus_dict,
        "selector_applied": selector_applied,
        "total_blocks": navigation_result.total_blocks,
        "blocks": blocks_list,
    }

    if session_origin == "command_created" and navigation_result.tree_id is not None:
        envelope["tree_id"] = navigation_result.tree_id

    return envelope
