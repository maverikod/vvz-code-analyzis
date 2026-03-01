"""
MCP command: cst_modify_tree

Modify CST tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.models import TreeOperation, TreeOperationType
from ..core.cst_tree.tree_builder import get_tree, rollback_tree_to_code
from ..core.cst_tree.tree_modifier import modify_tree
from ..core.cst_tree.tree_saver import save_tree_to_file
from ..cst_query import query_source

logger = logging.getLogger(__name__)


def _find_tree_node_id_by_position(
    tree: Any, start_line: int, start_col: int, end_line: int, end_col: int
) -> Optional[str]:
    """Find tree's node_id for metadata matching given position."""
    for nid, meta in tree.metadata_map.items():
        if (
            meta.start_line == start_line
            and meta.start_col == start_col
            and meta.end_line == end_line
            and meta.end_col == end_col
        ):
            return nid
    return None


def _resolve_selector_to_tree_node_ids(
    tree: Any, selector: str, match_index: Optional[int], replace_all: bool
) -> List[str]:
    """
    Resolve selector to tree's node_ids (UUIDs in node_map).
    Uses query_source for matches, then finds tree metadata by position.
    """
    source = tree.module.code
    matches = query_source(source, selector, include_code=False)
    if not matches:
        return []
    node_ids: List[str] = []
    if replace_all:
        for m in matches:
            nid = _find_tree_node_id_by_position(
                tree, m.start_line, m.start_col, m.end_line, m.end_col
            )
            if nid:
                node_ids.append(nid)
    else:
        idx = match_index if match_index is not None else 0
        if 0 <= idx < len(matches):
            m = matches[idx]
            nid = _find_tree_node_id_by_position(
                tree, m.start_line, m.start_col, m.end_line, m.end_col
            )
            if nid:
                node_ids.append(nid)
    return node_ids


