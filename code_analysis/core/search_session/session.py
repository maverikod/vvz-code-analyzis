"""
SearchSession entity and lifecycle state transitions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Final, Optional

INVALID_SESSION_TRANSITION: Final[str] = "INVALID_SESSION_TRANSITION"


class SearchSessionState(str, Enum):
    """Lifecycle state of a search session."""

    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    dead = "dead"
    expired = "expired"
    closed = "closed"


_TERMINAL_STATES = frozenset(
    {
        SearchSessionState.completed,
        SearchSessionState.failed,
        SearchSessionState.cancelled,
        SearchSessionState.timed_out,
        SearchSessionState.dead,
        SearchSessionState.expired,
        SearchSessionState.closed,
    }
)


@dataclass(frozen=True)
class SearchSession:
    """
    Logical execution context for one search request.

    Attributes:
        search_id: UUID string used for HTTP access to index, blocks, and status.
        state: Current lifecycle state.
        directory_path: Absolute path to the on-disk session directory root.
    """

    search_id: str
    state: SearchSessionState
    directory_path: Optional[Path] = None


def create_search_session(*, directory_path: Optional[Path] = None) -> SearchSession:
    """
    Create a new running search session with a fresh UUID.

    Args:
        directory_path: Optional session directory root. None until directory provisioning binds it.

    Returns:
        New SearchSession in ``running`` state.
    """
    return SearchSession(
        search_id=str(uuid.uuid4()),
        state=SearchSessionState.running,
        directory_path=directory_path.resolve() if directory_path is not None else None,
    )


def transition_session_state(
    session: SearchSession,
    new_state: SearchSessionState,
) -> SearchSession:
    """
    Return a new session with ``new_state``.

    Terminal states cannot transition back to ``running``.

    Raises:
        ValueError: With code ``INVALID_SESSION_TRANSITION`` when transition is illegal.
    """
    if session.state in _TERMINAL_STATES and new_state == SearchSessionState.running:
        raise ValueError(
            f"{INVALID_SESSION_TRANSITION}: cannot move from {session.state.value} to running"
        )
    if session.state == new_state:
        return session
    return replace(session, state=new_state)
