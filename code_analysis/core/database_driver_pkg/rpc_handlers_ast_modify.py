"""
RPC handlers for AST tree modify operations.

Handles modify operations for AST trees.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from code_analysis.core.cst_tree.models import TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree
from code_analysis.core.cst_tree.tree_finder import find_nodes
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.database_client.objects.ast_cst import ASTNode
from code_analysis.core.database_client.objects.tree_action import TreeAction
from code_analysis.core.database_client.objects.xpath_filter import XPathFilter

from .result import DataResult, ErrorResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class _RPCHandlersASTModifyMixin:
    """Mixin for AST tree modify operations."""

    def handle_modify_ast(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle modify_ast RPC method.

        Args:
            params: Dictionary with 'file_id', 'filter', 'action', and 'nodes' keys

        Returns:
            DataResult with modified AST tree or ErrorResult
        """
        try:
            file_id = params.get("file_id")
            if file_id is None:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="file_id parameter is required",
                )

            filter_dict = params.get("filter")
            if not filter_dict:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="filter parameter is required",
                )

            action_str = params.get("action")
            if not action_str:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="action parameter is required",
                )

            # Validate action
            try:
                action = TreeAction(action_str)
            except ValueError:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Invalid action: {action_str}",
                )

            xpath_filter = XPathFilter.from_dict(filter_dict)

            # Get file path from database
            file_data = self.driver.select(
                table_name="files",
                where={"id": file_id},
                limit=1,
            )
            if not file_data:
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description=f"File not found for file_id={file_id}",
                )

            file_path = file_data[0].get("path")
            if not file_path:
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description=f"File path not found for file_id={file_id}",
                )

            project_id = file_data[0].get("project_id", "")

            # Strategy: Source Code -> CST -> Modify -> Source Code -> AST
            # We need the actual source file to preserve formatting and comments
            # AST cannot be reliably restored to source code (loses formatting/comments)
            source_path = Path(file_path)
            if not source_path.exists():
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description=f"Source file not found: {file_path}. AST modification requires the actual source file to preserve formatting and comments.",
                )

            # Load CST tree from source file
            # This reads the file and parses it to CST, preserving formatting and comments
            try:
                tree = load_file_to_tree(str(source_path))
            except Exception as e:
                logger.error(
                    f"Error loading CST tree from file for AST modification: {e}",
                    exc_info=True,
                )
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Failed to load CST tree from file: {e}",
                )

            # Find nodes matching filter
            metadata_list = find_nodes(
                tree.tree_id,
                query=xpath_filter.selector,
                search_type="xpath",
                node_type=xpath_filter.node_type,
                name=xpath_filter.name,
                qualname=xpath_filter.qualname,
                start_line=xpath_filter.start_line,
                end_line=xpath_filter.end_line,
            )

            if not metadata_list:
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description="No nodes found matching filter",
                )

            # Convert action to TreeOperationType
            if action == TreeAction.REPLACE:
                op_type = TreeOperationType.REPLACE
            elif action == TreeAction.DELETE:
                op_type = TreeOperationType.DELETE
            elif action == TreeAction.INSERT:
                op_type = TreeOperationType.INSERT
            else:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Unsupported action: {action}",
                )

            # Build operations list
            nodes = params.get("nodes", [])
            operations = []

            for metadata in metadata_list:
                if action == TreeAction.DELETE:
                    operations.append(
                        TreeOperation(
                            action=op_type,
                            node_id=metadata.node_id,
                        )
                    )
                elif action == TreeAction.REPLACE:
                    if not nodes:
                        return ErrorResult(
                            error_code=ErrorCode.VALIDATION_ERROR,
                            description="nodes parameter required for REPLACE action",
                        )
                    # Use first node for replacement
                    node_data = nodes[0] if nodes else {}
                    # For AST nodes, prefer cst_code if available (from unparsed AST)
                    # Otherwise try to unparse from ast_json
                    if "cst_code" in node_data:
                        code = node_data["cst_code"]
                    elif "ast_json" in node_data:
                        # Try to restore code from AST JSON
                        # Note: This is best-effort, may lose formatting
                        return ErrorResult(
                            error_code=ErrorCode.VALIDATION_ERROR,
                            description="AST nodes for replacement must provide cst_code. Use query_cst to get nodes with code, or provide cst_code directly.",
                        )
                    else:
                        code = ""
                    operations.append(
                        TreeOperation(
                            action=op_type,
                            node_id=metadata.node_id,
                            code=code,
                        )
                    )
                elif action == TreeAction.INSERT:
                    if not nodes:
                        return ErrorResult(
                            error_code=ErrorCode.VALIDATION_ERROR,
                            description="nodes parameter required for INSERT action",
                        )
                    # Insert all nodes
                    for node_data in nodes:
                        # For AST nodes, prefer cst_code if available (from unparsed AST)
                        # Otherwise try to unparse from ast_json
                        if "cst_code" in node_data:
                            code = node_data["cst_code"]
                        elif "ast_json" in node_data:
                            # Try to restore code from AST JSON
                            # Note: This is best-effort, may lose formatting
                            return ErrorResult(
                                error_code=ErrorCode.VALIDATION_ERROR,
                                description="AST nodes for insertion must provide cst_code. Use query_cst to get nodes with code, or provide cst_code directly.",
                            )
                        else:
                            code = ""
                        operations.append(
                            TreeOperation(
                                action=op_type,
                                node_id=metadata.node_id,
                                code=code,
                                position="after",  # Default position
                            )
                        )

            # Apply modifications to CST
            modified_tree = modify_tree(tree.tree_id, operations)

            # Get modified source code from CST
            modified_source = modified_tree.module.code

            # Convert modified source back to AST
            try:
                modified_ast_tree = ast.parse(modified_source, filename=str(file_path))
            except SyntaxError as e:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description=f"Modified code has syntax errors: {e}",
                )

            # Serialize AST to JSON
            ast_json = json.dumps(ast.dump(modified_ast_tree))
            ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()
            file_mtime = time.time()

            # Save modified AST to database
            try:
                # Check if AST tree exists
                existing_ast = self.driver.select(
                    table_name="ast_trees",
                    where={"file_id": file_id},
                    order_by=["updated_at"],
                    limit=1,
                )
                if existing_ast:
                    # Update existing
                    self.driver.update(
                        table_name="ast_trees",
                        where={"id": existing_ast[0]["id"]},
                        data={
                            "ast_json": ast_json,
                            "ast_hash": ast_hash,
                            "file_mtime": file_mtime,
                            "updated_at": time.time(),
                        },
                    )
                else:
                    # Insert new
                    self.driver.insert(
                        table_name="ast_trees",
                        data={
                            "file_id": file_id,
                            "project_id": project_id,
                            "ast_json": ast_json,
                            "ast_hash": ast_hash,
                            "file_mtime": file_mtime,
                        },
                    )
            except Exception as e:
                logger.error(f"Error saving modified AST: {e}", exc_info=True)
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Failed to save modified AST: {e}",
                )

            # Return modified AST node
            # Get AST tree ID after save
            saved_ast = self.driver.select(
                table_name="ast_trees",
                where={"file_id": file_id},
                order_by=["updated_at"],
                limit=1,
            )
            ast_id = saved_ast[0]["id"] if saved_ast else None

            ast_node = ASTNode(
                id=ast_id,
                file_id=file_id,
                project_id=project_id,
                ast_json=ast_json,
                ast_hash=ast_hash,
                file_mtime=time.time(),
            )

            return DataResult(data=ast_node.to_dict())

        except ValueError as e:
            logger.error(f"Validation error in handle_modify_ast: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_modify_ast: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
