"""
Incremental compatibility layer for opt-in paginated SearchSession routing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Optional

from code_analysis.core.search_session.session import SearchSession

__all__ = [
    "BRIDGE_COMMANDS",
    "PaginatedSearchHandoff",
    "handoff_to_response",
    "maybe_route_paginated",
]

# Bridge command name -> supported backend search_type values for search_start.
BRIDGE_COMMANDS: dict[str, tuple[str, ...]] = {
    "search_start": ("fulltext", "semantic", "grep", "cross", "tree_query"),
}


@dataclass(frozen=True)
class PaginatedSearchHandoff:
    """Paginated execution handoff returned instead of a legacy inline payload."""

    job_id: str
    index_url: str
    first_block_position: Optional[int] = None
    legacy_payload: Optional[dict] = None


def handoff_to_response(handoff: PaginatedSearchHandoff) -> dict:
    """Serialize a handoff for MCP command responses."""
    payload = asdict(handoff)
    payload["success"] = True
    payload["paginated"] = True
    return payload


def maybe_route_paginated(
    *,
    params: dict,
    legacy_executor: Callable[[], dict],
    session_factory: Callable[[], SearchSession],
    first_block_position: Optional[int] = None,
) -> dict:
    """
    Route search execution through legacy or paginated SearchSession paths.

    When ``params["paginated"]`` is not true, ``legacy_executor`` output is returned
    unchanged. When paginated is true, a session is created via ``session_factory``
    and a job handoff is returned without merging a full legacy payload inline.
    """
    if params.get("paginated") is not True:
        return legacy_executor()

    session = session_factory()
    handoff = PaginatedSearchHandoff(
        job_id=session.search_id,
        index_url=f"/search/jobs/{session.search_id}/index",
        first_block_position=first_block_position,
        legacy_payload=None,
    )
    return handoff_to_response(handoff)
