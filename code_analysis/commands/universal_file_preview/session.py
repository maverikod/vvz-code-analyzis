"""
TreeSession (C-011) ownership and lifecycle for universal_file_preview.

The command supports two modes:
  Caller-owned: caller passes tree_id; command reads without creating.
  Command-owned: no tree_id supplied; command opens a transient session
               and returns its tree_id in the response for reuse.

The command never closes or invalidates a caller-owned session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any

from .base_handler import FileHandler
from .errors import PreviewError

logger = logging.getLogger(__name__)


def resolve_session(
    handler: FileHandler,
    params: dict[str, Any],
) -> tuple[Any | None, str, str | None] | PreviewError:
    """
    Resolve the TreeSession (C-011) for the request.

    Returns a 3-tuple: (session, session_origin, tree_id).
      session: the in-memory session object (type depends on handler), or None
               when no session infrastructure is needed by the handler.
      session_origin: 'caller_owned' when tree_id was supplied by the caller;
                      'command_created' when the command opened the session;
                      'none' when no session is used.
      tree_id: the session UUID when session_origin=='command_created', else None.

    The command never closes a caller_owned session.

    Args:
        handler: The FileHandler that will use the session.
        params: Validated parameter dict, may contain 'tree_id'.

    Returns:
        3-tuple or PreviewError.
    """
    tree_id_param = params.get("tree_id")
    if tree_id_param is not None:
        # Caller-owned: look up via get_tree (global in-memory CST registry)
        from ...core.cst_tree.tree_builder import get_tree  # noqa: PLC0415

        session = get_tree(tree_id_param)
        if session is None:
            # Unknown tree_id — treat as CONFLICTING_PARAMETERS
            from .errors import (
                INPUT_ERROR_CONFLICTING_PARAMETERS,
                input_error,
            )

            return input_error(
                INPUT_ERROR_CONFLICTING_PARAMETERS,
                f"tree_id {tree_id_param!r} not found in session registry.",
                details={"tree_id": tree_id_param},
            )
        return (session, "caller_owned", None)
    # Command-owned transient session: defer to handler's open_root; no pre-open.
    # The handler is responsible for opening its own session internally if needed.
    return (None, "none", None)