class CSTModifyTreeCommand(BaseMCPCommand):
    """Modify CST tree with atomic operations."""

    name = "cst_modify_tree"
    version = "1.0.0"
    descr = "Modify CST tree with atomic operations (replace, insert, delete)"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {
                    "type": "string",
                    "description": "Tree ID from cst_load_file",
                },
                "preview": {
                    "type": "boolean",
                    "description": "Preview mode: show changes without applying (default: false)",
                },
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "replace",
                                    "replace_range",
                                    "insert",
                                    "delete",
                                    "move",
                                ],
                                "description": "Operation type",
                            },
                            "node_id": {
                                "type": "string",
                                "description": "Node ID for replace/delete operations (from cst_find_node)",
                            },
                            "selector": {
                                "type": "string",
                                "description": (
                                    "XPath-like CSTQuery selector (alternative to node_id). "
                                    "Use with match_index or replace_all for multi-node ops."
                                ),
                            },
                            "match_index": {
                                "type": "integer",
                                "description": "When using selector: which match (0-based). Default 0.",
                            },
                            "replace_all": {
                                "type": "boolean",
                                "description": "When using selector: apply to all matches. Default false.",
                            },
                            "code": {
                                "type": "string",
                                "description": "New code for replace/insert operations (single string, may have escaping issues with multi-line)",
                            },
                            "code_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "New code as list of lines (alternative to code, recommended for multi-line code to avoid JSON escaping issues)",
                            },
                            "position": {
                                "description": (
                                    "Position for insert/move: 'first', 'last', 'before', 'after', 'end'; "
                                    'or object {"after": N} for after 0-based sibling index N.'
                                ),
                                "oneOf": [
                                    {
                                        "type": "string",
                                        "enum": [
                                            "first",
                                            "last",
                                            "before",
                                            "after",
                                            "end",
                                        ],
                                    },
                                    {
                                        "type": "object",
                                        "properties": {"after": {"type": "integer"}},
                                        "required": ["after"],
                                    },
                                ],
                            },
                            "parent_node_id": {
                                "type": "string",
                                "description": (
                                    "Parent node ID for insert/move. Use __root__ for module-level placement."
                                ),
                            },
                            "target_node_id": {
                                "type": "string",
                                "description": "Target node ID for insert operation (insert before/after this node, alternative to parent_node_id)",
                            },
                            "start_node_id": {
                                "type": "string",
                                "description": "Start node ID for replace_range operation (first node in range to replace)",
                            },
                            "end_node_id": {
                                "type": "string",
                                "description": "End node ID for replace_range operation (last node in range to replace)",
                            },
                        },
                        "required": ["action"],
                    },
                    "description": "List of operations to apply atomically",
                },
            },
            "project_id": {
                "type": "string",
                "description": (
                    "Optional. When set with file_path, apply operations then save tree to file. "
                    "On save failure, in-memory tree is rolled back and save_error is returned."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Optional. Target file path (relative to project root). "
                    "Used with project_id for apply+save in one request."
                ),
            },
            "validate": {
                "type": "boolean",
                "default": True,
                "description": "Validate before saving (when project_id+file_path are set)",
            },
            "backup": {
                "type": "boolean",
                "default": True,
                "description": "Create backup when saving (when project_id+file_path are set)",
            },
            "commit_message": {
                "type": "string",
                "description": "Optional git commit message when saving",
            },
            "required": ["tree_id", "operations"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        operations: List[Dict[str, Any]],
        preview: bool = False,
        project_id: Optional[str] = None,
        file_path: Optional[str] = None,
        validate: bool = True,
        backup: bool = True,
        commit_message: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            t0 = time.perf_counter()
            original_tree = get_tree(tree_id)
            if not original_tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            tree_operations: List[TreeOperation] = []
            for op_dict in operations:
                action_str = op_dict.get("action")
                if action_str == "replace":
                    action = TreeOperationType.REPLACE
                elif action_str == "replace_range":
                    action = TreeOperationType.REPLACE_RANGE
                elif action_str == "insert":
                    action = TreeOperationType.INSERT
                elif action_str == "delete":
                    action = TreeOperationType.DELETE
                elif action_str == "move":
                    action = TreeOperationType.MOVE
                else:
                    return ErrorResult(
                        message=f"Invalid action: {action_str}",
                        code="INVALID_ACTION",
                        details={"action": action_str},
                    )

                pos_val = op_dict.get("position")
                position_str: Optional[str] = None
                position_after_index: Optional[int] = None
                if isinstance(pos_val, dict) and "after" in pos_val:
                    position_str = "after"
                    try:
                        position_after_index = int(pos_val["after"])
                    except (TypeError, ValueError):
                        position_after_index = None
                elif isinstance(pos_val, str):
                    position_str = pos_val

                # Resolve selector to node_ids when selector provided (no node_id)
                node_ids_to_use: List[str] = []
                op_node_id = op_dict.get("node_id")
                selector = op_dict.get("selector")
                if op_node_id:
                    node_ids_to_use = [op_node_id]
                elif selector and action in (
                    TreeOperationType.REPLACE,
                    TreeOperationType.DELETE,
                ):
                    node_ids_to_use = _resolve_selector_to_tree_node_ids(
                        original_tree,
                        selector,
                        op_dict.get("match_index"),
                        op_dict.get("replace_all", False),
                    )
                    if not node_ids_to_use:
                        return ErrorResult(
                            message=f"Selector matched no nodes: {selector}",
                            code="SELECTOR_NO_MATCH",
                            details={"selector": selector},
                        )
                else:
                    node_ids_to_use = [op_dict.get("node_id", "")]

                for nid in node_ids_to_use:
                    tree_operations.append(
                        TreeOperation(
                            action=action,
                            node_id=nid,
                            code=op_dict.get("code"),
                            code_lines=op_dict.get("code_lines"),
                            position=position_str,
                            position_after_index=position_after_index,
                            parent_node_id=op_dict.get("parent_node_id"),
                            target_node_id=op_dict.get("target_node_id"),
                            start_node_id=op_dict.get("start_node_id"),
                            end_node_id=op_dict.get("end_node_id"),
                        )
                    )

            original_code = original_tree.module.code
            logger.info(
                "[TIMING] command=cst_modify_tree step=convert_ops elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )
            t_mod = time.perf_counter()
            modified_tree = modify_tree(tree_id, tree_operations)
            modified_code = modified_tree.module.code
            logger.info(
                "[TIMING] command=cst_modify_tree step=modify_tree elapsed_sec=%.4f total_elapsed_sec=%.4f",
                time.perf_counter() - t_mod,
                time.perf_counter() - t_start,
            )

            # If preview mode, return changes without applying
            if preview:
                from difflib import unified_diff

                diff_lines = list(
                    unified_diff(
                        original_code.splitlines(keepends=True),
                        modified_code.splitlines(keepends=True),
                        fromfile="original",
                        tofile="modified",
                        lineterm="",
                    )
                )
                diff = "".join(diff_lines)

                # Validate modified code
                validation_result = {
                    "syntax_valid": True,
                    "compiles": True,
                    "error": None,
                }
                try:
                    compile(modified_code, "<string>", "exec")
                except SyntaxError as e:
                    validation_result = {
                        "syntax_valid": False,
                        "compiles": False,
                        "error": str(e),
                        "line": e.lineno if e.lineno is not None else None,
                        "offset": e.offset if e.offset is not None else None,
                    }

                data = {
                    "success": True,
                    "preview": True,
                    "tree_id": tree_id,  # Return original tree_id in preview
                    "operations_count": len(operations),
                    "changes": [
                        {
                            "operation": op_dict.get("action"),
                            "node_id": op_dict.get("node_id")
                            or op_dict.get("start_node_id"),
                            "description": f"{op_dict.get('action')} operation",
                        }
                        for op_dict in operations
                    ],
                    "diff": diff,
                    "validation": validation_result,
                }

                return SuccessResult(data=data)

            # Build modified_nodes for verification (when multiple nodes affected)
            modified_nodes: List[Dict[str, Any]] = []
            for op in tree_operations:
                entry: Dict[str, Any] = {
                    "node_id": op.node_id,
                    "action": (
                        op.action.value
                        if hasattr(op.action, "value")
                        else str(op.action)
                    ),
                }
                if op.action == TreeOperationType.REPLACE and (
                    op.code or op.code_lines
                ):
                    entry["code"] = (
                        "\n".join(op.code_lines) if op.code_lines else (op.code or "")
                    )
                elif op.action == TreeOperationType.DELETE:
                    entry["code"] = ""
                    entry["removed"] = True
                modified_nodes.append(entry)

            # Normal mode: apply changes
            data = {
                "success": True,
                "preview": False,
                "tree_id": modified_tree.tree_id,
                "operations_applied": len(tree_operations),
                "modified_nodes": modified_nodes,
            }

            # Optional: save to file in the same request
            if project_id and file_path:
                database = self._open_database_from_config(auto_analyze=False)
                try:
                    absolute_file_path = self._resolve_file_path_from_project(
                        database, project_id, file_path
                    )
                    project = database.get_project(project_id)
                    if not project:
                        rollback_tree_to_code(tree_id, original_code)
                        return ErrorResult(
                            message=f"Project {project_id} not found",
                            code="PROJECT_NOT_FOUND",
                            details={"project_id": project_id},
                        )
                    project_root = Path(project.root_path)
                    try:
                        save_result = await asyncio.to_thread(
                            save_tree_to_file,
                            tree_id=tree_id,
                            file_path=str(absolute_file_path),
                            root_dir=project_root,
                            project_id=project_id,
                            database=database,
                            validate=validate,
                            backup=backup,
                            commit_message=commit_message,
                        )
                    except Exception as save_exc:
                        rollback_tree_to_code(tree_id, original_code)
                        data["modify_applied"] = False
                        data["save_applied"] = False
                        data["save_error"] = str(save_exc)
                        data["save_error_cause"] = str(save_exc)
                        return SuccessResult(data=data)
                    if not save_result.get("success"):
                        rollback_tree_to_code(tree_id, original_code)
                        save_err = save_result.get("error", "Save failed")
                        data["modify_applied"] = False
                        data["save_applied"] = False
                        data["save_error"] = save_err
                        data["save_error_cause"] = save_result.get(
                            "error_details", save_err
                        )
                        return SuccessResult(data=data)
                    data["save_applied"] = True
                    data["file_path"] = str(absolute_file_path)
                    if save_result.get("backup_uuid"):
                        data["backup_uuid"] = save_result["backup_uuid"]
                finally:
                    database.disconnect()

            return SuccessResult(data=data)

        except ValueError as e:
            # Extract detailed error information for better error messages
            error_msg = str(e)
            error_details = {"tree_id": tree_id, "error": error_msg}

            # Try to extract node context from error message
            if "Node" in error_msg and "was not replaced" in error_msg:
                # Parse error for additional context
                if "Node type:" in error_msg:
                    error_details["hint"] = (
                        "Check that the node is in a replaceable context (Module or IndentedBlock body)"
                    )
                if "Try using replace_range" in error_msg:
                    error_details["suggestion"] = (
                        "Consider using replace_range operation for replacing multiple statements"
                    )

            return ErrorResult(
                message=f"Invalid operation: {error_msg}",
                code="INVALID_OPERATION",
                details=error_details,
            )
        except Exception as e:
            logger.exception("cst_modify_tree failed: %s", e)
            return ErrorResult(
                message=f"cst_modify_tree failed: {e}", code="CST_MODIFY_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTModifyTreeCommand"]) -> Dict[str, Any]:
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
                "The cst_modify_tree command modifies a CST tree with atomic operations. "
                "All operations in a batch are validated before being applied. If any operation "
                "fails, all changes are rolled back and the tree remains unchanged.\n\n"
                "Operation flow:\n"
                "1. Validates tree_id exists\n"
                "2. Validates all operations (checks node_ids, code syntax)\n"
                "3. If all valid, applies all operations atomically\n"
                "4. Validates modified module (compiles it)\n"
                "5. Updates tree in memory\n"
                "6. Returns success with operations_applied count\n\n"
                "Supported Operations:\n"
                "- replace: Replace a node with new code\n"
                "  - Requires: node_id, code\n"
                "- insert: Insert a new node\n"
                "  - Requires: (parent_node_id OR target_node_id), code, position ('before' or 'after')\n"
                "  - parent_node_id: Insert at beginning/end of parent's body\n"
                "  - target_node_id: Insert before/after specific target node\n"
                "- delete: Delete a node\n"
                "  - Requires: node_id\n\n"
                "Atomicity:\n"
                "- All operations are validated before any are applied\n"
                "- If any operation fails validation, none are applied\n"
                "- If module validation fails after applying operations, tree is rolled back\n"
                "- Tree remains unchanged if any error occurs\n\n"
                "Use cases:\n"
                "- Batch modifications to code structure\n"
                "- Refactoring operations\n"
                "- Code transformations\n"
                "- Multiple related changes in one operation\n\n"
                "Important notes:\n"
                "- Operations are applied in order.\n"
                "- Use cst_save_tree to persist changes to file.\n"
                "- Tree modifications are in-memory until saved.\n"
                "- All operations must be valid for any to be applied.\n\n"
                "Batch behaviour:\n"
                "When you send multiple replace or delete operations in one request, each node "
                "is resolved in the current module by its position (from metadata). So the second "
                "and later operations see the tree after previous ops are applied; you can replace "
                "or delete several nodes in one call. Use one batch for related changes.\n\n"
                "Insert — parent_node_id:\n"
                "Must be a container node: Module, FunctionDef, or ClassDef (not the body node "
                "IndentedBlock). Use __root__ for module-level insert. To insert into a function "
                "body, use the function's node_id (FunctionDef from cst_find_node), not its "
                "IndentedBlock child."
            ),
            "parameters": {
                "tree_id": {
                    "description": "Tree ID from cst_load_file command",
                    "type": "string",
                    "required": True,
                },
                "operations": {
                    "description": "List of operations to apply atomically",
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "description": "Operation type: 'replace', 'insert', or 'delete'",
                                "type": "string",
                                "enum": ["replace", "insert", "delete"],
                            },
                            "node_id": {
                                "description": "Node ID for replace/delete operations",
                                "type": "string",
                            },
                            "code": {
                                "description": "New code for replace/insert operations (single string, must be valid Python). For multi-line code, prefer code_lines to avoid JSON escaping issues.",
                                "type": "string",
                            },
                            "code_lines": {
                                "description": "New code as list of lines (alternative to code, recommended for multi-line code). Each line is a separate array element, avoiding JSON escaping issues.",
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "position": {
                                "description": "Position for insert: 'before' or 'after' parent",
                                "type": "string",
                                "enum": ["before", "after"],
                            },
                            "parent_node_id": {
                                "description": "Parent node ID for insert operation (alternative to target_node_id)",
                                "type": "string",
                            },
                            "target_node_id": {
                                "description": "Target node ID for insert operation (insert before/after this node, alternative to parent_node_id)",
                                "type": "string",
                            },
                        },
                    },
                    "required": True,
                },
            },
            "return_value": {
                "success": {
                    "description": "Operations applied successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID (same as input)",
                        "operations_applied": "Number of operations successfully applied",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations_applied": 2,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., INVALID_OPERATION, CST_MODIFY_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Replace a function",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "replace",
                                "node_id": "function:old_function:FunctionDef:10:0-20:0",
                                "code": "def new_function():\n    return 'updated'",
                            }
                        ],
                    },
                    "explanation": (
                        "Replaces old_function with new_function. "
                        "The code must be valid Python syntax. "
                        "Operation is atomic - if code is invalid, tree remains unchanged."
                    ),
                },
                {
                    "description": "Delete a statement",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "delete",
                                "node_id": "smallstmt:Pass:15:4-15:8",
                            }
                        ],
                    },
                    "explanation": (
                        "Deletes a pass statement. "
                        "Node must exist in tree. "
                        "If node_id is invalid, operation fails and tree remains unchanged."
                    ),
                },
                {
                    "description": "Insert statement before existing code",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "insert",
                                "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
                                "code": "    logger.info('Starting processing')",
                                "position": "before",
                            }
                        ],
                    },
                    "explanation": (
                        "Inserts a logging statement at the beginning of process_data function. "
                        "Position 'before' means it will be inserted before existing function body. "
                        "Parent node must exist and be a container (function, class, etc.)."
                    ),
                },
                {
                    "description": "Insert statement after existing code",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "insert",
                                "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
                                "code": "    logger.info('Processing complete')",
                                "position": "after",
                            }
                        ],
                    },
                    "explanation": (
                        "Inserts a logging statement at the end of process_data function. "
                        "Position 'after' means it will be inserted after existing function body."
                    ),
                },
                {
                    "description": "Batch operations - multiple replacements",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "replace",
                                "node_id": "function:func1:FunctionDef:10:0-15:0",
                                "code": "def func1():\n    return 'updated1'",
                            },
                            {
                                "action": "replace",
                                "node_id": "function:func2:FunctionDef:20:0-25:0",
                                "code": "def func2():\n    return 'updated2'",
                            },
                        ],
                    },
                    "explanation": (
                        "Applies multiple replacements atomically. "
                        "If any operation fails, all operations are rolled back. "
                        "Useful for related changes that must succeed together."
                    ),
                },
                {
                    "description": "Complex batch: delete and insert",
                    "command": {
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "operations": [
                            {
                                "action": "delete",
                                "node_id": "smallstmt:old_code:15:4-15:20",
                            },
                            {
                                "action": "insert",
                                "parent_node_id": "function:main:FunctionDef:10:0-30:0",
                                "code": "    new_code()",
                                "position": "after",
                            },
                        ],
                    },
                    "explanation": (
                        "Deletes old code and inserts new code in one atomic operation. "
                        "Both operations must succeed, or both are rolled back. "
                        "Useful for refactoring where multiple changes are related."
                    ),
                },
            ],
            "error_cases": {
                "INVALID_OPERATION": {
                    "description": "Invalid operation parameters",
                    "message": "Invalid operation: {error details}",
                    "solution": (
                        "Check operation parameters:\n"
                        "- For replace: node_id must exist, code must be valid Python\n"
                        "- For delete: node_id must exist\n"
                        "- For insert: (parent_node_id OR target_node_id) must be provided, code must be valid Python, position must be 'before' or 'after'\n"
                        "All operations in a batch are validated before any are applied."
                    ),
                },
                "CST_MODIFY_ERROR": {
                    "description": "Error during tree modification",
                    "examples": [
                        {
                            "case": "Node not found",
                            "message": "cst_modify_tree failed: Node not found: {node_id}",
                            "solution": (
                                "Verify node_id is correct. "
                                "Use cst_load_file or query_cst to get valid node_ids."
                            ),
                        },
                        {
                            "case": "Invalid code syntax",
                            "message": "cst_modify_tree failed: Invalid code syntax",
                            "solution": (
                                "Ensure code is valid Python syntax. "
                                "Test code separately before using in operation."
                            ),
                        },
                        {
                            "case": "Module validation fails after modification",
                            "message": "cst_modify_tree failed: Module validation failed",
                            "solution": (
                                "The modified code results in invalid Python module. "
                                "Check that all operations together produce valid code. "
                                "Tree is automatically rolled back to original state."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Validate all operations before calling cst_modify_tree",
                "Use batch operations for related changes (atomicity)",
                "Test code syntax before using in replace/insert operations",
                "Use cst_load_file or query_cst to get valid node_ids",
                "Operations are applied in order - consider dependencies",
                "Use cst_save_tree to persist changes to file",
                "Tree modifications are in-memory until saved",
                "If any operation fails, all operations are rolled back",
            ],
        }
