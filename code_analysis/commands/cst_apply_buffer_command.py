"""
MCP command: cst_apply_buffer

Apply replacement code from a completed transfer upload buffer to a CST node.
Avoids large payload in JSON-RPC by uploading code in advance via transfer API.

Workflow:
  1. Client calls transfer_upload_begin -> uploads code chunks via PUT
  2. Client calls transfer_upload_complete -> gets transfer_id
  3. Client calls cst_apply_buffer with transfer_id + selector
  4. Server reads code from local buffer, applies via compose_cst_module ops

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .compose_cst_ops_flow import run_ops_mode

logger = logging.getLogger(__name__)


class CSTApplyBufferCommand(BaseMCPCommand):
    """Apply replacement code from a completed transfer upload buffer to a target file."""

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return JSON schema for cst_apply_buffer command parameters."""
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
                        "Selector for the node to replace. Same format as compose_cst_module ops selector. "
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
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and return params."""
        return super().validate_params(params)

    @classmethod
    def metadata(cls: type["CSTApplyBufferCommand"]) -> Dict[str, Any]:
        """Return command metadata."""
        return {
            "name": "cst_apply_buffer",
            "description": (
                "Apply replacement code from a completed transfer upload buffer to a CST node. "
                "Use this instead of compose_cst_module when the replacement code is large and "
                "would trigger external safety filters in the JSON-RPC payload. "
                "Upload the code first via transfer_upload_begin -> PUT chunks -> transfer_upload_complete, "
                "then call cst_apply_buffer with the transfer_id."
            ),
            "category": "cst",
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

        return await run_ops_mode(
            self,
            project_id=project_id,
            file_path=file_path,
            root_path=root_path,
            ops=ops,
            apply=apply,
            create_backup=create_backup,
            return_diff=return_diff,
            commit_message=commit_message,
            t_start=t_start,
            t_prev=t_start,
            validate_syntax_only=validate_syntax_only,
        )
