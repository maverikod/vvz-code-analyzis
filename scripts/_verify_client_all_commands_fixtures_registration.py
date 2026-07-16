"""
Post-``create_project`` fixture bootstrap: DB registration wait, index
refresh, seeded-file-id resolution, and a throwaway feature branch.

Isolates the polling/indexing steps ``_verify_client_all_commands_fixtures.seed_fixtures``
needs after ``create_project`` returns, so callers relying on ``file_id``
(session locks, transfer-by-id commands, advisory locks) and a second branch
(``git_branch_compare``, upstream/tracking) do not race the server's own
project-registration and indexing pipeline.

``wait_for_project_registered`` runs after the fixture files are uploaded
through the client session (see ``_verify_client_all_commands_fixtures``) and
confirms registration with a real DB-dependent call (``check_vectors``), not
just a snapshot listing, before letting the analysis phase (search,
revectorize, rebuild_faiss, repair_database, repair_worker_status,
change_project_id, ...) proceed. It does not raise on a bounded-wait timeout —
it prints a warning and returns ``False`` so the sweep still runs and
dependent commands surface their own real errors instead of the whole run
aborting.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime import cycle
    from _verify_client_all_commands_fixtures import FixtureContext

_REGISTRATION_TIMEOUT_SECONDS = 180.0
_REGISTRATION_POLL_INTERVAL_SECONDS = 5.0
_NOT_IN_DATABASE_MARKER = "not found in database"


async def wait_for_project_registered(
    client: CodeAnalysisAsyncClient,
    project_id: str,
    *,
    timeout: float = _REGISTRATION_TIMEOUT_SECONDS,
    interval: float = _REGISTRATION_POLL_INTERVAL_SECONDS,
) -> bool:
    """Poll until ``project_id`` is confirmed registered and DB-usable.

    ``create_project`` writes the on-disk ``projectid`` file synchronously, but
    the ``projects`` DB row — required by ``search`` / ``revectorize`` /
    ``rebuild_faiss`` / ``repair_database`` / ``repair_worker_status`` /
    ``check_vectors`` / ``update_indexes`` — is inserted asynchronously by the
    server, only once its own file-watcher scan discovers the project. Calling
    those commands before that row exists fails with a ``VALIDATION_ERROR``
    whose message contains "Project with ID ... not found in database". A
    ``projects.sample`` listing has proven an unreliable signal on its own (it
    can show the row while DB-dependent commands still reject the project), so
    this polls ``check_vectors`` directly — a fast, read-only, DB-dependent
    call — and only declares the project registered once that call stops
    returning the "not found in database" rejection (any other response,
    success or a different error, counts as registered). Watcher scan cycles
    are slow, so the bound is generously long; progress dots are printed while
    waiting so a long run is visibly still alive rather than silent.

    Args:
        client: Connected async client.
        project_id: Disposable project's UUID4.
        timeout: Maximum seconds to wait before giving up.
        interval: Seconds between polls.

    Returns:
        True if registration was confirmed within ``timeout`` seconds; False
        if the bounded wait expired (a warning is printed in that case —
        callers should proceed rather than abort, letting dependent commands
        surface their own real errors).
    """
    deadline = time.monotonic() + timeout
    last_error = "check_vectors never returned a non-registration response"
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            resp = await client.call_validated(
                "check_vectors", {"project_id": project_id}
            )
        except Exception as exc:  # noqa: BLE001 - keep polling until the deadline
            last_error = repr(exc)
        else:
            error_text = str(resp.get("error"))
            if resp.get("success") is True or _NOT_IN_DATABASE_MARKER not in error_text:
                if attempt > 1:
                    print()  # end the progress-dot line before returning
                return True
            last_error = error_text
        print(".", end="", flush=True)
        if attempt % 6 == 0:
            elapsed = attempt * interval
            print(
                f" WARN  still waiting for project {project_id} DB registration "
                f"(elapsed ~{elapsed:.0f}s of {timeout:.0f}s; last: {last_error})"
            )
        await asyncio.sleep(interval)
    print()
    print(
        f"WARN  disposable project {project_id} never confirmed registered "
        f"within {timeout}s (last: {last_error}); proceeding without "
        "confirmation — dependent commands will surface their own real errors."
    )
    return False


async def seed_feature_branch(
    client: CodeAnalysisAsyncClient, fixtures: "FixtureContext"
) -> None:
    """Create a throwaway feature branch for compare/upstream/tracking commands.

    Best-effort: failures are recorded as warnings rather than raised,
    mirroring the existing git history bootstrap in this module's caller.

    Args:
        client: Connected async client.
        fixtures: Fixture context to update in place; ``feature_branch_name``
            must already be set by the caller.
    """
    try:
        resp = await client.call_validated(
            "git_branch_create",
            {
                "project_id": fixtures.project_id,
                "name": fixtures.feature_branch_name,
                "checkout": False,
            },
        )
        if not resp.get("success"):
            fixtures.warnings.append(
                f"git_branch_create({fixtures.feature_branch_name}): {resp.get('error')!r}"
            )
    except Exception as exc:  # noqa: BLE001 - best-effort bootstrap
        fixtures.warnings.append(f"git_branch_create failed: {exc!r}")


async def resolve_seeded_file_ids(
    client: CodeAnalysisAsyncClient, fixtures: "FixtureContext"
) -> None:
    """Fallback resolution for any seeded ``file_id`` not already captured.

    ``client.file_sessions.upload_new`` already returns each ``file_id``
    directly at upload time (see ``_verify_client_all_commands_fixtures``), so
    this is now only a safety net for the case where an id came back empty —
    it re-reads ``list_project_files`` and fills in only the fields still
    unset, without overwriting ids already known to be good. Does nothing (no
    network call) if every id is already resolved. Does not call
    ``update_indexes`` itself — ``wait_for_project_registered`` already used it
    to confirm registration before this runs.

    Args:
        client: Connected async client.
        fixtures: Fixture context to update in place.
    """
    if fixtures.py_file_id and fixtures.yaml_file_id and fixtures.md_file_id:
        return

    try:
        resp = await client.call_validated(
            "list_project_files", {"project_id": fixtures.project_id}
        )
    except Exception as exc:  # noqa: BLE001 - leaves file ids unresolved, not fatal
        fixtures.warnings.append(f"list_project_files failed: {exc!r}")
        return
    if not resp.get("success"):
        fixtures.warnings.append(f"list_project_files: {resp.get('error')!r}")
        return
    data = resp.get("data") or {}
    rows = data.get("files") or []
    by_path: Dict[str, Optional[str]] = {
        str(row.get("path")): (str(row["file_id"]) if row.get("file_id") else None)
        for row in rows
        if isinstance(row, dict)
    }
    fixtures.py_file_id = fixtures.py_file_id or by_path.get(fixtures.py_file_path)
    fixtures.yaml_file_id = fixtures.yaml_file_id or by_path.get(
        fixtures.yaml_file_path
    )
    fixtures.md_file_id = fixtures.md_file_id or by_path.get(fixtures.md_file_path)
    if not fixtures.py_file_id:
        fixtures.warnings.append(
            f"no file_id resolved for seeded file {fixtures.py_file_path!r} "
            "even after the list_project_files fallback"
        )
