"""
Per-bucket classification/execution logic for the live-server verifier.

Each function here handles exactly one routing branch of the classification
model (REMOVED cross-check, Bucket B safety list, adapter-safe commands,
outage-risk gate, generic Bucket A execution) and returns a
:class:`CommandOutcome`. ``classify_command`` is the dispatcher that routes a
live command name to the right branch; the sweep engine
(``_verify_client_all_commands_sweep.py``) calls only that dispatcher.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Tuple

from code_analysis_client import CodeAnalysisAsyncClient, JobFailedError
from code_analysis_client.server_api import (
    CST_REMOVED_COMMANDS,
    EDITING_REMOVED_COMMANDS,
    LEGACY_REMOVED_COMMANDS,
    REMOVED_COMMANDS,
)

from _verify_client_all_commands_catalog import (
    ADAPTER_SAFE_TO_EXECUTE,
    BUCKET_B_REASONS,
    MISSING,
    OUTAGE_RISK_COMMANDS,
    STANDARD_ADAPTER_COMMANDS,
    Bucket,
    CommandOutcome,
    Status,
    fixture_value_for,
    is_purge_like,
    is_seeded_file_value,
    schema_has_force,
    schema_has_project_id,
    truncate,
)
from _verify_client_all_commands_fixtures import FixtureContext


def _removed_reason(name: str) -> str:
    """Build a human-readable reason naming which removed-set contains ``name``.

    Args:
        name: A command name known to be in ``REMOVED_COMMANDS``.

    Returns:
        Reason string naming the legacy/CST/editing removed-set membership.
    """
    sets = []
    if name in LEGACY_REMOVED_COMMANDS:
        sets.append("legacy")
    if name in CST_REMOVED_COMMANDS:
        sets.append("CST")
    if name in EDITING_REMOVED_COMMANDS:
        sets.append("editing")
    return f"removed command ({'/'.join(sets) or 'unknown'} removed-set)"


async def check_removed_command(
    client: CodeAnalysisAsyncClient, name: str
) -> CommandOutcome:
    """Confirm a REMOVED-listed command is actually absent live; never call it.

    Args:
        client: Connected async client.
        name: Command name present in ``REMOVED_COMMANDS``.

    Returns:
        A verify-only outcome; flags a discrepancy loudly if the command turns
        out to still be present/callable on the live server.
    """
    reason = _removed_reason(name)
    try:
        await client.get_command_schema(name)
    except Exception:
        return CommandOutcome(
            name,
            Bucket.REMOVED,
            Status.VERIFY_ONLY,
            f"{reason}; live-confirmed absent (schema fetch failed as expected)",
        )
    print(f"!!! DISCREPANCY: {name} listed removed but live-present !!!")
    return CommandOutcome(
        name,
        Bucket.REMOVED,
        Status.VERIFY_ONLY,
        f"{reason}; DISCREPANCY: live server reports this command present/callable, not invoked",
    )


async def check_bucket_b_command(
    client: CodeAnalysisAsyncClient, name: str
) -> CommandOutcome:
    """Record a Bucket B safety-list command's schema fetch; never call it.

    Args:
        client: Connected async client.
        name: Command name present in ``BUCKET_B_REASONS``.

    Returns:
        A verify-only outcome combining the fixed reason with schema-fetch status.
    """
    reason = BUCKET_B_REASONS[name]
    try:
        await client.get_command_schema(name)
        schema_note = "schema fetch ok"
    except Exception as exc:
        schema_note = f"schema fetch failed: {truncate(repr(exc))}"
    return CommandOutcome(
        name,
        Bucket.BUCKET_B,
        Status.VERIFY_ONLY,
        f"{reason} ({schema_note}); never invoked",
    )


async def run_adapter_safe_command(
    client: CodeAnalysisAsyncClient, name: str
) -> CommandOutcome:
    """Execute one of the echo/health/help adapter commands with no params.

    Args:
        client: Connected async client.
        name: One of ``ADAPTER_SAFE_TO_EXECUTE``.

    Returns:
        Outcome reflecting whether the plain call succeeded.
    """
    try:
        resp = await client.call(name, {})
    except Exception as exc:
        return CommandOutcome(name, Bucket.ADAPTER, Status.FAILED, truncate(repr(exc)))
    if resp.get("success") is True:
        return CommandOutcome(
            name,
            Bucket.ADAPTER,
            Status.EXECUTED_OK,
            "standard adapter command, executed with no params",
        )
    return CommandOutcome(
        name, Bucket.ADAPTER, Status.EXPECTED_ERROR, truncate(str(resp.get("error")))
    )


def synthesize_params(
    schema: Dict[str, Any], fixtures: FixtureContext, command_name: str = ""
) -> Tuple[Dict[str, Any], Optional[CommandOutcome]]:
    """Build a params dict for a command's required properties, or bail out.

    Args:
        schema: The command's ``get_schema()``-style dict.
        fixtures: The disposable project/session fixture for this run.
        command_name: Live command name, used to look up a per-command
            fixture-value override before the generic-by-property providers.

    Returns:
        Tuple of (params, early_outcome). ``early_outcome`` is ``None`` when
        synthesis succeeded; otherwise it is a template outcome (name left
        blank for the caller to fill in) to report instead of calling the
        command — either a missing generic provider or a required fixture
        file that failed to seed.
    """
    props = schema.get("properties") or {}
    required = schema.get("required") or []
    params: Dict[str, Any] = {}
    for prop in required:
        value = fixture_value_for(prop, fixtures, command_name)
        if value is MISSING:
            return {}, CommandOutcome(
                "",
                Bucket.BUCKET_A,
                Status.EXPECTED_ERROR,
                f"no generic fixture value for required param {prop!r} — "
                "needs command-specific data, not exercised",
            )
        if is_seeded_file_value(value, fixtures) and not fixtures.files_seeded:
            return {}, CommandOutcome(
                "",
                Bucket.BUCKET_A,
                Status.FAILED,
                f"required seeded fixture file unavailable ({fixtures.seed_error})",
            )
        params[prop] = value
    if "project_id" in props:
        params["project_id"] = fixtures.project_id
    return params, None


_STRUCTURED_ERROR_LOOKUP_ATTEMPTS = 4
_STRUCTURED_ERROR_LOOKUP_RETRY_DELAY_SECONDS = 0.5


async def _fetch_structured_job_error(
    client: CodeAnalysisAsyncClient, job_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Fetch a failed queued command's own structured error via its job status.

    ``JobFailedError.error`` only carries the queue-level error (populated
    when the worker/job itself crashed); a command that legitimately rejected
    its input (e.g. ``git_init`` on a path without permissions) reports its
    own structured error nested at ``data.result.result.error`` instead of at
    the top level of ``JobFailedError``. ``queue_get_job_status`` itself
    always returns synchronously (never queued), so this is a plain call, not
    another poll.

    Root cause (verified empirically against jobs a176e3c4/9552bc44): the
    queue store writes the job's terminal ``status`` (which is what makes
    ``call_validated`` raise ``JobFailedError``) slightly before it writes
    ``data.result.result`` — the inner command-error payload. A lookup made
    immediately after the raise can therefore race that second write and see
    ``status: failed`` with no inner error yet, even though the very same job
    reliably has one moments later. To ride out that race, this retries the
    lookup up to :data:`_STRUCTURED_ERROR_LOOKUP_ATTEMPTS` times, sleeping
    :data:`_STRUCTURED_ERROR_LOOKUP_RETRY_DELAY_SECONDS` between attempts,
    and returns as soon as a structured error dict shows up.

    Args:
        client: Connected async client.
        job_id: The failed job's id (``JobFailedError.job_id``); ``None``
            skips the lookup.

    Returns:
        The command's structured error dict (has a ``code`` and/or
        ``message`` key) if one is found within the retry budget, else
        ``None``.
    """
    if not job_id:
        return None
    for attempt in range(_STRUCTURED_ERROR_LOOKUP_ATTEMPTS):
        try:
            resp = await client.call("queue_get_job_status", {"job_id": job_id})
        except Exception:  # noqa: BLE001 - best-effort, falls back to the FAILED status
            resp = None
        if isinstance(resp, dict) and resp.get("success") is True:
            data = resp.get("data")
            result_field = data.get("result") if isinstance(data, dict) else None
            inner = (
                result_field.get("result") if isinstance(result_field, dict) else None
            )
            error = inner.get("error") if isinstance(inner, dict) else None
            if isinstance(error, dict) and (error.get("code") or error.get("message")):
                return error
        if attempt < _STRUCTURED_ERROR_LOOKUP_ATTEMPTS - 1:
            await asyncio.sleep(_STRUCTURED_ERROR_LOOKUP_RETRY_DELAY_SECONDS)
    return None


