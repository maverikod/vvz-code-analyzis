"""
MCP command: list_cst_blocks

Lists logical blocks (functions/classes/methods) with stable ids and exact line ranges.
Designed to be paired with compose_cst_module.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.cst_module import list_cst_blocks

logger = logging.getLogger(__name__)


class ListCSTBlocksCommand(Command):
    name = "list_cst_blocks"
    version = "1.0.0"
    descr = "List replaceable CST logical blocks (functions/classes/methods) with ids and ranges"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Project root directory"},
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (absolute or relative to root_dir)",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(self, root_dir: str, file_path: str, **kwargs) -> SuccessResult:
        try:
            root = Path(root_dir).resolve()
            target = Path(file_path)
            if not target.is_absolute():
                target = (root / target).resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )

            if not target.exists():
                return ErrorResult(
                    message="Target file does not exist",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            source = target.read_text(encoding="utf-8")
            blocks = list_cst_blocks(source)
            data = {
                "success": True,
                "file_path": str(target),
                "blocks": [
                    {
                        "id": b.block_id,
                        "kind": b.kind,
                        "qualname": b.qualname,
                        "start_line": b.start_line,
                        "end_line": b.end_line,
                    }
                    for b in blocks
                ],
            }
            return SuccessResult(data=data)
        except Exception as e:
            logger.exception("list_cst_blocks failed: %s", e)
            return ErrorResult(
                message=f"list_cst_blocks failed: {e}", code="CST_LIST_ERROR"
            )
