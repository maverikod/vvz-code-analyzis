"""
Queue-aware polling core: detect queued-job envelopes, poll them to completion,
and unwrap the inner command result.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from code_analysis_client.exceptions import (
    CommandFailedError,
    JobFailedError,
    JobTimeoutError,
)

# Keys a pure queue-service envelope may carry. A response whose keys are NOT a
# subset of this set carries real payload data alongside job_id/status and must
# never be mistaken for a queued placeholder (e.g. `search`, which returns both
# `job_id` for pagination and actual result items).
_SERVICE_ENVELOPE_KEYS = {
    "success",
    "job_id",
    "jobId",
    "status",
    "message",
    "store",
    "poll_with",
    "queued_after_timeout",
    "data",
}

_QUEUED_STATUSES = {"pending", "queued", "running"}
_TERMINAL_STATUSES = {"completed", "failed", "stopped", "cancelled"}
_FAILED_JOB_STATUSES = {"failed", "stopped", "cancelled"}

StatusHook = Callable[[Dict[str, Any]], Union[Any, Awaitable[Any]]]


def is_queued_envelope(resp: Dict[str, Any]) -> bool:
    """Return True when ``resp`` is a queue-service envelope (either deployed variant).

    Detection rule: a ``job_id``/``jobId`` is present (top level or under
    ``data``) AND one of:
      * ``poll_with == "queue_get_job_status"``
      * ``store == "queuemgr"``
      * ``queued_after_timeout`` is truthy
      * ``status`` is one of pending/queued/running AND the envelope's own keys
        are a subset of the known queue-service key set (this subset guard is
        what prevents false positives on commands like ``search`` whose
        legitimate result also carries a ``job_id`` plus real payload keys).
    """
    if not isinstance(resp, dict):
        return False

    job_id = resp.get("job_id") or resp.get("jobId")
    if not job_id:
        data = resp.get("data")
        if isinstance(data, dict):
            job_id = data.get("job_id") or data.get("jobId")
    if not job_id:
        return False

    if resp.get("poll_with") == "queue_get_job_status":
        return True
    if resp.get("store") == "queuemgr":
        return True
    if resp.get("queued_after_timeout"):
        return True

    status = resp.get("status")
    if status in _QUEUED_STATUSES and set(resp.keys()) <= _SERVICE_ENVELOPE_KEYS:
        return True

    return False


def _extract_job_id(resp: Dict[str, Any]) -> str:
    """Pull the job identifier out of a queued envelope (top level or under data)."""
    job_id = resp.get("job_id") or resp.get("jobId")
    if not job_id:
        data = resp.get("data")
        if isinstance(data, dict):
            job_id = data.get("job_id") or data.get("jobId")
    return str(job_id)


async def _call_status_hook(
    status_hook: Optional[StatusHook], data: Dict[str, Any]
) -> None:
    """Invoke ``status_hook`` with ``data``, awaiting it when it returns a coroutine."""
    if status_hook is None:
        return
    maybe = status_hook(data)
    if inspect.isawaitable(maybe):
        await maybe


async def wait_for_job(
    rpc: Any,
    job_id: str,
    *,
    timeout: Optional[float] = None,
    poll_interval: float = 1.0,
    status_hook: Optional[StatusHook] = None,
) -> Dict[str, Any]:
    """Poll ``queue_get_job_status`` via the raw adapter ``rpc`` until the job is terminal.

    Uses ``rpc.execute_command`` directly (never the queue-aware core) to avoid
    recursing back into job polling. ``timeout=None`` (default) polls until the
    job reaches a terminal state, per the user's requirement. If ``timeout`` is
    set and exceeded, raises :class:`JobTimeoutError` — the job keeps running
    server-side.
    """
    start = time.monotonic() if timeout is not None else None
    while True:
        resp = await rpc.execute_command("queue_get_job_status", {"job_id": job_id})
        data = resp.get("data") if isinstance(resp, dict) else None
        if not isinstance(data, dict):
            data = resp if isinstance(resp, dict) else {}

        await _call_status_hook(status_hook, data)

        status = str(data.get("status", "")).strip().lower()
        if status in _TERMINAL_STATUSES:
            return data

        if timeout is not None and start is not None:
            if (time.monotonic() - start) >= timeout:
                raise JobTimeoutError(job_id, timeout)

        await asyncio.sleep(poll_interval)


def unwrap_job_result(status_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the inner command result from a terminal job status ``data`` dict.

    Raises :class:`JobFailedError` when the job itself failed/stopped/cancelled
    or reported ``error``. Raises :class:`CommandFailedError` when the job
    completed but the inner command result is itself an error envelope.
    Otherwise returns the inner result dict, in the same shape a sync call
    would have returned.
    """
    job_id = status_data.get("job_id")
    status = str(status_data.get("status", "")).strip().lower()
    error = status_data.get("error")

    if status in _FAILED_JOB_STATUSES or error:
        raise JobFailedError(job_id, error, status=status)

    result_field = status_data.get("result")
    if isinstance(result_field, dict) and "result" in result_field:
        inner = result_field["result"]
    else:
        inner = result_field

    inner_looks_failed = isinstance(inner, dict) and inner.get("success") is False
    command_success_false = status_data.get("command_success") is False
    completed_with_error = bool(status_data.get("completed_with_error")) or bool(
        status_data.get("native_completed_with_error")
    )

    if inner_looks_failed or command_success_false or completed_with_error:
        command = (
            result_field.get("command") if isinstance(result_field, dict) else None
        )
        raise CommandFailedError(command, job_id, inner)

    return inner if isinstance(inner, dict) else {"result": inner}