async def classify_job_failed_error(
    client: CodeAnalysisAsyncClient,
    name: str,
    exc: JobFailedError,
    *,
    bucket: Bucket = Bucket.BUCKET_A,
) -> CommandOutcome:
    """Classify a ``JobFailedError`` as a structured expected-error, or keep it FAILED.

    Looks up the failed job's own structured error via
    :func:`_fetch_structured_job_error`. When found, the command legitimately
    rejected valid-looking input server-side (e.g. ``git_init`` on a
    permission-denied path) — that is an expected error, not a tooling
    failure, so it is reported the same way every other expected-error row
    is. When no structured inner error is found, the ``JobFailedError`` is
    reported verbatim as a FAILED outcome, same as before this classification
    existed.

    Args:
        client: Connected async client.
        name: Live command name that raised ``exc``.
        exc: The ``JobFailedError`` raised by ``call``/``call_validated``.
        bucket: Classification bucket to attach to the outcome.

    Returns:
        EXPECTED_ERROR outcome carrying the structured code+message when
        found; otherwise a FAILED outcome with the ``JobFailedError`` text.
    """
    structured = await _fetch_structured_job_error(client, exc.job_id)
    if structured is not None:
        return CommandOutcome(
            name, bucket, Status.EXPECTED_ERROR, truncate(str(structured))
        )
    return CommandOutcome(name, bucket, Status.FAILED, truncate(repr(exc)))


