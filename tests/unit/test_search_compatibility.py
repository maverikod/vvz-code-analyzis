"""Unit tests for incremental search compatibility routing."""

from __future__ import annotations

from code_analysis.core.search_session.compatibility import (
    BRIDGE_COMMANDS,
    PaginatedSearchHandoff,
    handoff_to_response,
    maybe_route_paginated,
)
from code_analysis.core.search_session.session import (
    SearchSession,
    SearchSessionState,
)


def test_bridge_commands_maps_search_start_backends() -> None:
    """Verify test bridge commands maps search start backends."""
    assert "search_start" in BRIDGE_COMMANDS
    assert set(BRIDGE_COMMANDS["search_start"]) == {
        "fulltext",
        "semantic",
        "grep",
        "cross",
        "tree_query",
    }


def test_maybe_route_paginated_false_returns_legacy_payload() -> None:
    """Verify test maybe route paginated false returns legacy payload."""
    legacy = {"success": True, "results": [{"file_path": "a.py"}]}

    result = maybe_route_paginated(
        params={"paginated": False},
        legacy_executor=lambda: legacy,
        session_factory=lambda: _session("unused"),
    )

    assert result is legacy


def test_maybe_route_paginated_true_returns_job_handoff_only() -> None:
    """Verify test maybe route paginated true returns job handoff only."""
    session = _session("job-123")

    result = maybe_route_paginated(
        params={"paginated": True},
        legacy_executor=lambda: {"unexpected": True},
        session_factory=lambda: session,
    )

    assert result["success"] is True
    assert result["paginated"] is True
    assert result["job_id"] == "job-123"
    assert result["index_url"] == "/search/jobs/job-123/index"
    assert result["first_block_position"] is None
    assert result["legacy_payload"] is None
    assert "results" not in result


def test_handoff_to_response_serializes_dataclass() -> None:
    """Verify test handoff to response serializes dataclass."""
    handoff = PaginatedSearchHandoff(
        job_id="abc",
        index_url="/search/jobs/abc/index",
        first_block_position=1,
        legacy_payload=None,
    )
    payload = handoff_to_response(handoff)
    assert payload["job_id"] == "abc"
    assert payload["first_block_position"] == 1


def _session(search_id: str) -> SearchSession:
    """Return session."""
    return SearchSession(
        search_id=search_id,
        state=SearchSessionState.running,
        directory_path=__import__("pathlib").Path("/tmp/search") / search_id,
    )
