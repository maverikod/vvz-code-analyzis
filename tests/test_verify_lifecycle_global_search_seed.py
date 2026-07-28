"""
Unit tests: global-search attribution check's throwaway-project seeder (bug 25c8d9dd wave-2).

The live ``create_project`` schema is ``{watch_dir_id, project_name, description}``
(all required, ``additionalProperties: false``) — the old seeder's ``{"name": ...}``
shape was never valid on the live server. A second latent mismatch was found while
fixing this: ``session_create`` only accepts ``comment`` (+ optional ``role_ids``),
also ``additionalProperties: false`` live; the old seeder passed ``project_id``,
which that schema rejects.

These tests stub the client entirely (no live server) and pin: (1) ``list_watch_dirs``
is resolved exactly once and its first row's ``id`` feeds ``watch_dir_id`` into both
``create_project`` calls; (2) ``create_project`` is invoked with
``watch_dir_id``/``project_name``/``description`` (never the old ``name`` key);
(3) ``session_create`` is invoked with only ``comment`` (never ``project_id``);
(4) a seed failure's underlying reason (e.g. the live server's ``create_project``
error) propagates verbatim through ``_seed_throwaway_project`` into the check's
FAILED outcome, never an opaque "seed step failed" with no detail.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

_LIVETESTS_DIR = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS_DIR))

from realsrv_test.core.catalog import Status  # noqa: E402
from realsrv_test.core.lifecycle_global_search import (  # noqa: E402
    CHECK_NAME,
    run_global_search_attribution_check,
)


class _StubFileSessions:
    """Records the seeded-upload calls; never touches a real transport."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    async def upload_new(
        self, session_id: str, payload: bytes, project_id: str, file_path: str
    ) -> str:
        self.calls.append((session_id, payload, project_id, file_path))
        return f"stub-file-id-{len(self.calls)}"


class _StubClient:
    """Minimal stand-in for ``CodeAnalysisAsyncClient`` used by this check.

    ``create_project_should_fail_for`` names labels (``"a"`` / ``"b"``) whose
    ``create_project`` call should return a server-side failure instead of
    succeeding, to exercise the reason-propagation path. Every
    ``call_validated`` invocation is recorded so tests can assert on the
    exact params sent — the regression guard for both schema mismatches this
    fix closes.
    """

    def __init__(
        self,
        *,
        watch_dirs: Optional[List[Dict[str, Any]]] = None,
        create_project_should_fail_for: Optional[set] = None,
    ) -> None:
        self.file_sessions = _StubFileSessions()
        self.calls: List[Any] = []
        self._watch_dirs = (
            watch_dirs
            if watch_dirs is not None
            else [{"id": "wd-1", "name": "watch", "absolute_path": "/watch"}]
        )
        self._create_project_should_fail_for = create_project_should_fail_for or set()
        self._project_ids: Dict[str, str] = {}
        self._project_counter = 0

    async def call_validated(
        self, command: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.calls.append((command, dict(params)))

        if command == "list_watch_dirs":
            return {
                "success": True,
                "data": {"watch_dirs": self._watch_dirs, "count": len(self._watch_dirs)},
            }

        if command == "create_project":
            # Regression pin: live create_project requires exactly these keys
            # (additionalProperties: false) — the old {"name": ...} shape 404s.
            assert set(params) == {
                "watch_dir_id",
                "project_name",
                "description",
                "create_venv",
                "apply_template",
            }, f"unexpected create_project params shape: {params!r}"
            label = params["project_name"].split("-")[3]
            if label in self._create_project_should_fail_for:
                return {"success": False, "error": f"boom-{label}"}
            self._project_counter += 1
            project_id = f"proj-{label}"
            self._project_ids[label] = project_id
            return {"success": True, "data": {"project_id": project_id}}

        if command == "session_create":
            # Regression pin: live session_create only accepts "comment" (+
            # optional role_ids), additionalProperties: false — the old
            # {"project_id": ...} shape 404s.
            assert set(params) == {"comment"}, (
                "session_create must be called with only 'comment' "
                f"(schema-mismatch regression); got {params!r}"
            )
            return {
                "success": True,
                "data": {"session_id": f"sess-{self._project_counter}"},
            }

        if command == "update_indexes":
            return {"success": True, "data": {}}

        if command == "search":
            if params.get("enable_grep"):
                return {"success": False, "error": "grep requires project_id"}
            items = [
                {"project_id": pid, "file_path": f"verify_global_{label}.py"}
                for label, pid in self._project_ids.items()
            ]
            return {"success": True, "data": {"items": items, "job_id": "job-1"}}

        if command == "search_close":
            return {"success": True, "data": {}}

        raise AssertionError(f"unexpected command in stub: {command!r}")


@pytest.mark.asyncio
async def test_seeds_with_correct_create_project_and_session_create_shapes() -> None:
    """Happy path: both throwaway projects seed and the global search finds both."""
    client = _StubClient()

    outcomes = await run_global_search_attribution_check(client, fixtures=None)

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.EXECUTED_OK, outcome.reason

    list_watch_dirs_calls = [c for c in client.calls if c[0] == "list_watch_dirs"]
    assert len(list_watch_dirs_calls) == 1, "watch_dir_id must be resolved once and reused"

    create_calls = [params for name, params in client.calls if name == "create_project"]
    assert len(create_calls) == 2
    for params in create_calls:
        assert params["watch_dir_id"] == "wd-1"
        assert params["project_name"].startswith("verify-global-search-")
        assert params["description"]

    session_calls = [params for name, params in client.calls if name == "session_create"]
    assert len(session_calls) == 2


@pytest.mark.asyncio
async def test_seed_failure_reason_propagates_verbatim_not_opaque() -> None:
    """create_project failing for project A surfaces the live error text, not just a stub label."""
    client = _StubClient(create_project_should_fail_for={"a"})

    outcomes = await run_global_search_attribution_check(client, fixtures=None)

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "boom-a" in outcome.reason
    assert "create_project:" in outcome.reason
    assert "throwaway project A" in outcome.reason


@pytest.mark.asyncio
async def test_fails_loud_when_no_watch_dirs_registered() -> None:
    """No watch dirs on the server -> FAILED with a named reason, never a silent skip."""
    client = _StubClient(watch_dirs=[])

    outcomes = await run_global_search_attribution_check(client, fixtures=None)

    outcome = outcomes[CHECK_NAME]
    assert outcome.status == Status.FAILED
    assert "watch_dir_id" in outcome.reason
    create_calls = [name for name, _ in client.calls if name == "create_project"]
    assert not create_calls, "must not attempt to seed projects without a watch_dir_id"
