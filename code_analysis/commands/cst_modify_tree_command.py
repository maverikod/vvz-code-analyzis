"""
MCP command: cst_modify_tree

Modify CST tree with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.models import TreeOperation, TreeOperationType
from ..core.cst_tree.tree_modifier import modify_tree

logger = logging.getLogger(__name__)


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
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["replace", "replace_range", "insert", "delete"],
                                "description": "Operation type",
                            },
                            "node_id": {
                                "type": "string",
                                "description": "Node ID for replace/delete operations",
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
                                "type": "string",
                                "enum": ["before", "after"],
                                "description": "Position for insert operation",
                            },
                            "parent_node_id": {
                                "type": "string",
                                "description": "Parent node ID for insert operation (alternative to target_node_id)",
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
            "required": ["tree_id", "operations"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        operations: List[Dict[str, Any]],
        **kwargs,
    ) -> SuccessResult:
        try:
            # Convert operations to TreeOperation objects
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
                else:
                    return ErrorResult(
                        message=f"Invalid action: {action_str}",
                        code="INVALID_ACTION",
                        details={"action": action_str},
                    )

                tree_operations.append(
                    TreeOperation(
                        action=action,
                        node_id=op_dict.get("node_id", ""),
                        code=op_dict.get("code"),
                        code_lines=op_dict.get("code_lines"),
                        position=op_dict.get("position"),
                        parent_node_id=op_dict.get("parent_node_id"),
                        target_node_id=op_dict.get("target_node_id"),
                        start_node_id=op_dict.get("start_node_id"),
                        end_node_id=op_dict.get("end_node_id"),
                    )
                )

            # Apply operations atomically
            tree = modify_tree(tree_id, tree_operations)

            data = {
                "success": True,
                "tree_id": tree.tree_id,
                "operations_applied": len(operations),
            }

            return SuccessResult(data=data)

        except ValueError as e:
            # Extract detailed error information for better error messages
            error_msg = str(e)
            error_details = {"tree_id": tree_id, "error": error_msg}
            
            # Try to extract node context from error message
            if "Node" in error_msg and "was not replaced" in error_msg:
                # Parse error for additional context
                if "Node type:" in error_msg:
                    error_details["hint"] = "Check that the node is in a replaceable context (Module or IndentedBlock body)"
                if "Try using replace_range" in error_msg:
                    error_details["suggestion"] = "Consider using replace_range operation for replacing multiple statements"
            
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
                "- Operations are applied in order\n"
                "- Use cst_save_tree to persist changes to file\n"
                "- Tree modifications are in-memory until saved\n"
                "- All operations must be valid for any to be applied"
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
