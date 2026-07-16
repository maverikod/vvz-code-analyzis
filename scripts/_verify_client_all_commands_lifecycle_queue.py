"""
Queue/adapter background-job lifecycle for the live-server all-commands verifier.

Two independent job registries are exercised:

* ``long_task`` — a builtin demo job (``mcp_proxy_adapter.core.job_manager``);
  it returns its own ``job_id`` synchronously, then ``job_status`` polls it.
* ``queue_add_job`` / ``queue_get_job_status`` / ``queue_get_job_logs`` /
  ``queue_stop_job`` / ``queue_delete_job`` — the ``QueueManager``-backed
  background queue, keyed by a client-chosen ``job_id``. A short sleep gives
  the one-second ``long_running`` demo job time to finish before ``queue_stop_job``
  is attempted; a real "already completed" rejection there is still a genuine
  invocation, not a skip.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome
from _verify_client_all_commands_fixtures import FixtureContext
from _verify_client_all_commands_lifecycle_common import (
    call_step,
    call_step_with_data,
    skip_outcome,
)


async def run_queue_lifecycle(
    client: CodeAnalysisAsyncClient, fixtures: FixtureContext
) -> Dict[str, CommandOutcome]:
    """Run the ``long_task``/``job_status`` pair and the queue-job lifecycle.

    Args:
        client: Connected async client.
        fixtures: The disposable project/session fixture for this run (unused
            here; every step in this lifecycle is project-independent).

    Returns:
        Mapping of every command name this lifecycle covers to its outcome.
    """
    _ = fixtures
    outcomes: Dict[str, CommandOutcome] = {}

    long_task_outcome, long_task_data = await call_step_with_data(
        client,
        "long_task",
        {"seconds": 1},
        bucket=Bucket.ADAPTER,
        ok_reason="demo long-running job enqueued",
    )
    outcomes["long_task"] = long_task_outcome
    long_task_job_id = str((long_task_data or {}).get("job_id") or "").strip()
    if long_task_job_id:
        outcomes["job_status"] = await call_step(
            client,
            "job_status",
            {"job_id": long_task_job_id},
            bucket=Bucket.ADAPTER,
        )
    else:
        outcomes["job_status"] = skip_outcome(
            "job_status",
            "skipped: long_task did not return a job_id",
            status=long_task_outcome.status,
        )

    queue_job_id = f"verify-sweep-{uuid.uuid4().hex[:12]}"
    outcomes["queue_add_job"] = await call_step(
        client,
        "queue_add_job",
        {
            "job_type": "long_running",
            "job_id": queue_job_id,
            "params": {"duration": 1, "task_type": "verify_sweep"},
        },
        bucket=Bucket.ADAPTER,
        ok_reason="background queue job enqueued",
    )
    outcomes["queue_get_job_status"] = await call_step(
        client, "queue_get_job_status", {"job_id": queue_job_id}, bucket=Bucket.ADAPTER
    )
    outcomes["queue_get_job_logs"] = await call_step(
        client, "queue_get_job_logs", {"job_id": queue_job_id}, bucket=Bucket.ADAPTER
    )

    # Let the 1-second job finish so stop/delete see a real terminal state
    # rather than racing the job runner.
    await asyncio.sleep(1.5)

    outcomes["queue_stop_job"] = await call_step(
        client,
        "queue_stop_job",
        {"job_id": queue_job_id},
        bucket=Bucket.ADAPTER,
        ok_reason="job stopped (or already completed)",
    )
    outcomes["queue_delete_job"] = await call_step(
        client,
        "queue_delete_job",
        {"job_id": queue_job_id},
        bucket=Bucket.ADAPTER,
        ok_reason="job deleted at lifecycle teardown",
    )
    return outcomes
