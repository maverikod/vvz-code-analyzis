"""
Ordered session lifecycle for the live-server all-commands verifier.

Exercises ``session_create`` .. ``session_delete`` and the ``subordinate_session_*``
link commands as one dependent chain against a dedicated session created and
torn down entirely within this module — distinct from ``fixtures.session_id``,
which several other commands use generically for the rest of the sweep and
which is only closed by the top-level ``teardown_fixtures``.

``session_delete`` / ``subordinate_session_delete`` are scoped by the
``session_id`` this lifecycle itself creates, so they are executed here rather
than treated as a global/bulk-scope verify-only risk.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import CommandOutcome
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import (
    call_step,
    call_step_with_data,
    skip_outcome,
)


async def run_session_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the ordered session/subordinate-session/file-lock command chain.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}

    create_outcome, create_data = await call_step_with_data(
        client,
        "session_create",
        {"comment": "verify_client_all_commands_live session lifecycle"},
        ok_reason="dedicated lifecycle session created",
    )
    outcomes["session_create"] = create_outcome
    session_id = str((create_data or {}).get("session_id") or "").strip()

    dependent_names = [
        "session_open_file",
        "session_list_file_locks",
        "session_close_file",
        "subordinate_session_create",
        "subordinate_session_get",
        "subordinate_session_update",
        "subordinate_session_delete",
        "session_delete",
    ]
    if not session_id:
        for name in dependent_names:
            outcomes[name] = skip_outcome(
                name,
                "skipped: session_create in this lifecycle did not return a session_id",
                status=create_outcome.status,
            )
        return outcomes

    file_id = fixtures.py_file_id
    if file_id:
        outcomes["session_open_file"] = await call_step(
            client,
            "session_open_file",
            {
                "session_id": session_id,
                "project_id": fixtures.project_id,
                "file_id": file_id,
            },
            ok_reason="locked seeded file via session_open_file",
        )
        outcomes["session_list_file_locks"] = await call_step(
            client, "session_list_file_locks", {"session_id": session_id}
        )
        outcomes["session_close_file"] = await call_step(
            client,
            "session_close_file",
            {
                "session_id": session_id,
                "project_id": fixtures.project_id,
                "file_id": file_id,
            },
            ok_reason="released seeded file via session_close_file",
        )
    else:
        reason = "skipped: no seeded file_id available (list_project_files never resolved one)"
        outcomes["session_open_file"] = skip_outcome("session_open_file", reason)
        outcomes["session_list_file_locks"] = await call_step(
            client, "session_list_file_locks", {"session_id": session_id}
        )
        outcomes["session_close_file"] = skip_outcome("session_close_file", reason)

    server_uuid = str(uuid.uuid4())
    outcomes["subordinate_session_create"] = await call_step(
        client,
        "subordinate_session_create",
        {
            "parent_session_id": session_id,
            "server_uuid": server_uuid,
            "comment": "verify sweep subordinate link",
        },
        ok_reason="subordinate link created against the lifecycle session",
    )
    outcomes["subordinate_session_get"] = await call_step(
        client,
        "subordinate_session_get",
        {"parent_session_id": session_id, "server_uuid": server_uuid},
    )
    outcomes["subordinate_session_update"] = await call_step(
        client,
        "subordinate_session_update",
        {
            "parent_session_id": session_id,
            "server_uuid": server_uuid,
            "comment": "verify sweep subordinate link updated",
        },
    )
    outcomes["subordinate_session_delete"] = await call_step(
        client,
        "subordinate_session_delete",
        {"parent_session_id": session_id, "server_uuid": server_uuid},
        ok_reason="subordinate link deleted at lifecycle teardown",
    )
    outcomes["session_delete"] = await call_step(
        client,
        "session_delete",
        {"session_id": session_id},
        ok_reason="dedicated lifecycle session deleted at teardown",
    )
    return outcomes
