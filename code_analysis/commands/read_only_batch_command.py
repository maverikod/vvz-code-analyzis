"""
Orchestration for batch read-only command execution.

Accepts a list of command invocations, validates via whitelist (Step 17),
executes each command, and builds the response envelope. Delegates oversized
output to read_only_batch_output (Step 18). No whitelist or storage logic
duplicated here.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Sequence, TypedDict

from mcp_proxy_adapter.commands.command_registry import CommandRegistry
from mcp_proxy_adapter.commands.command_registry import registry as default_registry
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .read_only_batch_output import write_oversized_batch_output
from .read_only_batch_whitelist import (
    READ_ONLY_BATCH_WHITELIST,
    read_only_batch_whitelist_doc,
    validate_command,
)

logger = logging.getLogger(__name__)


class _Invocation(TypedDict):
    """Single batch invocation: command name and params."""

    command: str
    params: dict[str, Any]


class _ResultEntry(TypedDict, total=False):
    """Single entry in batch results for response or storage."""

    command: str
    result: Any


def _json_safe(value: Any) -> Any:
    """Recursively return a JSON-serializable value.

    Dicts and lists/tuples are walked recursively so nested non-serializable
    values (e.g. uuid.UUID returned by the postgres driver) are converted at
    any depth. Mocks become None (existing behavior); uuid.UUID, datetime,
    date, Path, Decimal, and any other non-serializable value become str().
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if type(value).__name__ in ("MagicMock", "Mock"):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime, date, Path, Decimal)):
        return str(value)
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value) if value is not None else None


def _result_to_payload(result: SuccessResult | ErrorResult) -> dict[str, Any]:
    """Convert SuccessResult or ErrorResult to JSON-serializable dict."""
    if isinstance(result, SuccessResult):
        return {
            "success": True,
            "data": _json_safe(getattr(result, "data", None)),
            "message": _json_safe(getattr(result, "message", None)),
        }
    return {
        "success": False,
        "error": _json_safe(getattr(result, "message", str(result))),
        "error_code": _json_safe(getattr(result, "code", None)),
    }


def _serialized_size_bytes(results: Sequence[_ResultEntry]) -> int:
    """Compute deterministic JSON serialization size in bytes (UTF-8)."""
    payload = [
        {"command": e.get("command", ""), "result": e.get("result")} for e in results
    ]
    return len(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    )


async def run_read_only_batch(
    invocations: Sequence[_Invocation],
    max_response_bytes: int,
    output_dir: str,
    *,
    registry: Optional[CommandRegistry] = None,
) -> dict[str, Any]:
    """Orchestrate batch execution of read-only commands.

    Validates every command name against the hardcoded whitelist (no dynamic
    extension). Executes each invocation in order, then either returns
    inline results or delegates to write_oversized_batch_output and returns
    file metadata. Never returns oversized inline payload when over threshold.

    Args:
        invocations: List of {"command": str, "params": dict} to run.
        max_response_bytes: Size limit in bytes; above this, output goes to file.
        output_dir: Directory for oversized output file (used only when over limit).
        registry: Command registry to resolve command instances. Defaults to
            the global MCP registry (populated at server startup).

    Returns:
        Inline mode: {"inline": True, "results": [{"command": str, "result": dict}, ...]}.
        File mode: {"inline": False, "output_file": str, "file_size": int,
                    "results_metadata": [{"command", "size", "offset", "length"}, ...]}.
        Validation error: {"inline": False, "error": str, "error_code": str, ...}.
    """
    reg = registry if registry is not None else default_registry
    results: list[_ResultEntry] = []

    for inv in invocations:
        raw_cmd = inv.get("command")
        command_name = raw_cmd if isinstance(raw_cmd, str) else ""
        ok, error_payload = validate_command(command_name)
        if not ok:
            err = error_payload or {}
            return {
                "inline": False,
                "error": err.get("error", "Command not whitelisted"),
                "error_code": err.get("error_code", "BATCH_COMMAND_NOT_WHITELISTED"),
                "command": err.get("command", command_name),
                "message": err.get("message", ""),
            }

        params = inv.get("params") or {}
        try:
            command_class = reg.get_command(command_name)
        except KeyError:
            return {
                "inline": False,
                "error": f"Command not found: {command_name}",
                "error_code": "BATCH_COMMAND_NOT_FOUND",
                "command": command_name,
                "message": "Command is whitelisted but not registered.",
            }
        cmd = command_class()
        validated_params = cmd.validate_params(params)
        try:
            result = await cmd.execute(**validated_params)
        except Exception as e:
            logger.exception("Batch command %s failed", command_name)
            result = ErrorResult(
                message=str(e),
                code="BATCH_EXECUTION_ERROR",
            )

        payload = _result_to_payload(result)
        results.append(_ResultEntry(command=command_name, result=payload))

    size = _serialized_size_bytes(results)
    if size <= max_response_bytes:
        return {"inline": True, "results": results}

    metadata = write_oversized_batch_output(
        results,
        output_dir,
        file_prefix="batch_output",
    )
    return {
        "inline": False,
        "output_file": metadata["output_file"],
        "file_size": metadata["file_size"],
        "results_metadata": metadata["results_metadata"],
    }
