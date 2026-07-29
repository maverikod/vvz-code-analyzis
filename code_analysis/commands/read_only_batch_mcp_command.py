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
from .read_only_batch_whitelist import (
    READ_ONLY_BATCH_WHITELIST,
    read_only_batch_whitelist_doc,
)
from ..core.constants import (
    DEFAULT_BATCH_MAX_RESPONSE_BYTES,
    DEFAULT_BATCH_OUTPUT_DIR,
)
from ..core.list_pagination import list_pagination_schema_properties
from ..core.storage_paths import resolve_batch_output_dir

# Presence of any of these params (even 0 / an explicit falsy value) requests
# the paginated inline retrieval mode (TODO 9c2018a3) instead of the default
# inline-or-file behavior.
_PAGINATION_TRIGGER_KEYS = ("page_size", "block_position", "offset", "limit")


class ReadOnlyBatchMCPCommand(BaseMCPCommand):
    """Execute a batch of whitelisted read-only commands in one request."""

    name = "read_only_batch"
    version = "1.0.0"
    descr = (
        "Run multiple read-only commands in one request. When total response "
        "size exceeds threshold, results are written to a file and the "
        "response contains output_file path and results_metadata. Pass "
        "page_size/block_position/offset/limit for paginated inline "
        "retrieval instead (successive result pages, no filesystem output)."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Input schema: invocations list and optional overrides."""
        whitelist = sorted(READ_ONLY_BATCH_WHITELIST)
        pagination = list_pagination_schema_properties()
        for prop in pagination.values():
            prop["description"] = (
                str(prop["description"])
                + " Presence of this parameter switches on paginated inline "
                "retrieval (TODO 9c2018a3): a bounded page of `results` returned "
                "inline, never written to a file."
            )
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
                                "enum": whitelist,
                                "description": (
                                    "Whitelisted read-only command name "
                                    f"(e.g. universal_file_preview, get_class_hierarchy). "
                                    f"Allowed: {read_only_batch_whitelist_doc()}."
                                ),
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
                        "If omitted, server config batch_max_response_bytes is used. "
                        "Ignored when paginated inline retrieval is active."
                    ),
                },
                **pagination,
            },
            "required": ["invocations"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        invocations: Sequence[Dict[str, Any]],
        max_response_bytes: Optional[int] = None,
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        """Run batch and return inline results, a paginated inline page, or file metadata."""
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
        output_dir = str(
            resolve_batch_output_dir(config_path=config_path, dir_str=output_dir_str)
        )

        inv_list: List[Dict[str, Any]] = [
            {"command": inv.get("command", ""), "params": inv.get("params") or {}}
            for inv in (invocations or [])
        ]
        pagination_field_values = {
            "page_size": page_size,
            "block_position": block_position,
            "offset": offset,
            "limit": limit,
        }
        pagination_requested = any(
            pagination_field_values[key] is not None
            for key in _PAGINATION_TRIGGER_KEYS
        )
        result = await run_read_only_batch(
            cast(Sequence[_BatchInvocation], inv_list),
            max_response_bytes=max_bytes,
            output_dir=output_dir,
            pagination_requested=pagination_requested,
            page_size=page_size,
            block_position=block_position,
            offset=offset,
            limit=limit,
        )
        return SuccessResult(data=result)

    @classmethod
    def metadata(cls: type["ReadOnlyBatchMCPCommand"]) -> Dict[str, Any]:
        """Detailed metadata for MCP help and discovery (man-page style)."""
        whitelist_doc = read_only_batch_whitelist_doc()
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
                f"hardcoded whitelist are allowed: {whitelist_doc}. "
                "Mutating commands are never exposed.\n\n"
                "Operation flow:\n"
                "1. Validates invocations list is non-empty\n"
                "2. For each invocation, validates command name against whitelist (fail-fast on first rejection)\n"
                "3. Resolves command instances from registry and executes in order\n"
                "4. If page_size/block_position/offset/limit was passed, returns one "
                "bounded inline page over results (TODO 9c2018a3) -- see Pagination below\n"
                "5. Otherwise: serializes combined results; if size <= max_response_bytes returns inline\n"
                "6. If over threshold, writes to file in batch_output_dir and returns output_file, file_size, results_metadata\n\n"
                "Threshold behavior:\n"
                "- max_response_bytes from param or server config batch_max_response_bytes\n"
                "- Above threshold: results written to batch_output_dir; response has inline: false, output_file, file_size, results_metadata (size/offset/length per command for byte-range extraction)\n"
                "- Ignored entirely when pagination is requested (see below)\n\n"
                "Pagination (paginated inline retrieval, TODO 9c2018a3):\n"
                "- Passing any of page_size / block_position / offset / limit switches the "
                "response to a bounded, paginated inline page over the per-invocation "
                "results -- same envelope/bounds convention as list_project_files / search "
                "(page_size default 20, max 200; block_position 1-based; offset legacy "
                "alternative)\n"
                "- ALL invocations still run on every call (this command has no server-side "
                "session to resume from); pagination only bounds the response size, letting "
                "a caller page through results without ever touching the filesystem\n"
                "- Response: inline: true, paginated: true, items/results (page slice), "
                "count, total, page_size, block_position, has_more, offset\n"
                "- The file-overflow mechanism above is unaffected when pagination is not requested\n\n"
                "Use cases:\n"
                "- Run several read-only analysis commands in one round-trip\n"
                "- Reduce latency when client needs hierarchy + entities + dependencies\n"
                "- Handle large combined payload via file reference and offset/length extraction\n"
                "- Page through many invocation results inline without a filesystem round-trip\n\n"
                "Important notes:\n"
                "- Whitelist is hardcoded; no dynamic extension from client or config\n"
                "- First non-whitelisted command aborts the batch with error_code BATCH_COMMAND_NOT_WHITELISTED\n"
                "- output_file path is absolute; client may read fragments using results_metadata offset and length"
            ),
            "parameters": {
                "invocations": {
                    "description": (
                        "List of command invocations. Each item: command (string, required), params (object). "
                        "Only whitelisted read-only commands allowed; mutating commands are rejected."
                    ),
                    "type": "array",
                    "required": True,
                    "items": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": (
                                    "Whitelisted read-only command name "
                                    f"(e.g. universal_file_preview). Allowed: {whitelist_doc}."
                                ),
                            },
                            "params": {
                                "type": "object",
                                "description": "Parameters for the command (project_id, file_path, etc.).",
                                "additionalProperties": True,
                            },
                        },
                        "required": ["command"],
                    },
                },
                "max_response_bytes": {
                    "description": (
                        "Optional override for max inline response size in bytes. "
                        "Above this, output is written to file; response contains output_file and results_metadata. "
                        "If omitted, server config batch_max_response_bytes is used. "
                        "Ignored when paginated inline retrieval is active."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "page_size": {
                    "description": (
                        "Paginated inline retrieval: rows per page (default 20, max 200). "
                        "Presence of this parameter switches on pagination."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 20,
                },
                "block_position": {
                    "description": (
                        "Paginated inline retrieval: 1-based page index (default 1). "
                        "Increment for the next page."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 1,
                },
                "offset": {
                    "description": (
                        "Paginated inline retrieval: legacy row offset, ignored when "
                        "block_position is set."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "limit": {
                    "description": "Paginated inline retrieval: legacy alias for page_size.",
                    "type": "integer",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Preview + entity lookup in one batch",
                    "command": {
                        "invocations": [
                            {
                                "command": "universal_file_preview",
                                "params": {
                                    "project_id": "proj-uuid",
                                    "file_path": "src/example.py",
                                },
                            },
                            {
                                "command": "get_code_entity_info",
                                "params": {
                                    "project_id": "proj-uuid",
                                    "entity_name": "ExampleClass",
                                },
                            },
                        ],
                    },
                    "explanation": (
                        "Runs file preview and entity info in one round-trip; "
                        "both commands are read-only and whitelisted."
                    ),
                },
                {
                    "description": "Small batch inline",
                    "command": {
                        "invocations": [
                            {
                                "command": "get_class_hierarchy",
                                "params": {"project_id": "proj-uuid"},
                            },
                            {
                                "command": "list_code_entities",
                                "params": {
                                    "project_id": "proj-uuid",
                                    "entity_type": "class",
                                },
                            },
                        ],
                    },
                    "explanation": "Runs two read-only commands; if combined size is under threshold, returns inline results.",
                },
                {
                    "description": "Force file output with zero threshold",
                    "command": {
                        "invocations": [
                            {
                                "command": "list_code_entities",
                                "params": {"project_id": "proj-uuid"},
                            }
                        ],
                        "max_response_bytes": 0,
                    },
                    "explanation": "With max_response_bytes=0 (or very small), response will be file reference and results_metadata.",
                },
                {
                    "description": "Paginated inline retrieval over many invocations",
                    "command": {
                        "invocations": [
                            {
                                "command": "get_class_hierarchy",
                                "params": {"project_id": "proj-uuid"},
                            },
                            {
                                "command": "list_code_entities",
                                "params": {"project_id": "proj-uuid"},
                            },
                            {
                                "command": "get_ast",
                                "params": {
                                    "project_id": "proj-uuid",
                                    "file_path": "src/main.py",
                                },
                            },
                        ],
                        "page_size": 1,
                        "block_position": 1,
                    },
                    "explanation": (
                        "Returns page 1 (the first invocation's result only) inline; "
                        "increment block_position for the next result, never touching "
                        "the filesystem even if the full batch would overflow to file."
                    ),
                },
            ],
            "error_cases": {
                "BATCH_COMMAND_NOT_WHITELISTED": {
                    "description": "A command in invocations is not in the read-only whitelist",
                    "example": "invocations include cst_save_tree or update_indexes",
                    "solution": f"Use only whitelisted commands: {whitelist_doc}.",
                },
                "BATCH_COMMAND_NOT_FOUND": {
                    "description": "Command is whitelisted but not registered in the server registry",
                    "example": "Command name typo or server not fully loaded",
                    "solution": "Check command name spelling; ensure server has registered AST commands.",
                },
                "BATCH_EXECUTION_ERROR": {
                    "description": "One of the batch commands raised an exception during execute",
                    "example": "project_id not found, database error, invalid params for that command",
                    "solution": "Inspect the failed command and params; fix project_id or run update_indexes if needed.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Batch completed; payload is either inline or file reference.",
                    "data": {
                        "inline": "True if results are in response; False if output was written to file.",
                        "results": "When inline true (non-paginated): array of { command: str, result: { success, data | error, error_code } }. When paginated: alias of items (page slice only).",
                        "paginated": "True only when pagination was requested; omitted otherwise.",
                        "items": "When paginated: page slice, same shape as results entries.",
                        "count": "When paginated: number of entries in this page.",
                        "total": "When paginated: total invocation results before pagination.",
                        "page_size": "When paginated: resolved rows-per-page (default 20, max 200).",
                        "block_position": "When paginated: resolved 1-based page index.",
                        "has_more": "When paginated: True if a further page exists.",
                        "offset": "When paginated: resolved row offset for this page.",
                        "output_file": "When inline false (oversize): absolute path to .jsonl file.",
                        "file_size": "When inline false: total file size in bytes.",
                        "results_metadata": "When inline false: list of { command, size, offset, length } for byte-range extraction.",
                        "error": "When inline false and validation failed: error message.",
                        "error_code": "When inline false and error: BATCH_COMMAND_NOT_WHITELISTED | BATCH_COMMAND_NOT_FOUND | ...",
                        "command": "When inline false and error: the command that failed validation.",
                        "message": "When inline false and error: human-readable message.",
                    },
                    "example_inline": {
                        "inline": True,
                        "results": [
                            {
                                "command": "get_class_hierarchy",
                                "result": {
                                    "success": True,
                                    "data": {"hierarchy": {}, "count": 0},
                                },
                            },
                        ],
                    },
                    "example_oversize": {
                        "inline": False,
                        "output_file": "/path/to/data/batch_output/batch_output_abc123.jsonl",
                        "file_size": 10240,
                        "results_metadata": [
                            {
                                "command": "list_code_entities",
                                "size": 5120,
                                "offset": 0,
                                "length": 5120,
                            },
                            {
                                "command": "find_dependencies",
                                "size": 5120,
                                "offset": 5120,
                                "length": 5120,
                            },
                        ],
                    },
                    "example_error": {
                        "inline": False,
                        "error": "Command is not in the read-only batch whitelist.",
                        "error_code": "BATCH_COMMAND_NOT_WHITELISTED",
                        "command": "cst_save_tree",
                        "message": "Command is not in the read-only batch whitelist.",
                    },
                    "example_paginated_inline": {
                        "inline": True,
                        "paginated": True,
                        "items": [
                            {
                                "command": "get_class_hierarchy",
                                "result": {
                                    "success": True,
                                    "data": {"hierarchy": {}, "count": 0},
                                },
                            },
                        ],
                        "results": [
                            {
                                "command": "get_class_hierarchy",
                                "result": {
                                    "success": True,
                                    "data": {"hierarchy": {}, "count": 0},
                                },
                            },
                        ],
                        "count": 1,
                        "total": 3,
                        "page_size": 1,
                        "block_position": 1,
                        "has_more": True,
                        "offset": 0,
                    },
                },
                "error": {
                    "description": "Command failed (e.g. invalid schema, server error)",
                    "code": "Error code from MCP layer",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use invocations with whitelisted commands only; mutating commands are rejected.",
                "Set max_response_bytes when you expect large combined output and want file reference.",
                "Use results_metadata offset/length to read per-command fragments from output_file without loading whole file.",
                "Keep batch size reasonable to avoid timeouts; threshold only limits response size, not execution time.",
                "Prefer page_size/block_position over max_response_bytes when you want to page through "
                "results inline without ever writing/reading a file; every page re-runs all invocations "
                "(no server-side session), so it only bounds response size, not execution cost.",
            ],
        }
