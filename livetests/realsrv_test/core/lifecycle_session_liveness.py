"""
A dead session must give up its file locks (TODO d75d5e9a).

Registered as suite ``s20`` (``realsrv_test.suites.s20_session_liveness``,
``SUITE_NAME = "sessionliveness"``).

The reported failure, via ai-editor bug 3d1dd9ab: an ai-editor container restart
orphaned its Code Analysis session, the exclusive file lock that session held
survived indefinitely, and every later open of that path from a new session
failed. No client could recover -- clients cannot identify a lock's holder and
cannot release another session's lock -- so the only cure was a manual
``session_delete`` by whoever had server access.

This check reproduces that shape end to end against the real server: session A
takes a lock and then stops calling (which is all a crashed client does from the
server's point of view), session B is refused, the reaper runs, and B succeeds.

Two things keep it safe on a shared server. The sweep is scoped with
``only_session_ids`` to session A alone, so nothing else on the box is touched
even though the threshold is deliberately tiny. And B passes its own
``session_id``, which is touched before the sweep, so B cannot reap itself.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from code_analysis_client import CodeAnalysisAsyncClient

from realsrv_test.core.catalog import Bucket, CommandOutcome, Status, truncate
from realsrv_test.core.fixtures import FixtureContext

CHECK_NAME_DEAD_SESSION_LOCK = "dead_session_lock_is_released"
CHECK_NAME_CONFLICT_NAMES_HOLDER = "file_locked_error_names_the_holder"

#: Seconds the abandoned session is left untouched before the sweep. Small
#: because the sweep is scoped to that one session; the point is only that its
#: idle time exceeds the threshold we pass.
_IDLE_SECONDS = 3.0
_REAP_TTL_SECONDS = 1


def _outcome(name: str, status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Wrap one classification as a single-entry outcome map."""
    return {name: CommandOutcome(name, Bucket.BUCKET_A, status, reason)}


def _skip_both(status: Status, reason: str) -> Dict[str, CommandOutcome]:
    """Report the same non-result for both checks this module owns."""
    return {
        **_outcome(CHECK_NAME_DEAD_SESSION_LOCK, status, reason),
        **_outcome(CHECK_NAME_CONFLICT_NAMES_HOLDER, status, reason),
    }


async def _create_session(client: CodeAnalysisAsyncClient, comment: str) -> str:
    """Create a client session and return its id."""
    response = await client.call_validated("session_create", {"comment": comment})
    data = _data_of(response)
    return str((data or {}).get("session_id") or "").strip()


def _data_of(response: Any) -> Optional[Dict[str, Any]]:
    """Extract the data payload from a client response of either shape."""
    if isinstance(response, dict):
        inner = response.get("data")
        return inner if isinstance(inner, dict) else response
    data = getattr(response, "data", None)
    return data if isinstance(data, dict) else None


def _error_details(exc: BaseException) -> Dict[str, Any]:
    """Best-effort extraction of the structured error payload from a client error."""
    for attribute in ("data", "details", "error_data"):
        candidate = getattr(exc, attribute, None)
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


async def _delete_session(client: CodeAnalysisAsyncClient, session_id: str) -> None:
    """Delete a session, ignoring failures during cleanup."""
    if not session_id:
        return
    try:
        await client.call_validated(
            "session_delete", {"session_id": session_id, "force": True}
        )
    except Exception:  # noqa: BLE001 - cleanup must never mask the real result
        pass