async def run_bucket_a(
    client: CodeAnalysisAsyncClient, name: str, fixtures: FixtureContext
) -> CommandOutcome:
    """Generic Bucket A path: synthesize params and call via ``call_validated``.

    Args:
        client: Connected async client.
        name: Live command name.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Outcome reflecting execution result, a legitimate rejection, a missing
        generic provider, or an unexpected failure. A ``JobFailedError`` from
        the client's auto-polling is classified via
        :func:`classify_job_failed_error` rather than reported as a blanket
        FAILED.
    """
    try:
        schema = await client.get_command_schema(name)
    except Exception as exc:
        return CommandOutcome(
            name,
            Bucket.BUCKET_A,
            Status.FAILED,
            f"schema fetch failed: {truncate(repr(exc))}",
        )
    params, early = synthesize_params(schema, fixtures, name)
    if early is not None:
        return CommandOutcome(name, early.bucket, early.status, early.reason)
    try:
        resp = await client.call_validated(name, params)
    except JobFailedError as exc:
        return await classify_job_failed_error(client, name, exc)
    except Exception as exc:
        return CommandOutcome(name, Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc)))
    if resp.get("success") is True:
        return CommandOutcome(
            name,
            Bucket.BUCKET_A,
            Status.EXECUTED_OK,
            "executed against disposable project",
        )
    return CommandOutcome(
        name, Bucket.BUCKET_A, Status.EXPECTED_ERROR, truncate(str(resp.get("error")))
    )


