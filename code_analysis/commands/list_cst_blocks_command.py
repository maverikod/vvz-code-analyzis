"""
MCP command: list_cst_blocks

List logical Python blocks (functions, classes, methods) with stable ids.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import libcst as cst
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .list_cst_blocks_command_metadata import get_list_cst_blocks_metadata
from ..core.cst_module import list_cst_blocks
from ..core.file_lock import file_lock

logger = logging.getLogger(__name__)


class ListCSTBlocksCommand(BaseMCPCommand):
    name = "list_cst_blocks"
    version = "1.0.0"
    descr = (
        "List logical blocks (functions, classes, methods) in a .py file with stable "
        "block ids and line ranges for use with cst_apply_buffer / compose_cst selectors."
    )
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base,
                "file_path": {
                    "type": "string",
                    "description": "Path to .py file relative to project root",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_list_cst_blocks_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self, project_id: str, file_path: str, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        t_start = time.perf_counter()
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
            finally:
                database.disconnect()

            if target.suffix.lower() != ".py":
                return ErrorResult(
                    message="list_cst_blocks only supports .py files",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )
            if not target.exists():
                return ErrorResult(
                    message="File not found",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            with file_lock(target):
                source = target.read_text(encoding="utf-8")

            try:
                blocks_models = list_cst_blocks(source)
            except cst.ParserSyntaxError as e:
                return ErrorResult(
                    message=f"Syntax error in Python source: {e}",
                    code="CST_PARSE_ERROR",
                    details={"file_path": str(target), "error": str(e)},
                )

            blocks = [
                {
                    "id": b.block_id,
                    "block_id": b.block_id,
                    "kind": b.kind,
                    "qualname": b.qualname,
                    "start_line": b.start_line,
                    "end_line": b.end_line,
                }
                for b in blocks_models
            ]

            logger.info(
                "[TIMING] command=list_cst_blocks blocks=%d elapsed_sec=%.4f",
                len(blocks),
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "file_path": str(target.resolve()),
                    "blocks": blocks,
                    "total_blocks": len(blocks),
                }
            )
        except Exception as e:
            logger.exception("list_cst_blocks failed: %s", e)
            return ErrorResult(
                message=f"list_cst_blocks failed: {e}",
                code="CST_LIST_ERROR",
                details={"error": str(e)},
            )
