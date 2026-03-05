"""
MCP command wrapper: read_only_batch.

Exposes batch execution of whitelisted read-only commands. Input: list of
command invocations. Output: inline results or file reference when over
threshold. No mutating commands are exposed through this endpoint.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, cast

from mcp_proxy_adapter.commands.result import SuccessResult

from .base_mcp_command import BaseMCPCommand
from .read_only_batch_command import _Invocation as _BatchInvocation
from .read_only_batch_command import run_read_only_batch
from ..core.constants import (
    DEFAULT_BATCH_MAX_RESPONSE_BYTES,
    DEFAULT_BATCH_OUTPUT_DIR,
)


def _resolve_batch_output_dir(config_path: Path, dir_str: str) -> str:
    """Resolve batch output dir (absolute or relative to config dir)."""
    config_dir = config_path.resolve().parent
    p = Path(dir_str).expanduser()
    if not p.is_absolute():
        p = (config_dir / p).resolve()
    return str(p.resolve())


class ReadOnlyBatchMCPCommand(BaseMCPCommand):
    """Execute a batch of whitelisted read-only commands in one request."""

    name = "read_only_batch"
    version = "1.0.0"
    descr = (
        "Run multiple read-only commands in one request. When total response "
        "size exceeds threshold, results are written to a file and the "
        "response contains output_file path and results_metadata."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Input schema: invocations list and optional overrides."""
        return {
            "type": "object",
            "properties": {
                "invocations": {
                    "type": "array",
                    "description": (
                        "List of command invocations. Each item: "
                        '{"command": "<name>", "params": {...}}. '
                        "Only whitelisted read-only commands are allowed; "
                        "mutating commands are rejected."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Command name (e.g. get_class_hierarchy, list_code_entities).",
                            },
                            "params": {
                                "type": "object",
                                "description": "Parameters for the command (project_id, file_path, etc.).",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["command"],
                        "additionalProperties": True,
                    },
                },
                "max_response_bytes": {
                    "type": "integer",
                    "description": (
                        "Optional override: max inline response size in bytes. "
                        "Above this, output is written to a file and response "
                        "contains output_file and results_metadata. "
                        "If omitted, server config batch_max_response_bytes is used."
                    ),
                },
            },
            "required": ["invocations"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        invocations: Sequence[Dict[str, Any]],
        max_response_bytes: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        """Run batch and return inline results or file metadata."""
        config_path = BaseMCPCommand._resolve_config_path()
        config_data = BaseMCPCommand._get_raw_config()
        ca = config_data.get("code_analysis") or {}
        max_bytes = (
            max_response_bytes
            if max_response_bytes is not None
            else ca.get("batch_max_response_bytes", DEFAULT_BATCH_MAX_RESPONSE_BYTES)
        )
        if max_bytes <= 0:
            max_bytes = DEFAULT_BATCH_MAX_RESPONSE_BYTES
        output_dir_str = ca.get("batch_output_dir", DEFAULT_BATCH_OUTPUT_DIR)
        output_dir = _resolve_batch_output_dir(config_path, output_dir_str)

        inv_list: List[Dict[str, Any]] = [
            {"command": inv.get("command", ""), "params": inv.get("params") or {}}
            for inv in (invocations or [])
        ]
        result = await run_read_only_batch(
            cast(Sequence[_BatchInvocation], inv_list),
            max_response_bytes=max_bytes,
            output_dir=output_dir,
        )
        return SuccessResult(data=result)

    @classmethod
    def metadata(cls: type["ReadOnlyBatchMCPCommand"]) -> Dict[str, Any]:
        """Detailed metadata for MCP help and discovery."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The read_only_batch command runs multiple read-only commands in a single request. "
                "Each invocation must specify a command name and params. Only commands in the "
                "hardcoded whitelist are allowed (e.g. get_class_hierarchy, list_code_entities, "
                "find_dependencies, find_usages, get_entity_dependencies, get_entity_dependents, "
                "export_graph, get_code_entity_info). Mutating commands are never exposed.\n\n"
                "Threshold behavior: If the combined JSON size of all results exceeds "
                "max_response_bytes (from param or server config batch_max_response_bytes), "
                "results are written to a file in batch_output_dir. The response then contains "
                "inline: false, output_file (absolute path), file_size, and results_metadata "
                "(per-command size, offset, length for byte-range extraction).\n\n"
                'Response format (inline): { "inline": true, "results": [ {"command": str, '
                '"result": { "success": bool, "data" | "error": ... } }, ... ] }.\n\n'
                'Response format (oversize): { "inline": false, "output_file": str, '
                '"file_size": int, "results_metadata": [ {"command", "size", '
                '"offset", "length"}, ... ] }. Client may read file at output_file and use '
                "offset/length to extract per-command fragments.\n\n"
                'Error response (e.g. non-whitelisted command): { "inline": false, '
                '"error": str, "error_code": str, "command": str, "message": str }.'
            ),
            "input_schema_summary": (
                "invocations: array of { command: string, params: object }. "
                "Optional max_response_bytes: integer override for size threshold."
            ),
            "output_schema_summary": (
                "inline true: results array with command and result per item. "
                "inline false and success: output_file (path), file_size, results_metadata. "
                "inline false and error: error, error_code, command, message."
            ),
        }
