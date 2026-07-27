"""
Unit tests: content_stale roundtrip check's CA-native write path (bug 25c8d9dd wave-2).

``universal_file_open`` / ``universal_file_edit`` / ``universal_file_write`` are not
registered on the live code-analysis-server (editor-only surface, confirmed 404 via
``help(universal_file_save)``; see ``code_analysis/commands/registration.py``). The
check must instead overwrite the seeded file through
``project_file_transfer_upload_save`` UPDATE mode — client facade
``FileSessionClient.upload(session_id, payload, file_id, ...)`` — which delegates to
the same ``UniversalFileSaveCommand`` -> ``persist_plain_text_file_metadata`` pipeline
that sets ``content_stale=1`` on its existing-row UPDATE branch (commit 345f083c).

These tests stub the client entirely (no live server) and pin: (1) the roundtrip
calls ``file_sessions.upload`` (update mode) exactly once, with ``file_id`` and
``project_id`` matching the seeded file, and never calls the unregistered
``universal_file_open`` / ``universal_file_edit`` / ``universal_file_write`` commands;
(2) a raised exception from that call surfaces a FAILED outcome naming both the
write path and the verbatim exception, never an opaque failure; (3) the full
stale -> reindex -> clear roundtrip still reports EXECUTED_OK when the stubbed
search responses show the flag flipping as expected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _verify_client_all_commands_catalog import Status  # noqa: E402
from _verify_client_all_commands_fixtures import FixtureContext  # noqa: E402
from _verify_client_all_commands_lifecycle_content_stale import (  # noqa: E402
    CHECK_NAME,
    run_content_stale_roundtrip_check,
)


class _StubFileSessions:
    """Records ``upload_new``/``upload`` calls; never touches a real transport."""

    def __init__(self) -> None:
        self.upload_new_calls: List[Any] = []
        self.upload_calls: List[Dict[str, Any]] = []
        self.raise_on_upload: Optional[Exception] = None

    async def upload_new(
        self, session_id: str, payload: bytes, project_id: str, file_path: str
    ) -> str:
        self.upload_new_calls.append((session_id, payload, project_id, file_path))
        return "stub-file-id"

    async def upload(
        self,
        session_id: str,
        payload: bytes,
        file_id: str,
        *,
        project_id: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self.upload_calls.append(
            {
                "session_id": session_id,
                "payload": payload,
                "file_id": file_id,
                "project_id": project_id,
                "filename": filename,
                **kwargs,
            }
        )
        if self.raise_on_upload is not None:
            raise self.raise_on_upload
        return {"success": True, "file_id": file_id, "changed": True}


class _StubClient:
    """Minimal stand-in for ``CodeAnalysisAsyncClient`` used by this check.

    ``search_stale_sequence`` supplies the ``content_stale`` value returned by
    each successive ``search`` call (call 0 = post-write check, call 1 =
    post-reindex check) so tests can drive the stale->clear roundtrip
    explicitly. Every ``call_validated`` invocation is recorded so tests can
    assert the unregistered ``universal_file_open``/``edit``/``write`` never
    fire (the exact regression this fix closes).
    """

    def __init__(
        self, *, search_stale_sequence: Optional[List[bool]] = None
    ) -> None:
        self.file_sessions = _StubFileSessions()
        self.calls: List[Any] = []
        self._search_stale_sequence = (
            search_stale_sequence
            if search_stale_sequence is not None
            else [False, True, False]
        )
        self._search_call_count = 0

    async def call_validated(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.calls.append((command, dict(params)))

        if command == "update_indexes":
            return {"success": True, "data": {}}

        if command in {
            "git_identity_set",
            "git_add",
            "git_commit",
            "git_branch_checkout",
            "git_remote_add",
            "git_remote_remove",
            "git_pull_safe",
        }:
            return {"success": True, "data": {}}

        if command == "git_status":
            return {"success": True, "data": {"branch": "main"}}

        if command == "search":
            relative_path = (
                self.file_sessions.upload_new_calls[0][3]
                if self.file_sessions.upload_new_calls
                else ""
            )
            idx = self._search_call_count
            self._search_call_count += 1
            stale = (
                self._search_stale_sequence[idx]
                if idx < len(self._search_stale_sequence)
                else self._search_stale_sequence[-1]
            )
            return {
                "success": True,
                "data": {
                    "items": [{"file_path": relative_path, "content_stale": stale}],
                    "job_id": f"job-{idx}",
                },
            }

        if command == "search_close":
            return {"success": True, "data": {}}

        raise AssertionError(f"unexpected command in stub: {command!r}")


def _fixtures() -> FixtureContext:
    return FixtureContext(
        project_id="fixture-project-id",
        project_name="fixture-project",
        watch_dir_id="wd-0",
        project_root=Path("/var/casmgr/watch_catalog/x/fixture-project"),
        session_id="fixture-session-id",
    )


@pytest.mark.asyncio
async def test_roundtrip_uses_upload_update_mode_not_unregistered_edit_commands() -> None:
    """Happy path: exactly one file_sessions.upload() call; no universal_file_* calls."""
    client = _StubClient()

    outcomes = await run_content_stale_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.EXECUTED_OK, outcome.reason

    assert len(client.file_sessions.upload_calls) == 1
    call = client.file_sessions.upload_calls[0]
    assert call["file_id"] == "stub-file-id"
    assert call["project_id"] == "fixture-project-id"
    assert call["session_id"] == "fixture-session-id"

    command_names = {name for name, _ in client.calls}
    for forbidden in (
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_save",
    ):
        assert forbidden not in command_names, (
            f"{forbidden!r} is not registered on the live server and must never "
            "be called by this check"
        )


@pytest.mark.asyncio
async def test_roundtrip_fails_loud_when_upload_raises() -> None:
    """A raised exception from the update-mode save is reported, never swallowed."""
    client = _StubClient()
    client.file_sessions.raise_on_upload = RuntimeError("boom")

    outcomes = await run_content_stale_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "boom" in outcome.reason
    assert "project_file_transfer_upload_save" in outcome.reason


@pytest.mark.asyncio
async def test_roundtrip_fails_when_flag_never_clears_after_reindex() -> None:
    """content_stale still true after update_indexes -> FAILED, not a false green."""
    client = _StubClient(search_stale_sequence=[False, True, True])

    outcomes = await run_content_stale_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "expected False" in outcome.reason


@pytest.mark.asyncio
async def test_roundtrip_skips_when_fixture_session_missing() -> None:
    """No fixture session_id -> EXPECTED_ERROR skip, no calls attempted."""
    client = _StubClient()
    fixtures = FixtureContext(
        project_id="fixture-project-id",
        project_name="fixture-project",
        watch_dir_id="wd-0",
        project_root=Path("/var/casmgr/watch_catalog/x/fixture-project"),
        session_id=None,
    )

    outcomes = await run_content_stale_roundtrip_check(client, fixtures)

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.EXPECTED_ERROR
    assert not client.calls
    assert not client.file_sessions.upload_new_calls
    assert not client.file_sessions.upload_calls
