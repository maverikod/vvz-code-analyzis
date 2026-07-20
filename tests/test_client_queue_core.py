"""
Tests for the single queue-aware core (_execute) that every client entry point
(``call``, ``call_validated``, ``call_unified*``, ``client.commands.*``) routes
through.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from code_analysis_client import (
    ClientValidationError,
    CommandFailedError,
    JobFailedError,
    JobTimeoutError,
    QueueJobError,
)
from code_analysis_client.client import CodeAnalysisAsyncClient

POLL_INTERVAL = 0.01


class FakeRpc:
    """Duck-typed stand-in for ``JsonRpcClient``: scripted ``execute_command`` responses."""

    def __init__(self, responses: List[Any]) -> None:
        """Store the queue of scripted responses/exceptions to hand back in order."""
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    async def execute_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        use_cmd_endpoint: bool = False,
    ) -> Dict[str, Any]:
        """Record the call and pop the next scripted response (or raise it)."""
        self.calls.append(
            {
                "command": command,
                "params": dict(params or {}),
                "use_cmd_endpoint": use_cmd_endpoint,
            }
        )
        if not self._responses:
            raise AssertionError(f"FakeRpc: no scripted response left for {command!r}")
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def make_client(fake_rpc: FakeRpc) -> CodeAnalysisAsyncClient:
    """Build a client without network I/O and swap in the fake rpc transport."""
    client = CodeAnalysisAsyncClient()
    client._rpc = fake_rpc  # type: ignore[attr-defined]  # __slots__ attribute, no network touched
    return client


# ---------------------------------------------------------------------------
# exception hierarchy: queued-job runtime errors must NOT be catchable via
# ClientValidationError (that would silently swallow runtime job failures in
# a handler written only for bad-parameter validation errors).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_type",
    [JobFailedError, JobTimeoutError, CommandFailedError],
)
def test_queue_job_errors_subclass_queue_job_error_not_client_validation_error(
    exc_type,
):
    assert issubclass(exc_type, QueueJobError)
    assert not issubclass(exc_type, ClientValidationError)


def test_queue_job_error_itself_is_not_a_client_validation_error():
    assert not issubclass(QueueJobError, ClientValidationError)
    assert issubclass(QueueJobError, RuntimeError)


# ---------------------------------------------------------------------------
# (a) sync result passes through untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_result_passes_through_untouched():
    resp = {"success": True, "data": {"foo": "bar"}}
    fake = FakeRpc([resp])
    client = make_client(fake)

    result = await client.call("some_cmd", {"x": 1})

    assert result == resp
    assert len(fake.calls) == 1
    assert fake.calls[0]["command"] == "some_cmd"


# ---------------------------------------------------------------------------
# (b) queued envelope (poll_with variant) -> pending, pending, completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queued_poll_with_variant_polls_to_completion():
    queued = {
        "success": True,
        "job_id": "j1",
        "status": "pending",
        "message": "queued",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    pending1 = {"success": True, "data": {"job_id": "j1", "status": "pending"}}
    pending2 = {"success": True, "data": {"job_id": "j1", "status": "running"}}
    completed = {
        "success": True,
        "data": {
            "job_id": "j1",
            "status": "completed",
            "result": {
                "command": "some_cmd",
                "result": {"success": True, "data": {"value": 42}},
                "status": "completed",
            },
            "job_success": True,
            "command_success": True,
        },
    }
    fake = FakeRpc([queued, pending1, pending2, completed])
    client = make_client(fake)

    result = await client.call("some_cmd", {"x": 1}, poll_interval=POLL_INTERVAL)

    assert result == {"success": True, "data": {"value": 42}}
    assert len(fake.calls) == 4
    for call in fake.calls[1:]:
        assert call["command"] == "queue_get_job_status"
        assert call["params"] == {"job_id": "j1"}


# ---------------------------------------------------------------------------
# (c) queued_after_timeout variant -> completed with inner success:false -> CommandFailedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queued_after_timeout_variant_inner_failure_raises_command_failed():
    queued = {
        "success": True,
        "job_id": "j2",
        "status": "pending",
        "queued_after_timeout": True,
    }
    completed_with_failure = {
        "success": True,
        "data": {
            "job_id": "j2",
            "status": "completed",
            "result": {
                "command": "broken_cmd",
                "result": {"success": False, "message": "boom"},
                "status": "completed",
            },
            "command_success": False,
        },
    }
    fake = FakeRpc([queued, completed_with_failure])
    client = make_client(fake)

    with pytest.raises(CommandFailedError) as excinfo:
        await client.call("broken_cmd", {}, poll_interval=POLL_INTERVAL)

    assert excinfo.value.job_id == "j2"
    assert excinfo.value.command == "broken_cmd"
    assert excinfo.value.error == {"success": False, "message": "boom"}


# ---------------------------------------------------------------------------
# (d) job failed -> JobFailedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_failed_status_raises_job_failed_error(monkeypatch):
    from code_analysis_client import queue_wait

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(queue_wait.asyncio, "sleep", fast_sleep)

    queued = {
        "success": True,
        "job_id": "j3",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    failed = {
        "success": True,
        "data": {"job_id": "j3", "status": "failed", "error": "exploded"},
    }
    # No structured inner error ever shows up (no `result` payload at all) —
    # all 4 refetch attempts also come back bare, so JobFailedError.error
    # falls back to the flat queue-level "error" string.
    fake = FakeRpc([queued, failed, failed, failed, failed, failed])
    client = make_client(fake)

    with pytest.raises(JobFailedError) as excinfo:
        await client.call("boom_cmd", {}, poll_interval=POLL_INTERVAL)

    assert excinfo.value.job_id == "j3"
    assert excinfo.value.error == "exploded"
    # queued response + initial status fetch + 4 exhausted refetch attempts
    assert len(fake.calls) == 6


# ---------------------------------------------------------------------------
# (d2) job failed with the command's own structured error already nested in
# the first terminal status response -> surfaced verbatim, no refetch needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_failed_with_nested_structured_error_surfaces_it():
    queued = {
        "success": True,
        "job_id": "j7",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    failed = {
        "success": True,
        "data": {
            "job_id": "j7",
            "status": "failed",
            "result": {
                "command": "git_init",
                "result": {
                    "success": False,
                    "error": {"code": "PATH_ESCAPES_ROOT", "message": "nope"},
                },
                "status": "failed",
            },
        },
    }
    fake = FakeRpc([queued, failed])
    client = make_client(fake)

    with pytest.raises(JobFailedError) as excinfo:
        await client.call("git_init", {}, poll_interval=POLL_INTERVAL)

    assert excinfo.value.job_id == "j7"
    assert excinfo.value.error == {"code": "PATH_ESCAPES_ROOT", "message": "nope"}
    # queued response + the single status fetch; no refetch was needed.
    assert len(fake.calls) == 2


# ---------------------------------------------------------------------------
# (d3) status-before-result write-order race: the status turns "failed"
# before the result payload lands; unwrap_job_result re-fetches until the
# structured inner error shows up.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_failed_status_before_result_race_retries_until_surfaced(
    monkeypatch,
):
    from code_analysis_client import queue_wait

    async def fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(queue_wait.asyncio, "sleep", fast_sleep)

    queued = {
        "success": True,
        "job_id": "j8",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    # wait_for_job's own poll observes the terminal "failed" status, but the
    # result payload has not landed in the store yet.
    failed_no_result = {
        "success": True,
        "data": {"job_id": "j8", "status": "failed"},
    }
    # First refetch attempt: still no result.
    still_no_result = {
        "success": True,
        "data": {"job_id": "j8", "status": "failed"},
    }
    # Second refetch attempt: the structured inner error has finally landed.
    failed_with_result = {
        "success": True,
        "data": {
            "job_id": "j8",
            "status": "failed",
            "result": {
                "command": "git_init",
                "result": {
                    "success": False,
                    "error": {"code": "PATH_ESCAPES_ROOT", "message": "late"},
                },
                "status": "failed",
            },
        },
    }
    fake = FakeRpc([queued, failed_no_result, still_no_result, failed_with_result])
    client = make_client(fake)

    with pytest.raises(JobFailedError) as excinfo:
        await client.call("git_init", {}, poll_interval=POLL_INTERVAL)

    assert excinfo.value.job_id == "j8"
    assert excinfo.value.error == {"code": "PATH_ESCAPES_ROOT", "message": "late"}
    # queued + wait_for_job's status fetch + 2 refetch attempts
    assert len(fake.calls) == 4


# ---------------------------------------------------------------------------
# (e) timeout=0.05 with never-terminal job -> JobTimeoutError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_exceeded_raises_job_timeout_error():
    queued = {
        "success": True,
        "job_id": "j4",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    pending_forever = {"success": True, "data": {"job_id": "j4", "status": "running"}}
    # Plenty of scripted polls; the timeout must fire well before they run out.
    fake = FakeRpc([queued] + [pending_forever] * 50)
    client = make_client(fake)

    with pytest.raises(JobTimeoutError) as excinfo:
        await client.call("slow_cmd", {}, timeout=0.05, poll_interval=POLL_INTERVAL)

    assert excinfo.value.job_id == "j4"


# ---------------------------------------------------------------------------
# (f) search-like response with job_id PLUS payload keys is NOT treated as queued
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_like_response_with_job_id_is_not_queued():
    search_resp = {
        "success": True,
        "job_id": "sj1",
        "items": ["a", "b"],
        "has_more": True,
    }
    fake = FakeRpc([search_resp])
    client = make_client(fake)

    result = await client.call("search", {"query": "x"})

    assert result == search_resp
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# (g) client.commands.<name>(...) goes through the core and unwraps a queued result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commands_proxy_routes_through_core_and_unwraps():
    queued = {
        "success": True,
        "job_id": "j5",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    completed = {
        "success": True,
        "data": {
            "job_id": "j5",
            "status": "completed",
            "result": {
                "command": "my_cmd",
                "result": {"success": True, "data": {"ok": True}},
                "status": "completed",
            },
            "command_success": True,
        },
    }
    fake = FakeRpc([queued, completed])
    client = make_client(fake)
    # Stub schema lookup (skip network `help` round trip).
    client._command_schema_cache["my_cmd"] = {  # type: ignore[attr-defined]
        "type": "object",
        "properties": {"foo": {"type": "string"}},
        "additionalProperties": False,
    }

    result = await client.commands.my_cmd(foo="bar")

    assert result == {"success": True, "data": {"ok": True}}
    assert fake.calls[0]["command"] == "my_cmd"
    assert fake.calls[0]["params"] == {"foo": "bar"}


# ---------------------------------------------------------------------------
# (h) status_hook receives each poll status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_hook_receives_each_poll():
    queued = {
        "success": True,
        "job_id": "j6",
        "status": "pending",
        "store": "queuemgr",
        "poll_with": "queue_get_job_status",
    }
    pending = {"success": True, "data": {"job_id": "j6", "status": "pending"}}
    completed = {
        "success": True,
        "data": {
            "job_id": "j6",
            "status": "completed",
            "result": {
                "command": "hooked_cmd",
                "result": {"ok": True},
                "status": "completed",
            },
            "command_success": True,
        },
    }
    fake = FakeRpc([queued, pending, completed])
    client = make_client(fake)

    seen: List[Dict[str, Any]] = []

    def hook(data: Dict[str, Any]) -> None:
        seen.append(data)

    result = await client.call(
        "hooked_cmd", {}, poll_interval=POLL_INTERVAL, status_hook=hook
    )

    assert result == {"ok": True}
    assert len(seen) == 2
    assert seen[0]["status"] == "pending"
    assert seen[1]["status"] == "completed"


# ---------------------------------------------------------------------------
# (i) queue_get_job_status itself, called via `call`, does not recurse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queue_get_job_status_call_does_not_recurse():
    # A direct status response has data-payload keys (status inside `data`, not
    # at top level) -> the top-level envelope must NOT be mistaken for queued.
    status_resp = {
        "success": True,
        "data": {
            "job_id": "jX",
            "status": "completed",
            "result": {
                "command": "queue_get_job_status",
                "result": {},
                "status": "completed",
            },
            "command_success": True,
        },
    }
    fake = FakeRpc([status_resp])
    client = make_client(fake)

    result = await client.call("queue_get_job_status", {"job_id": "jX"})

    assert result == status_resp
    assert len(fake.calls) == 1