async def run_dead_session_lock_release(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """TODO d75d5e9a: a lock must not outlive the session that took it.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Outcomes for the lock-release check and the conflict-payload check.
    """
    file_id = fixtures.py_file_id
    if not file_id:
        return _skip_both(
            Status.INCONCLUSIVE,
            "skipped: no seeded file_id available to lock",
        )

    abandoned = ""
    survivor = ""
    outcomes: Dict[str, CommandOutcome] = {}
    try:
        abandoned = await _create_session(client, "d75d5e9a abandoned session")
        survivor = await _create_session(client, "d75d5e9a surviving session")
        if not abandoned or not survivor:
            return _skip_both(
                Status.INCONCLUSIVE, "session_create did not return a session_id"
            )

        lock_params = {
            "project_id": fixtures.project_id,
            "file_id": file_id,
        }
        await client.call_validated(
            "session_open_file", {"session_id": abandoned, **lock_params}
        )

        # Half one: the conflict must say WHO holds the lock. Before the fix the
        # response was a bare "FILE_LOCKED" with no holder and no liveness, so a
        # client could not tell a live peer from an orphan.
        try:
            await client.call_validated(
                "session_open_file", {"session_id": survivor, **lock_params}
            )
            outcomes.update(
                _outcome(
                    CHECK_NAME_CONFLICT_NAMES_HOLDER,
                    Status.FAILED,
                    (
                        "a second session acquired a lock already held by "
                        f"{abandoned}: exclusive locking is not exclusive"
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - the refusal is the expected path
            details = _error_details(exc)
            holder = str(details.get("holder_session_id") or "")
            if holder == abandoned and "holder_idle_seconds" in details:
                outcomes.update(
                    _outcome(
                        CHECK_NAME_CONFLICT_NAMES_HOLDER,
                        Status.EXECUTED_OK,
                        (
                            "FILE_LOCKED names the holder and its liveness: "
                            f"holder_session_id={holder}, holder_exists="
                            f"{details.get('holder_exists')}, holder_idle_seconds="
                            f"{details.get('holder_idle_seconds')}, holder_expired="
                            f"{details.get('holder_expired')}, ttl_seconds="
                            f"{details.get('ttl_seconds')}"
                        ),
                    )
                )
            else:
                outcomes.update(
                    _outcome(
                        CHECK_NAME_CONFLICT_NAMES_HOLDER,
                        Status.FAILED,
                        (
                            "FILE_LOCKED carried no usable holder information; "
                            f"expected holder {abandoned}, got details="
                            f"{truncate(repr(details))} from {truncate(repr(exc))}"
                        ),
                    )
                )

        # Half two: the abandoned session stops calling, exactly as a crashed
        # client does, and the reaper releases what it was holding.
        await asyncio.sleep(_IDLE_SECONDS)
        reap_response = await client.call_validated(
            "session_reap_dead",
            {
                "session_id": survivor,
                "ttl_seconds": _REAP_TTL_SECONDS,
                "only_session_ids": [abandoned],
            },
        )
        reap_data = _data_of(reap_response) or {}
        reaped_ids = [
            str(item.get("session_id"))
            for item in (reap_data.get("reaped") or [])
            if isinstance(item, dict)
        ]
        if abandoned not in reaped_ids:
            outcomes.update(
                _outcome(
                    CHECK_NAME_DEAD_SESSION_LOCK,
                    Status.FAILED,
                    (
                        f"session_reap_dead did not release the abandoned session "
                        f"{abandoned} after {_IDLE_SECONDS}s idle at "
                        f"ttl_seconds={_REAP_TTL_SECONDS}; report={truncate(repr(reap_data))}"
                    ),
                )
            )
            return outcomes

        try:
            await client.call_validated(
                "session_open_file", {"session_id": survivor, **lock_params}
            )
        except Exception as exc:  # noqa: BLE001 - this is the defect's signature
            outcomes.update(
                _outcome(
                    CHECK_NAME_DEAD_SESSION_LOCK,
                    Status.FAILED,
                    (
                        "the lock survived its session: after reaping "
                        f"{abandoned}, a new session still could not open the "
                        f"file ({truncate(repr(exc))}) -- this is TODO d75d5e9a"
                    ),
                )
            )
            return outcomes

        released_total = reap_data.get("released_lock_total")
        outcomes.update(
            _outcome(
                CHECK_NAME_DEAD_SESSION_LOCK,
                Status.EXECUTED_OK,
                (
                    f"session {abandoned} took an exclusive lock and stopped "
                    f"calling; after {_IDLE_SECONDS}s the scoped sweep released it "
                    f"(released_lock_total={released_total}) and a new session "
                    "acquired the same file"
                ),
            )
        )
        await client.call_validated(
            "session_close_file", {"session_id": survivor, **lock_params}
        )
        return outcomes
    except Exception as exc:  # noqa: BLE001 - a broken chain is a real failure
        reason = truncate(repr(exc))
        for name in (CHECK_NAME_DEAD_SESSION_LOCK, CHECK_NAME_CONFLICT_NAMES_HOLDER):
            outcomes.setdefault(
                name, CommandOutcome(name, Bucket.BUCKET_A, Status.FAILED, reason)
            )
        return outcomes
    finally:
        await _delete_session(client, survivor)
        await _delete_session(client, abandoned)
