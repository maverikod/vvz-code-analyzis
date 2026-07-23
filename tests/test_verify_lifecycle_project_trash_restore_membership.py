"""
Unit tests: project_trash_restore_roundtrip check's post-restore membership
assertion (bug c8ad0c21, iteration 4).

``list_projects`` is paginated (default ``page_size`` 20, stable name-sort).
On a live server with more than 20 registered projects, the check's
disposable project (``verify_trashrestore_<hex>``) can sort past the first
page. The check MUST filter server-side with ``name_contains`` (applied
before pagination) rather than scanning an unfiltered first page — otherwise
the assertion fails by construction regardless of whether the restore
actually worked. These tests stub the client entirely (no live server) and
pin: (1) the outgoing ``list_projects`` call always carries
``name_contains=<project_name>``; (2) a present, non-deleted, correctly
rooted row is accepted; (3) an absent row, a ``deleted=true`` row, and a
``root_path`` mismatch are all reported as FAILED with a distinguishing
reason.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _verify_client_all_commands_catalog import Status  # noqa: E402
from _verify_client_all_commands_fixtures import FixtureContext  # noqa: E402
from _verify_client_all_commands_lifecycle_project_trash_restore import (  # noqa: E402
    CHECK_NAME,
    run_project_trash_restore_roundtrip_check,
)

_PROJECT_ID = "34d2bde9-9606-43dc-ad32-2651abf5fbeb"
_SESSION_ID = "22222222-2222-2222-2222-222222222222"
_RESTORED_ROOT = "/var/casmgr/watch_catalog/x/verify_trashrestore_stub"
_FIXTURE_FILE_RELPATH = "restore_check.py"


class _StubFileSessions:
    """Records the seeded-upload call; never touches a real transport."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    async def upload_new(
        self, session_id: str, payload: bytes, project_id: str, file_path: str
    ) -> str:
        self.calls.append((session_id, payload, project_id, file_path))
        return "stub-file-id"


class _StubClient:
    """Minimal stand-in for ``CodeAnalysisAsyncClient`` used by this check.

    ``items_for_name`` builds the canned response for the *filtered*
    membership lookup (``name_contains=<captured project_name>``) once the
    real (randomly suffixed) project name is known — it is called with that
    name right after ``create_project``. Every other command returns a
    fixed, always-successful envelope. Every ``call_validated`` invocation
    is recorded so tests can assert on the exact params sent (the
    regression guard for bug c8ad0c21 iteration 4).
    """

    def __init__(
        self, items_for_name: Callable[[str], List[Dict[str, Any]]]
    ) -> None:
        self.file_sessions = _StubFileSessions()
        self.calls: List[Any] = []
        self._items_for_name = items_for_name
        self._list_projects_items: List[Dict[str, Any]] = []
        self._captured_project_name: Optional[str] = None

    async def call_validated(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.calls.append((command, dict(params)))

        if command == "create_project":
            self._captured_project_name = params["project_name"]
            self._list_projects_items = self._items_for_name(
                self._captured_project_name
            )
            return {"success": True, "data": {"project_id": _PROJECT_ID}}

        if command == "session_create":
            return {"success": True, "data": {"session_id": _SESSION_ID}}

        if command == "session_delete":
            return {"success": True, "data": {}}

        if command == "project_set_mark_del":
            return {"success": True, "data": {}}

        if command == "list_trashed_projects":
            return {
                "success": True,
                "data": {
                    "items": [
                        {
                            "original_name": self._captured_project_name,
                            "folder_name": f"{self._captured_project_name}_trashed",
                        }
                    ]
                },
            }

        if command == "restore_project_from_trash":
            return {"success": True, "data": {"root_path": _RESTORED_ROOT}}

        if command == "list_projects":
            # Regression pin for bug c8ad0c21 iteration 4: this MUST be a
            # server-side name filter, applied before pagination — never a
            # naive unfiltered/default-page call.
            assert params.get("name_contains") == self._captured_project_name, (
                "list_projects must be called with name_contains=<project_name> "
                f"(pagination-blind regression); got params={params!r}"
            )
            return {"success": True, "data": {"items": self._list_projects_items}}

        if command == "list_project_files":
            return {
                "success": True,
                "data": {"items": [{"relative_path": _FIXTURE_FILE_RELPATH}]},
            }

        if command == "permanently_delete_from_trash":
            return {"success": True, "data": {}}

        raise AssertionError(f"unexpected command in stub: {command!r}")


def _fixtures() -> FixtureContext:
    return FixtureContext(
        project_id="fixture-project-id",
        project_name="fixture-project",
        watch_dir_id=str(uuid.uuid4()),
        project_root="/var/casmgr/watch_catalog/x/fixture-project",
    )


@pytest.mark.asyncio
async def test_membership_check_passes_via_name_filter() -> None:
    """A present, non-deleted, correctly rooted row -> EXECUTED_OK."""
    client = _StubClient(
        items_for_name=lambda name: [
            {"id": _PROJECT_ID, "name": name, "root_path": name, "deleted": False}
        ]
    )

    outcomes = await run_project_trash_restore_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.EXECUTED_OK, outcome.reason
    assert "trashed and restored" in outcome.reason


@pytest.mark.asyncio
async def test_membership_check_fails_when_filtered_response_omits_project() -> None:
    """Filtered list_projects still missing the row -> a real defect, FAILED."""
    client = _StubClient(items_for_name=lambda name: [])  # project genuinely absent

    outcomes = await run_project_trash_restore_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "not present in list_projects(name_contains=" in outcome.reason


@pytest.mark.asyncio
async def test_membership_check_fails_when_row_still_marked_deleted() -> None:
    """Row present but deleted=true -> restore did not really clear it, FAILED."""
    client = _StubClient(
        items_for_name=lambda name: [
            {"id": _PROJECT_ID, "name": name, "root_path": name, "deleted": True}
        ]
    )

    outcomes = await run_project_trash_restore_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "still marked deleted=true" in outcome.reason


@pytest.mark.asyncio
async def test_membership_check_fails_on_root_path_mismatch() -> None:
    """Row present, not deleted, but root_path disagrees -> FAILED."""
    client = _StubClient(
        items_for_name=lambda name: [
            {
                "id": _PROJECT_ID,
                "name": name,
                "root_path": "some_other_folder_name",
                "deleted": False,
            }
        ]
    )

    outcomes = await run_project_trash_restore_roundtrip_check(client, _fixtures())

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "unexpected root_path" in outcome.reason
