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

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.cst_module import (
    ReplaceOp,
    InsertOp,
    CreateOp,
    Selector,
    apply_replace_ops,
    apply_insert_ops,
    apply_create_ops,
    compile_module,
    unified_diff,
    write_with_backup,
    validate_module_docstrings,
)

logger = logging.getLogger(__name__)


class ComposeCSTModuleCommand(BaseMCPCommand):
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
                    "description": "List of operations (replace/insert/create)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operation_type": {
                                "type": "string",
                                "enum": ["replace", "insert", "create"],
                                "default": "replace",
                                "description": "Type of operation: replace (default), insert (add before/after), create (create new node)",
                            },
                            "selector": {
                                "type": ["object", "null"],
                                "description": "Selector for target node (null for insert/create at end)",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": [
                                            "module",
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
                                "description": "Code snippet: for replace (replacement, empty=delete), for insert/create (new node code)",
                            },
                            "position": {
                                "type": "string",
                                "enum": [
                                    "before",
                                    "after",
                                    "end",
                                    "end_of_module",
                                    "after_selector",
                                    "before_selector",
                                    "end_of_class",
                                    "end_of_function",
                                ],
                                "default": "after",
                                "description": "Position for insert/create: before/after/end (insert), end_of_module/after_selector/before_selector/end_of_class/end_of_function (create)",
                            },
                            "file_docstring": {
                                "type": "string",
                                "description": "Required when kind='module': file-level docstring",
                            },
                        },
                        "required": ["new_code"],
                        "allOf": [
                            {
                                "if": {
                                    "properties": {
                                        "selector": {
                                            "properties": {"kind": {"const": "module"}}
                                        }
                                    }
                                },
                                "then": {
                                    "required": ["file_docstring", "new_code"],
                                    "properties": {
                                        "file_docstring": {
                                            "type": "string",
                                            "minLength": 1,
                                            "description": "File-level docstring (required and must not be empty for module creation)",
                                        },
                                        "new_code": {
                                            "type": "string",
                                            "minLength": 1,
                                            "description": "First node code - function or class (required and must not be empty for module creation)",
                                        },
                                    },
                                },
                            }
                        ],
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
            root_path = self._validate_root_dir(root_dir)

            # Resolve file path (may not exist if creating new file)
            target = Path(file_path)
            if not target.is_absolute():
                target = root_path / target
            target = target.resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )

            # Handle file creation from scratch
            if not target.exists():
                # Check if we have a "module" selector to create from scratch
                has_module_selector = any(
                    op.get("selector", {}).get("kind") == "module" for op in ops
                )
                if has_module_selector:
                    # Create module from scratch
                    old_source = ""
                else:
                    return ErrorResult(
                        message=(
                            "Target file does not exist. "
                            "To create a new file, use selector with kind='module'"
                        ),
                        code="FILE_NOT_FOUND",
                        details={"file_path": str(target)},
                    )
            else:
                old_source = target.read_text(encoding="utf-8")

            # Separate operations by type
            replace_ops: list[ReplaceOp] = []
            insert_ops: list[InsertOp] = []
            create_ops: list[CreateOp] = []

            for op in ops:
                op_type = op.get("operation_type", "replace")
                sel_dict = op.get("selector")

                selector = None
                if sel_dict:
                    selector = Selector(
                        kind=str(sel_dict.get("kind")),
                        name=sel_dict.get("name"),
                        start_line=sel_dict.get("start_line"),
                        start_col=sel_dict.get("start_col"),
                        end_line=sel_dict.get("end_line"),
                        end_col=sel_dict.get("end_col"),
                        block_id=sel_dict.get("block_id"),
                        node_id=sel_dict.get("node_id"),
                        query=sel_dict.get("query"),
                        match_index=sel_dict.get("match_index"),
                    )

                new_code = str(op.get("new_code", ""))
                position = op.get("position", "after")
                file_docstring = op.get("file_docstring")

                if op_type == "replace":
                    if selector is None:
                        return ErrorResult(
                            message="Selector is required for replace operation",
                            code="INVALID_OPERATION",
                            details={"operation_type": op_type},
                        )
                    replace_ops.append(
                        ReplaceOp(
                            selector=selector,
                            new_code=new_code,
                            file_docstring=file_docstring,
                        )
                    )
                elif op_type == "insert":
                    insert_ops.append(
                        InsertOp(
                            selector=selector,
                            new_code=new_code,
                            position=position,
                            file_docstring=file_docstring,
                        )
                    )
                elif op_type == "create":
                    create_ops.append(
                        CreateOp(
                            selector=selector,
                            new_code=new_code,
                            position=position,
                            file_docstring=file_docstring,
                        )
                    )
                else:
                    return ErrorResult(
                        message=f"Unknown operation type: {op_type}",
                        code="INVALID_OPERATION",
                        details={"operation_type": op_type},
                    )

            # Apply operations in order: replace, then insert, then create
            current_source = old_source
            all_stats: dict[str, Any] = {
                "replaced": 0,
                "removed": 0,
                "inserted": 0,
                "created": 0,
                "unmatched": [],
            }

            if replace_ops:
                current_source, replace_stats = apply_replace_ops(
                    current_source, replace_ops
                )
                all_stats["replaced"] = replace_stats.get("replaced", 0)
                all_stats["removed"] = replace_stats.get("removed", 0)
                all_stats["unmatched"].extend(replace_stats.get("unmatched", []))

            if insert_ops:
                current_source, insert_stats = apply_insert_ops(
                    current_source, insert_ops
                )
                all_stats["inserted"] = insert_stats.get("inserted", 0)
                all_stats["unmatched"].extend(insert_stats.get("unmatched", []))

            if create_ops:
                current_source, create_stats = apply_create_ops(
                    current_source, create_ops
                )
                all_stats["created"] = create_stats.get("created", 0)
                all_stats["unmatched"].extend(create_stats.get("unmatched", []))

            new_source = current_source
            stats = all_stats
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

            # Validate docstrings before applying changes
            docstring_valid, docstring_error, docstring_errors = (
                validate_module_docstrings(new_source)
            )
            if not docstring_valid:
                payload: dict[str, Any] = {
                    "success": False,
                    "message": "Docstring validation failed",
                    "docstring_errors": docstring_errors,
                    "stats": stats,
                }
                if return_diff:
                    payload["diff"] = unified_diff(old_source, new_source, str(target))
                if return_source:
                    payload["source"] = new_source
                return ErrorResult(
                    message=docstring_error or "Docstring validation failed",
                    code="DOCSTRING_VALIDATION_ERROR",
                    details=payload,
                )

            backup_path = None
            backup_uuid = None
            if apply and target.exists():
                # Create backup using BackupManager before applying changes
                backup_manager = BackupManager(root_path)
                # Extract related files from ops (files mentioned in selectors)
                related_files = []
                for op in ops:
                    selector = op.get("selector", {})
                    name = selector.get("name", "")
                    if name and "." in name:
                        # Extract class/module name from selector
                        parts = name.split(".")
                        if len(parts) > 1:
                            related_files.append(parts[0])

                backup_uuid = backup_manager.create_backup(
                    target,
                    command="compose_cst_module",
                    related_files=related_files if related_files else None,
                )
                if backup_uuid:
                    logger.info(f"Backup created before CST compose: {backup_uuid}")

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
                "backup_uuid": backup_uuid,
                "compiled": True,
                "stats": stats,
            }
            if return_diff:
                data["diff"] = unified_diff(old_source, new_source, str(target))
            if return_source:
                data["source"] = new_source

            return SuccessResult(data=data)
        except Exception as e:
            return self._handle_error(e, "CST_COMPOSE_ERROR", "compose_cst_module")
