"""
PreviewReference contract for structural search results.

Embeds file path and stable node identity sufficient for universal_file_preview
inspection without inventing a separate result presentation model.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

_UNSTABLE_NODE_ID = "UNSTABLE_NODE_ID"


@dataclass(frozen=True)
class PreviewReference:
    """Preview-compatible reference for one structural search result node."""

    file_path: str
    node_id: Optional[str]
    selector: Optional[str]
    draft_session_id: Optional[str]


def build_preview_reference(
    *,
    file_path: str,
    node_id: Optional[str],
    selector: Optional[str] = None,
    draft_session_id: Optional[str] = None,
    stable_id_verified: bool,
) -> PreviewReference:
    """Build a PreviewReference after stable-id validation.

    Raises:
        ValueError: With code ``UNSTABLE_NODE_ID`` when *node_id* is set but
            *stable_id_verified* is False.
        ValueError: When neither *node_id* nor *selector* is provided.
    """
    if node_id and not stable_id_verified:
        raise ValueError(_UNSTABLE_NODE_ID)
    if not node_id and not selector:
        raise ValueError("preview reference requires node_id or selector")
    return PreviewReference(
        file_path=file_path,
        node_id=node_id,
        selector=selector,
        draft_session_id=draft_session_id,
    )


def preview_reference_to_dict(ref: PreviewReference) -> dict[str, Any]:
    """Serialize a PreviewReference for search result JSON payloads."""
    payload: dict[str, Any] = {"file_path": ref.file_path}
    if ref.node_id is not None:
        payload["node_id"] = ref.node_id
    if ref.selector is not None:
        payload["selector"] = ref.selector
    if ref.draft_session_id is not None:
        payload["draft_session_id"] = ref.draft_session_id
    return payload


__all__ = [
    "PreviewReference",
    "build_preview_reference",
    "preview_reference_to_dict",
]
