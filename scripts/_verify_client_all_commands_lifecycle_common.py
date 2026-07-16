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

from code_analysis_client import CodeAnalysisAsyncClient

from _verify_client_all_commands_catalog import Bucket, CommandOutcome, Status, truncate


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
