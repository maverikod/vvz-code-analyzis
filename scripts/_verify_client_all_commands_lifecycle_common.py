"""
Shared call/skip helpers for the ordered command lifecycles.

Each ``_verify_client_all_commands_lifecycle_*`` module builds one ordered flow
of interdependent commands (session, transfer, search, git, github, entities,
fs, workers, queue) and returns a ``{command_name: CommandOutcome}`` mapping
consumed by ``_verify_client_all_commands_lifecycles.run_lifecycles``. This
module holds the two small helpers every lifecycle module uses to call one
step and to record a step skipped because an earlier dependency failed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient, JobFailedError

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate
from _verify_client_all_commands_classifiers import classify_job_failed_error


async def call_step_with_data(
    client: CodeAnalysisAsyncClient,
    name: str,
    params: Dict[str, Any],
    *,
    bucket: Bucket = Bucket.BUCKET_A,
    ok_reason: str = "executed as part of an ordered lifecycle",
) -> Tuple[CommandOutcome, Optional[Dict[str, Any]]]:
    """Call one lifecycle step and return its outcome plus the response data.

    Never raises: any transport/validation exception is captured as a
    :attr:`Status.FAILED` outcome so one broken step cannot abort the rest of
    its lifecycle or the overall sweep.

    A raised :class:`JobFailedError` gets its own branch, routed through
    :func:`_verify_client_all_commands_classifiers.classify_job_failed_error`
    instead of the generic handler below. Root cause this branch fixes
    (verified empirically against live run logs for ``git_branch_set_upstream``
    / ``git_branch_track_remote``, jobs ``4914da2b-16dc-4c24-843f-7a6a2656b098``
    / ``af6947cd-1fa7-4233-abf9-430ae3249789``): before this fix, the generic
    ``except Exception`` below caught ``JobFailedError`` too and reported it
    verbatim (``FAILED ... JobFailedError(...: None)``), so the structured
    inner-error lookup in ``classify_job_failed_error`` /
    ``_fetch_structured_job_error`` — the retry loop that DOES successfully
    reclassify the same kind of failure for every Bucket-A command that goes
    through ``run_bucket_a`` instead of a lifecycle step — was never even
    called for lifecycle-precomputed commands. It was never a timing/race
    problem with the retry loop itself (the retries were never reached), and
    ``exc.job_id`` was never actually ``None`` (the two job ids above prove
    it) — the ``None`` in the FAILED reason is ``JobFailedError.error``,
    logged verbatim because nothing ever fetched the real nested error at
    ``data.result.result.error``.

    Args:
        client: Connected async client.
        name: Live command name to invoke.
        params: Params to pass to ``call_validated``.
        bucket: Classification bucket to attach to the outcome.
        ok_reason: Reason text used when the call reports success.

    Returns:
        Tuple of (outcome, response ``data`` dict or ``None`` when the call
        failed or returned no dict-shaped data).
    """
    try:
        resp = await client.call_validated(name, params)
    except JobFailedError as exc:
        outcome = await classify_job_failed_error(client, name, exc, bucket=bucket)
        return outcome, None
    except Exception as exc:  # noqa: BLE001 - one bad step must not abort the sweep
        return CommandOutcome(name, bucket, Status.FAILED, truncate(repr(exc))), None
    if resp.get("success") is True:
        data = resp.get("data")
        return (
            CommandOutcome(name, bucket, Status.EXECUTED_OK, ok_reason),
            data if isinstance(data, dict) else None,
        )
    return (
        CommandOutcome(
            name, bucket, Status.EXPECTED_ERROR, truncate(str(resp.get("error")))
        ),
        None,
    )


async def call_step(
    client: CodeAnalysisAsyncClient,
    name: str,
    params: Dict[str, Any],
    *,
    bucket: Bucket = Bucket.BUCKET_A,
    ok_reason: str = "executed as part of an ordered lifecycle",
) -> CommandOutcome:
    """Call one lifecycle step and return only its outcome (data discarded).

    Args:
        client: Connected async client.
        name: Live command name to invoke.
        params: Params to pass to ``call_validated``.
        bucket: Classification bucket to attach to the outcome.
        ok_reason: Reason text used when the call reports success.

    Returns:
        The step's outcome.
    """
    outcome, _ = await call_step_with_data(
        client, name, params, bucket=bucket, ok_reason=ok_reason
    )
    return outcome


def skip_outcome(
    name: str, reason: str, *, status: Status = Status.EXPECTED_ERROR
) -> CommandOutcome:
    """Build an outcome for a step skipped because an earlier step failed.

    Args:
        name: Live command name that was never invoked.
        reason: Human-readable explanation naming the blocking dependency.
        status: :attr:`Status.EXPECTED_ERROR` (default) when the dependency
            was itself a legitimate rejection; pass :attr:`Status.FAILED` when
            it propagates a tooling failure.

    Returns:
        An outcome recording the skip without ever calling the command.
    """
    return CommandOutcome(name, Bucket.BUCKET_A, status, reason)