async def run_outage_risk_command(
    client: CodeAnalysisAsyncClient, name: str, fixtures: FixtureContext
) -> CommandOutcome:
    """Exercise a known outage-risk command with an explicit ``force=False`` gate.

    See docs/bugreports/2026-07-06-jsonrpc-empty-body-after-sync-cap-fallback.md
    for why ``revectorize``/``rebuild_faiss``/``update_indexes`` get this extra gate
    on top of the normal Bucket A path.

    Args:
        client: Connected async client.
        name: One of ``OUTAGE_RISK_COMMANDS``.
        fixtures: The disposable project/session fixture for this run.

    Returns:
        Outcome: verify-only if the command has no project-scoped safe
        invocation, otherwise the normal executed/expected-error/failed outcomes.
    """
    try:
        schema = await client.get_command_schema(name)
    except Exception as exc:
        return CommandOutcome(
            name,
            Bucket.BUCKET_A,
            Status.FAILED,
            f"schema fetch failed: {truncate(repr(exc))}",
        )
    if not schema_has_project_id(schema):
        return CommandOutcome(
            name,
            Bucket.BUCKET_A,
            Status.VERIFY_ONLY,
            "known outage risk and no project-scoped safe invocation, see "
            "docs/bugreports/2026-07-06-jsonrpc-empty-body-after-sync-cap-fallback.md",
        )
    params, early = synthesize_params(schema, fixtures, name)
    if early is not None:
        return CommandOutcome(name, early.bucket, early.status, early.reason)
    if schema_has_force(schema):
        params["force"] = False
    try:
        resp = await client.call_validated(name, params)
    except Exception as exc:
        return CommandOutcome(name, Bucket.BUCKET_A, Status.FAILED, truncate(repr(exc)))
    if resp.get("success") is True:
        return CommandOutcome(
            name,
            Bucket.BUCKET_A,
            Status.EXECUTED_OK,
            "outage-risk command executed with force=False against disposable project",
        )
    return CommandOutcome(
        name, Bucket.BUCKET_A, Status.EXPECTED_ERROR, truncate(str(resp.get("error")))
    )


async def classify_command(
    client: CodeAnalysisAsyncClient,
    name: str,
    fixtures: FixtureContext,
    precomputed: Optional[Dict[str, CommandOutcome]] = None,
) -> CommandOutcome:
    """Route one live command name to its classification/execution path.

    Precedence: precomputed ordered-lifecycle outcome (session, transfer,
    search, git, github, entities, fs, workers, queue — see
    ``_verify_client_all_commands_lifecycles.run_lifecycles``), then REMOVED
    cross-check, then fixed Bucket B safety list, then adapter-safe
    (echo/health/help/queue_health/queue_list_jobs/plugins/roletest), then
    remaining standard-adapter infra (verify-only), then outage-risk gate,
    then the general purge/delete/trash scoping gate, then generic Bucket A
    execution.

    Args:
        client: Connected async client.
        name: Live command name.
        fixtures: The disposable project/session fixture for this run.
        precomputed: Outcomes already produced by the ordered lifecycles, keyed
            by command name; consulted before any other routing branch.

    Returns:
        The classification/execution outcome for ``name``.
    """
    if precomputed and name in precomputed:
        return precomputed[name]
    if name in REMOVED_COMMANDS:
        return await check_removed_command(client, name)
    if name in BUCKET_B_REASONS:
        return await check_bucket_b_command(client, name)
    if name in ADAPTER_SAFE_TO_EXECUTE:
        return await run_adapter_safe_command(client, name)
    if name in STANDARD_ADAPTER_COMMANDS:
        return CommandOutcome(
            name,
            Bucket.ADAPTER,
            Status.VERIFY_ONLY,
            "standard mcp_proxy_adapter infra command, not project-scoped, not exercised",
        )
    if name in OUTAGE_RISK_COMMANDS:
        return await run_outage_risk_command(client, name, fixtures)
    if is_purge_like(name):
        try:
            schema = await client.get_command_schema(name)
        except Exception as exc:
            return CommandOutcome(
                name,
                Bucket.BUCKET_A,
                Status.FAILED,
                f"schema fetch failed: {truncate(repr(exc))}",
            )
        if not schema_has_project_id(schema):
            return CommandOutcome(
                name,
                Bucket.BUCKET_A,
                Status.VERIFY_ONLY,
                "schema shows no project_id — global/bulk scope risk",
            )
    return await run_bucket_a(client, name, fixtures)
