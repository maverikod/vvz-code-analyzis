"""
Inline search timeout with automatic queue fallback for heavy search commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .progress_tracker import get_progress_tracker_from_context
from .search_timeouts import (
    AUTO_QUEUE_REASON,
    EXECUTION_MODE_QUEUED,
    INTERNAL_EXECUTION_MODE_KEY,
    resolve_inline_timeout_seconds,
)

INTERNAL_QUEUE_METADATA_KEY = "_search_auto_queue_metadata"


def is_queued_search_execution(
    *,
    context: Optional[Dict[str, Any]],
) -> bool:
    """True when running as a background job (no second auto-queue)."""
    ctx = context or {}
    if ctx.get(INTERNAL_EXECUTION_MODE_KEY) == EXECUTION_MODE_QUEUED:
        return True
    return get_progress_tracker_from_context(ctx) is not None


def build_auto_queue_job_metadata(
    *,
    command_name: str,
    inline_timeout_seconds: float,
) -> Dict[str, Any]:
    return {
        "auto_queued": True,
        "reason": AUTO_QUEUE_REASON,
        "original_command": command_name,
        "inline_timeout_seconds": inline_timeout_seconds,
    }


def params_for_auto_queue_enqueue(params: Dict[str, Any]) -> Dict[str, Any]:
    """User params for re-enqueue; strip transport-only keys."""
    skip = {
        INTERNAL_EXECUTION_MODE_KEY,
        INTERNAL_QUEUE_METADATA_KEY,
        "poll_interval",
        "max_wait_time",
        "context",
    }
    return {k: v for k, v in params.items() if k not in skip}


def queued_inline_timeout_response(
    *,
    job_id: str,
    inline_timeout_seconds: float,
) -> SuccessResult:
    message = "Search did not finish within inline timeout and was queued."
    return SuccessResult(
        data={
            "queued": True,
            "job_id": job_id,
            "status": "pending",
            "inline_timeout_seconds": inline_timeout_seconds,
            "message": message,
        },
        message=message,
    )


def mark_inline_result(
    result: SuccessResult | ErrorResult,
) -> SuccessResult | ErrorResult:
    if isinstance(result, ErrorResult):
        return result
    data = dict(result.data or {})
    data["queued"] = False
    return SuccessResult(data=data, message=result.message)


async def enqueue_search_command(
    *,
    command_name: str,
    params: Dict[str, Any],
    context: Dict[str, Any],
    inline_timeout_seconds: float,
) -> SuccessResult:
    from mcp_proxy_adapter.commands.hooks import hooks
    from mcp_proxy_adapter.commands.queue.jobs import CommandExecutionJob
    from mcp_proxy_adapter.integrations.queuemgr_integration import (
        get_global_queue_manager,
    )

    queue_manager = await get_global_queue_manager()
    job_id = str(uuid.uuid4())
    command_params = params_for_auto_queue_enqueue(params)
    command_params.pop("poll_interval", None)
    command_params.pop("max_wait_time", None)

    job_context = dict(context or {})
    job_context[INTERNAL_EXECUTION_MODE_KEY] = EXECUTION_MODE_QUEUED

    job_params: Dict[str, Any] = {
        "command": command_name,
        "params": command_params,
        "context": job_context,
        "auto_import_modules": hooks.get_auto_import_modules(),
        "auto_queue_metadata": build_auto_queue_job_metadata(
            command_name=command_name,
            inline_timeout_seconds=inline_timeout_seconds,
        ),
    }

    await queue_manager.add_job(CommandExecutionJob, job_id, job_params)

    async def _start_job_background() -> None:
        try:
            await queue_manager.start_job(job_id)
        except Exception:
            pass

    asyncio.create_task(_start_job_background())
    return queued_inline_timeout_response(
        job_id=job_id,
        inline_timeout_seconds=inline_timeout_seconds,
    )


async def run_search_inline_or_queue(
    *,
    command_name: str,
    params: Dict[str, Any],
    context: Dict[str, Any],
    auto_queue_on_inline_timeout: bool,
    inline_timeout_seconds: Optional[float],
    execute_fn: Callable[[], Awaitable[SuccessResult | ErrorResult]],
    cancel_event: Optional[threading.Event] = None,
) -> SuccessResult | ErrorResult:
    """Try inline execution; on timeout enqueue the same command once."""
    if is_queued_search_execution(context=context):
        return mark_inline_result(await execute_fn())

    if not auto_queue_on_inline_timeout:
        return mark_inline_result(await execute_fn())

    inline_limit = resolve_inline_timeout_seconds(inline_timeout_seconds)
    try:
        result = await asyncio.wait_for(execute_fn(), timeout=inline_limit)
    except asyncio.TimeoutError:
        if cancel_event is not None:
            cancel_event.set()
        return await enqueue_search_command(
            command_name=command_name,
            params=params,
            context=context,
            inline_timeout_seconds=inline_limit,
        )

    return mark_inline_result(result)
