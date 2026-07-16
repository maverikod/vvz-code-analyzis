"""
Worker/pip command lifecycle for the live-server all-commands verifier.

``project_pip_install`` runs as a queued background job: the dispatch
response reports ``job_id``/``status`` at the top level of the envelope
(sibling to ``success``, not nested under ``data``), and ``success: true``
there only means the job was enqueued, not that the venv exists yet.
``project_pip_check`` / ``_list`` / ``_search`` / ``_show`` / ``_uninstall``
and ``run_project_module`` all need that venv, so this lifecycle polls the
generic adapter ``queue_get_job_status`` for the pip job's own ``job_id``
(bounded wait) and only runs the venv-dependent commands after the job
reaches ``status: completed``. ``project_pip_uninstall`` runs last since it
removes the package the other commands just inspected.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Tuple

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import call_step

_PACKAGES = ["pip"]
_PIP_JOB_WAIT_TIMEOUT_SECONDS = 60.0
_PIP_JOB_WAIT_INTERVAL_SECONDS = 2.0


async def _describe_pip_job_failure(
    client: CodeAnalysisAsyncClient, job_id: str, data: Dict[str, Any]
) -> str:
    """Build a detailed failure reason for a terminally-failed pip install job.

    ``queue_get_job_status``'s top-level ``error`` field is only populated
    when the queued job itself raised (e.g. a worker crash); a command that
    legitimately returned an error result (venv creation refused, pip exiting
    non-zero, ...) shows up instead nested under ``data["result"]["result"]``
    (the command-execution envelope), or only in the subprocess's stderr. This
    inspects both, then calls ``queue_get_job_logs`` for a stderr tail so a
    genuine "no venv, cannot create one" rejection is recorded verbatim rather
    than as the uninformative ``job failed: None``.

    Args:
        client: Connected async client.
        job_id: The failed pip-install job's id.
        data: The ``queue_get_job_status`` response ``data`` payload observed
            at the moment ``status`` was seen as ``"failed"``.

    Returns:
        Human-readable failure detail combining whatever the job-status
        response carries with a stderr tail fetched via ``queue_get_job_logs``;
        never empty.
    """
    parts = []
    top_error = data.get("error")
    if top_error:
        parts.append(f"error={truncate(str(top_error))}")
    result = data.get("result")
    if isinstance(result, dict):
        inner = result.get("result")
        if isinstance(inner, dict):
            inner_error = inner.get("error") or inner.get("message")
            if inner_error:
                parts.append(f"result.error={truncate(str(inner_error))}")
            inner_data = inner.get("data")
            if isinstance(inner_data, dict):
                stderr = inner_data.get("stderr")
                if stderr:
                    parts.append(f"stderr={truncate(str(stderr), 400)}")
        elif result:
            parts.append(f"result={truncate(str(result))}")
    try:
        logs_resp = await client.call_validated(
            "queue_get_job_logs", {"job_id": job_id}
        )
    except Exception as exc:  # noqa: BLE001 - best-effort diagnostics only
        parts.append(f"queue_get_job_logs raised: {truncate(repr(exc))}")
    else:
        if logs_resp.get("success") is True:
            logs_data: Dict[str, Any] = logs_resp.get("data") or {}
            stderr_tail = str(logs_data.get("stderr") or "").strip()
            if stderr_tail:
                parts.append(f"job_logs.stderr={truncate(stderr_tail, 400)}")
        else:
            parts.append(
                f"queue_get_job_logs failed: {truncate(str(logs_resp.get('error')))}"
            )
    if not parts:
        parts.append("no failure detail available in job status or logs")
    return "; ".join(parts)


async def _wait_for_pip_job(
    client: CodeAnalysisAsyncClient, job_id: str
) -> Tuple[bool, str]:
    """Poll ``queue_get_job_status`` until the pip install job reaches a terminal state.

    Not credited to the ``queue_get_job_status`` outcome slot — that command
    name is already exercised (with its own job) by
    ``_verify_client_all_commands_lifecycle_queue.run_queue_lifecycle``; this
    is purely an internal wait.

    Args:
        client: Connected async client.
        job_id: The ``job_id`` returned at the top level of the
            ``project_pip_install`` dispatch response.

    Returns:
        Tuple of (completed, note) — ``completed`` is True only if the job
        reached ``status: completed`` within the bounded wait; ``note``
        explains the last observed status/error either way.
    """
    deadline = time.monotonic() + _PIP_JOB_WAIT_TIMEOUT_SECONDS
    last_note = "queue_get_job_status never returned success"
    while time.monotonic() < deadline:
        try:
            resp = await client.call_validated(
                "queue_get_job_status", {"job_id": job_id}
            )
        except Exception as exc:  # noqa: BLE001 - keep polling until the deadline
            last_note = truncate(repr(exc))
        else:
            if resp.get("success") is True:
                data: Dict[str, Any] = resp.get("data") or {}
                status = str(data.get("status") or "").lower()
                if status == "completed":
                    return True, status
                if status == "failed":
                    detail = await _describe_pip_job_failure(client, job_id, data)
                    return False, f"job failed: {detail}"
                last_note = f"status={status!r}"
            else:
                last_note = truncate(str(resp.get("error")))
        await asyncio.sleep(_PIP_JOB_WAIT_INTERVAL_SECONDS)
    return False, f"timed out waiting for pip install job {job_id} (last: {last_note})"


async def run_worker_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run start/stop worker, pause/resume, run_project_module, and pip commands.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    outcomes: Dict[str, CommandOutcome] = {}
    project_id = fixtures.project_id

    outcomes["start_worker"] = await call_step(
        client,
        "start_worker",
        {"worker_type": "file_watcher", "project_id": project_id},
        ok_reason="file_watcher worker started for the disposable project",
    )
    outcomes["stop_worker"] = await call_step(
        client,
        "stop_worker",
        {"worker_type": "file_watcher"},
        ok_reason="file_watcher worker stopped",
    )

    await call_step(
        client,
        "set_project_processing_paused",
        {"project_id": project_id, "processing_paused": True},
    )
    outcomes["set_project_processing_paused"] = await call_step(
        client,
        "set_project_processing_paused",
        {"project_id": project_id, "processing_paused": False},
        ok_reason="processing paused then resumed for the disposable project",
    )

    # project_pip_install only enqueues the venv-bootstrap job; job_id/status
    # come back at the top level of the response, not under `data`.
    try:
        install_resp = await client.call_validated(
            "project_pip_install", {"project_id": project_id, "packages": _PACKAGES}
        )
    except Exception as exc:  # noqa: BLE001 - one bad step must not abort the sweep
        install_outcome = CommandOutcome(
            "project_pip_install", Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc))
        )
        install_resp = {}
    else:
        if install_resp.get("success") is True:
            install_outcome = CommandOutcome(
                "project_pip_install",
                Bucket.BUCKET_A,
                Status.EXECUTED_OK,
                "venv bootstrap job enqueued for the disposable project",
            )
        else:
            install_outcome = CommandOutcome(
                "project_pip_install",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                truncate(str(install_resp.get("error"))),
            )

    venv_ready = False
    if install_outcome.status is Status.EXECUTED_OK:
        job_id = str(install_resp.get("job_id") or "").strip()
        if job_id:
            venv_ready, wait_note = await _wait_for_pip_job(client, job_id)
            if not venv_ready:
                install_outcome = CommandOutcome(
                    "project_pip_install",
                    Bucket.BUCKET_A,
                    Status.EXPECTED_ERROR,
                    f"enqueued but did not complete: {wait_note}",
                )
        else:
            install_outcome = CommandOutcome(
                "project_pip_install",
                Bucket.BUCKET_A,
                Status.FAILED,
                "enqueue reported success but the response had no top-level job_id",
            )
    outcomes["project_pip_install"] = install_outcome

    if venv_ready:
        outcomes["run_project_module"] = await call_step(
            client,
            "run_project_module",
            {"project_id": project_id, "module": fixtures.module_name},
            ok_reason=f"ran python -m {fixtures.module_name} against the seeded fixture file",
        )
        outcomes["project_pip_check"] = await call_step(
            client,
            "project_pip_check",
            {"project_id": project_id, "packages": _PACKAGES},
        )
        outcomes["project_pip_list"] = await call_step(
            client, "project_pip_list", {"project_id": project_id}
        )
        outcomes["project_pip_search"] = await call_step(
            client, "project_pip_search", {"project_id": project_id, "query": "pip"}
        )
        outcomes["project_pip_show"] = await call_step(
            client,
            "project_pip_show",
            {"project_id": project_id, "packages": _PACKAGES},
        )
        outcomes["project_pip_uninstall"] = await call_step(
            client,
            "project_pip_uninstall",
            {"project_id": project_id, "packages": _PACKAGES},
            ok_reason="package uninstalled at lifecycle teardown",
        )
    else:
        skip_status = (
            install_outcome.status
            if install_outcome.status is not Status.EXECUTED_OK
            else Status.EXPECTED_ERROR
        )
        reason = (
            "skipped: project_pip_install job did not reach status=completed "
            "(no venv confirmed ready)"
        )
        for name in (
            "run_project_module",
            "project_pip_check",
            "project_pip_list",
            "project_pip_search",
            "project_pip_show",
            "project_pip_uninstall",
        ):
            outcomes[name] = CommandOutcome(name, Bucket.BUCKET_A, skip_status, reason)
    return outcomes
