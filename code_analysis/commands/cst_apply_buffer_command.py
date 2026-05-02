"""
MCP command: cst_apply_buffer

Apply replacement code from a completed transfer upload buffer to a CST node.
Avoids large payload in JSON-RPC by uploading code in advance via transfer API.

Workflow:
  1. Client calls transfer_upload_begin -> uploads code chunks via PUT
  2. Client calls transfer_upload_complete -> gets transfer_id
  3. Client calls cst_apply_buffer with transfer_id + selector
  4. Server reads code from local buffer, applies via run_ops_mode (CST replace-ops)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .compose_cst_ops_flow import run_ops_mode

logger = logging.getLogger(__name__)


class CSTApplyBufferCommand(BaseMCPCommand):
    name = "cst_apply_buffer"
    version = "1.0.0"
    descr = "Apply replacement code from a completed transfer upload buffer to a CST node"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False
    """Apply replacement code from a completed transfer upload buffer to a target file."""

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
                "transfer_id": {
                    "type": "string",
                    "description": (
                        "Transfer ID from transfer_upload_complete. "
                        "The uploaded content will be used as replacement code."
                    ),
                },
                "selector": {
                    "type": "object",
                    "description": (
                        "Selector for the node to replace. Same format as cst_apply_buffer ops selector. "
                        "Examples: {kind: function, name: my_func}, {kind: method, name: execute}, "
                        "{kind: range, start_line: 10, end_line: 20}, {kind: node_id, node_id: <uuid>}."
                    ),
                },
                "apply": {
                    "type": "boolean",
                    "description": "If true (default), write result to file. If false, preview only.",
                    "default": True,
                },
                "validate_syntax_only": {
                    "type": "boolean",
                    "description": (
                        "When true: validate syntax only (ast.parse). "
                        "Skip mypy and docstring checks. "
                        "Use when pre-existing mypy/docstring errors block a local patch."
                    ),
                    "default": False,
                },
                "create_backup": {
                    "type": "boolean",
                    "description": "If true (default), create file backup before writing.",
                    "default": True,
                },
                "return_diff": {
                    "type": "boolean",
                    "description": "If true, include unified diff in response.",
                    "default": False,
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message",
                },
            },
            "required": ["project_id", "file_path", "transfer_id", "selector"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and return params."""
        return super().validate_params(params)

    @classmethod
    def metadata(cls: type["CSTApplyBufferCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The cst_apply_buffer command applies replacement code from a pre-uploaded transfer buffer "
                "to a CST node in a Python file. It solves the problem of large code payloads in JSON-RPC "
                "requests by decoupling the upload step from the apply step.\n\n"
                "This command is the preferred alternative to cst_apply_buffer when the replacement code "
                "is large enough to trigger payload size limits or content filters in the transport layer.\n\n"
                "Operation flow:\n"
                "1. Client calls transfer_upload_begin -> receives transfer_id and chunk URL\n"
                "2. Client PUTs code chunks to the chunk URL (raw bytes, optionally gzip-compressed)\n"
                "3. Client calls transfer_upload_complete -> transfer_id is finalized\n"
                "4. Client calls cst_apply_buffer with transfer_id + selector + file_path\n"
                "5. Server calls get_transfer_store() to locate the committed buffer\n"
                "6. Server reads buffer (decompresses if gzip)\n"
                "7. Server calls run_ops_mode() with the code as new_code\n"
                "8. Result is written to file (apply=true) or returned as preview (apply=false)\n\n"
                "Compression support:\n"
                "- identity: buffer is read as plain UTF-8 text\n"
                "- gzip: buffer is decompressed with gzip.decompress() before use\n\n"
                "Atomicity:\n"
                "- File is either completely updated or completely unchanged\n"
                "- Backup is created before any write (when create_backup=true)\n"
                "- On any error: original file is preserved\n\n"
                "Use cases:\n"
                "- Replacing large functions or classes that exceed JSON-RPC payload limits\n"
                "- Applying code from a file upload without passing it through the JSON-RPC channel\n"
                "- Streaming large code changes in chunks\n\n"
                "Important notes:\n"
                "- transfer_id must reference a completed upload (transfer_upload_complete was called)\n"
                "- The selector format is identical to cst_apply_buffer ops selector\n"
                "- apply=false performs a dry-run and returns diff without writing to disk\n"
                "- return_diff=true includes unified diff in the response regardless of apply value"
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID (from create_project or list_projects). Required.",
                    "type": "string",
                    "required": True,
                    "example": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                },
                "file_path": {
                    "description": "Target Python file path relative to project root.",
                    "type": "string",
                    "required": True,
                    "example": "code_analysis/commands/my_command.py",
                },
                "transfer_id": {
                    "description": (
                        "Transfer session ID returned by transfer_upload_complete. "
                        "The buffer at this ID contains the replacement code."
                    ),
                    "type": "string",
                    "required": True,
                    "example": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                },
                "selector": {
                    "description": (
                        "Selector for the target node. Same format as cst_apply_buffer ops selector. "
                        "Supported kinds: function, class, method, module, range, block_id, node_id, cst_query. "
                        "For kind=method, also provide class_name. "
                        "For kind=range, provide start_line and end_line. "
                        "For kind=node_id, provide node_id (UUID4)."
                    ),
                    "type": "object",
                    "required": True,
                    "example": {
                        "kind": "method",
                        "name": "execute",
                        "class_name": "MyCommand",
                    },
                },
                "apply": {
                    "description": "If true (default), write result to file. If false, preview only (dry-run).",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "validate_syntax_only": {
                    "description": (
                        "When true: validate syntax only (ast.parse). "
                        "Skip flake8/mypy/docstring checks. "
                        "Use when pre-existing linter or type errors must not block a local patch."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "create_backup": {
                    "description": "If true (default), create a backup of the target file before writing.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "return_diff": {
                    "description": "If true, include unified diff in the response. Works with both apply=true and apply=false.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "commit_message": {
                    "description": "Optional git commit message. If provided, creates a git commit after saving.",
                    "type": "string",
                    "required": False,
                },
            },
            "return_value": {
                "success": {
                    "description": "Buffer applied successfully",
                    "data": {
                        "success": "Always True on success",
                        "file_path": "Absolute path to the modified file",
                        "file_written": "True if file was written to disk (apply=true)",
                        "preview_only": "True if apply=false (dry-run)",
                        "diff": "Unified diff string (only if return_diff=true)",
                        "stats": "Operation statistics from run_ops_mode",
                    },
                    "example": {
                        "success": True,
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "file_written": True,
                        "preview_only": False,
                    },
                },
                "error": {
                    "description": "Apply failed",
                    "data": {
                        "success": "Always False on error",
                        "error": "Error message",
                        "error_code": "Machine-readable error code",
                    },
                    "example": {
                        "success": False,
                        "error": "Transfer not found: a1b2c3d4-...",
                        "error_code": "TRANSFER_NOT_FOUND",
                    },
                },
            },
            "usage_examples": [
                {
                    "description": "Apply large function from gzip-compressed buffer",
                    "workflow": [
                        "1. transfer_upload_begin -> transfer_id, chunk_url",
                        "2. PUT gzip(new_code) to chunk_url",
                        "3. transfer_upload_complete(transfer_id)",
                        "4. cst_apply_buffer(project_id, file_path, transfer_id, selector)",
                    ],
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "file_path": "code_analysis/commands/my_command.py",
                        "transfer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "selector": {
                            "kind": "method",
                            "name": "execute",
                            "class_name": "MyCommand",
                        },
                    },
                    "explanation": (
                        "Uploads new execute() implementation via transfer buffer and applies it. "
                        "Backup is created, file is validated, database is updated."
                    ),
                },
                {
                    "description": "Dry-run preview with diff",
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "file_path": "code_analysis/commands/my_command.py",
                        "transfer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "selector": {"kind": "function", "name": "process_data"},
                        "apply": False,
                        "return_diff": True,
                    },
                    "explanation": (
                        "Previews the change without writing to disk. "
                        "Returns unified diff for review."
                    ),
                },
                {
                    "description": "Apply with syntax-only validation and git commit",
                    "command": {
                        "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                        "file_path": "code_analysis/commands/my_command.py",
                        "transfer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "selector": {"kind": "class", "name": "MyCommand"},
                        "validate_syntax_only": True,
                        "commit_message": "refactor: replace MyCommand class body",
                    },
                    "explanation": (
                        "Applies replacement skipping flake8/mypy checks (useful when the file has "
                        "pre-existing linter issues). Creates git commit after successful write."
                    ),
                },
            ],
            "error_cases": {
                "TRANSFER_NOT_FOUND": {
                    "description": "Transfer ID not found or not committed",
                    "message": "Transfer not found or not committed: {transfer_id}",
                    "solution": "Ensure transfer_upload_complete was called for this transfer_id",
                },
                "BUFFER_READ_ERROR": {
                    "description": "Cannot read or decompress the transfer buffer",
                    "message": "Failed to read transfer buffer: {reason}",
                    "solution": "Check compression format; verify upload completed successfully",
                },
                "COMPOSE_ERROR": {
                    "description": "CST compose operation failed (syntax error, selector mismatch, etc.)",
                    "message": "Compose error: {reason}",
                    "solution": (
                        "Check selector matches an existing node. "
                        "Verify replacement code has valid Python syntax."
                    ),
                },
            },
            "best_practices": [
                "Use this command instead of cst_apply_buffer for code blocks > 50 KB",
                "Always call transfer_upload_complete before cst_apply_buffer",
                "Use apply=false + return_diff=true for a safe preview before writing",
                "Use validate_syntax_only=true only when pre-existing linter errors are known",
                "Always provide create_backup=true (default) for safety",
                "After a batch of file changes, run update_indexes to refresh the index",
            ],
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        transfer_id: str,
        selector: Dict[str, Any],
        apply: bool = True,
        validate_syntax_only: bool = False,
        create_backup: bool = True,
        return_diff: bool = False,
        commit_message: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute cst_apply_buffer command."""
        # Step 1: get transfer store and resolve buffer path
        try:
            from mcp_proxy_adapter.api.handlers import get_transfer_store
            from mcp_proxy_adapter.transfer import TransferError
        except ImportError as e:
            return ErrorResult(
                message=f"mcp_proxy_adapter not available: {e}",
                code="IMPORT_ERROR",
            )

        try:
            store = get_transfer_store()
            local_path = store.get_committed_upload_path(transfer_id)
        except Exception as e:
            err_msg = str(e)
            if "not complete" in err_msg.lower() or "not an upload" in err_msg.lower():
                return ErrorResult(
                    message=f"Transfer not ready: {err_msg}",
                    code="TRANSFER_NOT_COMPLETE",
                    details={"transfer_id": transfer_id},
                )
            return ErrorResult(
                message=f"Transfer not found or expired: {err_msg}",
                code="TRANSFER_NOT_FOUND",
                details={"transfer_id": transfer_id},
            )

        # Step 2: read code from buffer (handle gzip compression)
        try:
            session_info = store.get_completed_transfer(transfer_id)
            compression = str(session_info.get("compression", "identity"))
            buffer_path = Path(local_path)
            if compression == "gzip":
                with gzip.open(buffer_path, "rt", encoding="utf-8") as f:
                    new_code = f.read()
            else:
                new_code = buffer_path.read_text(encoding="utf-8")
        except Exception as e:
            return ErrorResult(
                message=f"Failed to read transfer buffer: {e}",
                code="BUFFER_READ_ERROR",
                details={"transfer_id": transfer_id, "local_path": local_path},
            )

        logger.info(
            "[cst_apply_buffer] transfer_id=%s file_path=%s selector=%s apply=%s "
            "buffer_bytes=%d compression=%s",
            transfer_id,
            file_path,
            selector,
            apply,
            len(new_code),
            compression,
        )

        # Step 3: resolve project root and run ops flow
        try:
            root_path = self._resolve_project_root(project_id)
        except Exception as e:
            return ErrorResult(
                message=f"Failed to resolve project root: {e}",
                code="PROJECT_NOT_FOUND",
                details={"project_id": project_id},
            )

        ops = [{"selector": selector, "new_code": new_code}]

        import time

        t_start = time.perf_counter()

        return await asyncio.to_thread(
            run_ops_mode,
            project_id,
            file_path,
            root_path,
            ops,
            apply,
            create_backup,
            return_diff,
            commit_message,
            t_start,
            t_start,
            None,
            validate_syntax_only,
        )

