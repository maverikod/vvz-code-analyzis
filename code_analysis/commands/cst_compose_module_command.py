"""
MCP command: compose_cst_module

Applies module-level block replacements using LibCST and validates the result by
compiling the resulting module source.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.cst_module_tools import (
    ReplaceOp,
    Selector,
    apply_replace_ops,
    compile_module,
    unified_diff,
    write_with_backup,
)

logger = logging.getLogger(__name__)


class ComposeCSTModuleCommand(Command):
    """
    Compose/patch a module using CST operations.

    This is intended for "logical blocks" workflows:
    - choose blocks (functions/classes/statements) by selectors
    - replace them with new code snippets
    - normalize imports to the top
    - validate via compile()
    """

    name = "compose_cst_module"
    version = "1.0.0"
    descr = "Replace module-level blocks using LibCST and compile the result"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (absolute or relative to root_dir)",
                },
                "ops": {
                    "type": "array",
                    "description": "List of replacement operations",
                    "items": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "object",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "function",
                                            "class",
                                            "method",
                                            "range",
                                            "block_id",
                                            "node_id",
                                            "cst_query",
                                        ],
                                    },
                                    "name": {"type": "string"},
                                    "start_line": {"type": "integer"},
                                    "start_col": {"type": "integer"},
                                    "end_line": {"type": "integer"},
                                    "end_col": {"type": "integer"},
                                    "block_id": {"type": "string"},
                                    "node_id": {"type": "string"},
                                    "query": {"type": "string"},
                                    "match_index": {"type": "integer"},
                                },
                                "required": ["kind"],
                                "additionalProperties": False,
                            },
                            "new_code": {
                                "type": "string",
                                "description": "Replacement code snippet (empty string means delete)",
                            },
                        },
                        "required": ["selector", "new_code"],
                        "additionalProperties": False,
                    },
                },
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, write changes to file (after successful compile)",
                },
                "create_backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "If apply=true, create a backup in .code_mapper_backups",
                },
                "return_source": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, return the resulting source text (can be large)",
                },
                "return_diff": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, return unified diff",
                },
            },
            "required": ["root_dir", "file_path", "ops"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        ops: list[dict[str, Any]],
        apply: bool = False,
        create_backup: bool = True,
        return_source: bool = False,
        return_diff: bool = True,
        **kwargs,
    ) -> SuccessResult:
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

            old_source = target.read_text(encoding="utf-8")

            parsed_ops: list[ReplaceOp] = []
            for op in ops:
                sel = op.get("selector", {})
                selector = Selector(
                    kind=str(sel.get("kind")),
                    name=sel.get("name"),
                    start_line=sel.get("start_line"),
                    start_col=sel.get("start_col"),
                    end_line=sel.get("end_line"),
                    end_col=sel.get("end_col"),
                    block_id=sel.get("block_id"),
                    node_id=sel.get("node_id"),
                    query=sel.get("query"),
                    match_index=sel.get("match_index"),
                )
                parsed_ops.append(
                    ReplaceOp(selector=selector, new_code=str(op.get("new_code", "")))
                )

            new_source, stats = apply_replace_ops(old_source, parsed_ops)
            ok, compile_error = compile_module(new_source, filename=str(target))

            if not ok:
                payload: dict[str, Any] = {
                    "success": False,
                    "message": "Compilation failed after CST patch",
                    "compile_error": compile_error,
                    "stats": stats,
                }
                if return_diff:
                    payload["diff"] = unified_diff(old_source, new_source, str(target))
                if return_source:
                    payload["source"] = new_source
                return ErrorResult(
                    message="Compilation failed after CST patch",
                    code="COMPILE_ERROR",
                    details=payload,
                )

            backup_path = None
            if apply:
                backup_path = write_with_backup(
                    target, new_source, create_backup=create_backup
                )

            data: dict[str, Any] = {
                "success": True,
                "message": (
                    "CST patch applied successfully"
                    if apply
                    else "CST patch preview generated"
                ),
                "file_path": str(target),
                "applied": apply,
                "backup_path": str(backup_path) if backup_path else None,
                "compiled": True,
                "stats": stats,
            }
            if return_diff:
                data["diff"] = unified_diff(old_source, new_source, str(target))
            if return_source:
                data["source"] = new_source

            return SuccessResult(data=data)
        except Exception as e:
            logger.exception("compose_cst_module failed: %s", e)
            return ErrorResult(
                message=f"compose_cst_module failed: {e}", code="CST_COMPOSE_ERROR"
            )
