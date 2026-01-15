"""
RPC handlers for CST tree modify operations.

Handles modify operations for CST trees.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict

from code_analysis.core.cst_tree.models import TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree
from code_analysis.core.cst_tree.tree_finder import find_nodes
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.database_client.objects.ast_cst import CSTNode
from code_analysis.core.database_client.objects.tree_action import TreeAction
from code_analysis.core.database_client.objects.xpath_filter import XPathFilter

from .result import DataResult, ErrorResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class _RPCHandlersCSTModifyMixin:
    """Mixin for CST tree modify operations."""

    def handle_modify_cst(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle modify_cst RPC method.

        Args:
            params: Dictionary with 'file_id', 'filter', 'action', and 'nodes' keys

        Returns:
            DataResult with modified CST tree or ErrorResult
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

            # Load CST tree
            tree = load_file_to_tree(file_path)

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
                    code = node_data.get("cst_code", "")
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
                    # For INSERT, metadata.node_id is the target node (insert before/after it)
                    # We need to use target_node_id instead of node_id
                    for node_data in nodes:
                        code = node_data.get("cst_code", "")
                        position = node_data.get(
                            "position", "after"
                        )  # Allow position from node_data
                        operations.append(
                            TreeOperation(
                                action=op_type,
                                node_id="",  # node_id not used for INSERT
                                code=code,
                                target_node_id=metadata.node_id,  # Use target_node_id for INSERT
                                position=position,  # Use position from node_data or default "after"
                            )
                        )

            # Apply modifications
            modified_tree = modify_tree(tree.tree_id, operations)

            # Convert modified tree to CSTNode format
            modified_cst_code = modified_tree.module.code
            cst_hash = hashlib.sha256(modified_cst_code.encode()).hexdigest()

            cst_node = CSTNode(
                id=None,
                file_id=file_id,
                project_id=file_data[0].get("project_id", ""),
                cst_code=modified_cst_code,
                cst_hash=cst_hash,
            )

            return DataResult(data=cst_node.to_dict())

        except ValueError as e:
            logger.error(f"Validation error in handle_modify_cst: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_modify_cst: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
