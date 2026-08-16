"""
Unit tests: the shared disposable-project purge helper (bug d5835fbf).

Stubs the client entirely (no live server) and pins the trash-folder
resolution strategy documented in
``realsrv_test.core.disposable_project.purge_disposable_project``: a
before/after ``list_trashed_projects`` diff resolves the folder this call's
own ``project_set_mark_del`` created, independent of what name the project
carried at deletion time (the rename-proof fix for bug d5835fbf); a
same-``original_name`` match is only a fallback for cases the diff can't
settle on its own. Also pins: already-absent idempotence still attempts a
trash purge, a hard mark_del failure never even looks at trash, and the
helper never raises regardless of what any downstream call does.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.core.disposable_project import (  # noqa: E402
    purge_disposable_project,
)

_PROJECT_ID = "34d2bde9-9606-43dc-ad32-2651abf5fbeb"


class _StubClient:
    """Minimal stand-in for ``CodeAnalysisAsyncClient``.

    ``list_trash_pages`` is consumed one page per ``list_trashed_projects``
    call (first call = "before" snapshot, second = "after"); once exhausted,
    the last page is repeated. ``mark_del_result`` controls the
    ``project_set_mark_del`` response: a callable is invoked (may raise or
    return a response dict), anything else is returned verbatim wrapped as
    ``{"success": True, "data": mark_del_result}``.
    """

    def __init__(
        self,
        *,
        list_trash_pages: List[List[Dict[str, Any]]],
        mark_del_result: Any = None,
        purge_result: Dict[str, Any] | None = None,
    ) -> None:
        self.list_trash_pages = list_trash_pages
        self._list_trash_call_count = 0
        self.mark_del_result = mark_del_result
        self.purge_result = purge_result or {"success": True, "data": {}}
        self.calls: List[Any] = []

    async def call_validated(self, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append((command, dict(params)))

        if command == "list_trashed_projects":
            idx = min(self._list_trash_call_count, len(self.list_trash_pages) - 1)
            items = self.list_trash_pages[idx] if self.list_trash_pages else []
            self._list_trash_call_count += 1
            return {"success": True, "data": {"items": items}}

        if command == "project_set_mark_del":
            if callable(self.mark_del_result):
                return self.mark_del_result(params)
            return {"success": True, "data": self.mark_del_result or {}}

        if command == "permanently_delete_from_trash":
            return self.purge_result

        raise AssertionError(f"unexpected command in stub: {command!r}")


def _purge_calls(client: _StubClient) -> List[Dict[str, Any]]:
    return [params for name, params in client.calls if name == "permanently_delete_from_trash"]


@pytest.mark.asyncio
async def test_purge_resolves_via_before_after_diff_regardless_of_name() -> None:
    """Exactly one new trash folder appears -> resolved by diff, no name needed.

    This is the rename-proof case: ``project_name`` is intentionally
    ``None`` here (mirrors lifecycle_project_lock.py renaming the shared
    fixture project away from its creation-time name mid-sweep) and the
    diff alone still finds the right folder.
    """
    before = [{"folder_name": "unrelated_old_2020-01-01T00-00-00Z", "original_name": "unrelated_old", "deleted_at": "2020-01-01T00-00-00Z"}]
    after = before + [
        {
            "folder_name": "verify_lock_original_deadbeef_2026-08-15T10-00-00Z",
            "original_name": "verify_lock_original_deadbeef",
            "deleted_at": "2026-08-15T10-00-00Z",
        }
    ]
    client = _StubClient(list_trash_pages=[before, after])

    result = await purge_disposable_project(client, _PROJECT_ID, None)

    assert result.startswith("purged (diff):"), result
    assert _purge_calls(client) == [
        {"trash_folder_name": "verify_lock_original_deadbeef_2026-08-15T10-00-00Z"}
    ]


@pytest.mark.asyncio
async def test_purge_falls_back_to_name_match_when_before_snapshot_unavailable() -> None:
    """Before-lookup itself fails -> diff can't be computed, name fallback resolves it."""

    class _FlakyBeforeClient(_StubClient):
        async def call_validated(self, command, params):
            if command == "list_trashed_projects" and self._list_trash_call_count == 0:
                self._list_trash_call_count += 1
                raise RuntimeError("transient network error")
            return await super().call_validated(command, params)

    after = [
        {
            "folder_name": "my_project_2026-08-15T10-00-00Z",
            "original_name": "my_project",
            "deleted_at": "2026-08-15T10-00-00Z",
        }
    ]
    client = _FlakyBeforeClient(list_trash_pages=[after])

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert result.startswith("purged (name-fallback):"), result
    assert _purge_calls(client) == [{"trash_folder_name": "my_project_2026-08-15T10-00-00Z"}]


@pytest.mark.asyncio
async def test_purge_reports_not_found_without_raising_when_nothing_matches() -> None:
    """No diff, no name match -> a descriptive non-raising outcome, no purge call."""
    same_page = [
        {
            "folder_name": "someone_elses_project_2026-08-15T10-00-00Z",
            "original_name": "someone_elses_project",
            "deleted_at": "2026-08-15T10-00-00Z",
        }
    ]
    client = _StubClient(list_trash_pages=[same_page, same_page])

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert "trash-entry-not-found" in result
    assert _purge_calls(client) == []


@pytest.mark.asyncio
async def test_purge_already_absent_still_attempts_trash_purge() -> None:
    """mark_del rejects with 'not found in database' -> treated as OK, trash purge still tried."""

    def _already_absent(_params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "Project not found in database: x"}

    # mark_del is already-absent (this call didn't itself trash anything new),
    # so before/after are identical -- the diff is empty and resolution must
    # fall back to a same-name match against the entry an EARLIER call already
    # trashed.
    already_trashed = [
        {
            "folder_name": "my_project_2026-08-15T10-00-00Z",
            "original_name": "my_project",
            "deleted_at": "2026-08-15T10-00-00Z",
        }
    ]
    client = _StubClient(
        list_trash_pages=[already_trashed, already_trashed],
        mark_del_result=_already_absent,
    )

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert result.startswith("purged (name-fallback):"), result
    assert _purge_calls(client) == [{"trash_folder_name": "my_project_2026-08-15T10-00-00Z"}]


@pytest.mark.asyncio
async def test_purge_hard_mark_del_failure_never_touches_trash() -> None:
    """A real (non-already-absent) mark_del failure aborts before any trash lookup."""

    def _hard_failure(_params: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "DATABASE_ERROR: connection refused"}

    client = _StubClient(list_trash_pages=[[]], mark_del_result=_hard_failure)

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert result.startswith("mark_del-failed:"), result
    # Only the "before" list_trashed_projects call happened -- no "after" lookup,
    # no purge call.
    list_trash_calls = [c for c in client.calls if c[0] == "list_trashed_projects"]
    assert len(list_trash_calls) == 1
    assert _purge_calls(client) == []


@pytest.mark.asyncio
async def test_purge_mark_del_raise_never_propagates() -> None:
    """An exception from project_set_mark_del itself is caught, not re-raised."""

    class _RaisingClient(_StubClient):
        async def call_validated(self, command, params):
            if command == "project_set_mark_del":
                self.calls.append((command, dict(params)))
                raise RuntimeError("connection reset")
            return await super().call_validated(command, params)

    client = _RaisingClient(list_trash_pages=[[]])

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert result.startswith("mark_del-raised:"), result
    assert _purge_calls(client) == []


@pytest.mark.asyncio
async def test_purge_never_raises_when_permanently_delete_fails() -> None:
    """A resolvable folder but a failing purge call -> reported, not raised."""
    before: List[Dict[str, Any]] = []
    after = [
        {
            "folder_name": "my_project_2026-08-15T10-00-00Z",
            "original_name": "my_project",
            "deleted_at": "2026-08-15T10-00-00Z",
        }
    ]
    client = _StubClient(
        list_trash_pages=[before, after],
        purge_result={"success": False, "error": "PERMISSION_DENIED"},
    )

    result = await purge_disposable_project(client, _PROJECT_ID, "my_project")

    assert result.startswith("purge-failed"), result
