"""
RPC handlers for AST/CST tree query operations.

Handles query operations for AST and CST trees.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
import json
import logging
from typing import Any, Dict

from code_analysis.core.cst_tree.tree_builder import load_file_to_tree
from code_analysis.core.cst_tree.tree_finder import find_nodes
from code_analysis.core.database_client.objects.ast_cst import ASTNode, CSTNode
from code_analysis.core.database_client.objects.xpath_filter import XPathFilter

from code_analysis.core.database_client.protocol import (
    DataResult,
    ErrorResult,
    ErrorCode,
)

logger = logging.getLogger(__name__)


class _RPCHandlersASTCSTQueryMixin:
    """Mixin for AST/CST tree query operations."""

    def handle_query_ast(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle query_ast RPC method.

        Args:
            params: Dictionary with 'file_id' and 'filter' keys

        Returns:
            DataResult with list of AST nodes or ErrorResult
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

            # Get AST tree from database
            ast_tree_rows = self.driver.select(
                table_name="ast_trees",
                where={"file_id": file_id},
                order_by=["updated_at"],
                limit=1,
            )
            if not ast_tree_rows:
                return ErrorResult(
                    error_code=ErrorCode.NOT_FOUND,
                    description=f"AST tree not found for file_id={file_id}",
                )

            # Load CST tree to find nodes using XPath filter
            # AST filtering is done through CST, as XPath works with CST
            try:
                tree = load_file_to_tree(file_path)
            except Exception as e:
                logger.error(
                    f"Error loading CST tree for AST query: {e}", exc_info=True
                )
                return ErrorResult(
                    error_code=ErrorCode.DATABASE_ERROR,
                    description=f"Failed to load CST tree: {e}",
                )

            # Find nodes using XPath filter (works with CST)
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

            # Convert TreeNodeMetadata to ASTNode format
            # For each CST node found, create an AST node representation
            # AST filtering is done through CST, as XPath works with CST
            ast_nodes = []
            for metadata in metadata_list:
                # Get node code from CST tree
                node = tree.node_map.get(metadata.node_id)
                code = node.code if node and hasattr(node, "code") else metadata.code

                if code:
                    # Parse code snippet to get AST node
                    try:
                        # Try to parse as expression first (for simple expressions)
                        try:
                            node_ast = ast.parse(code, mode="eval")
                            node_ast = node_ast.body
                        except SyntaxError:
                            # If not an expression, parse as statement
                            node_ast_module = ast.parse(code, mode="exec")
                            if node_ast_module.body:
                                node_ast = node_ast_module.body[0]
                            else:
                                node_ast = ast.Expr(ast.Constant(None))

                        # Serialize AST node to JSON (ast.dump returns string)
                        node_ast_json = json.dumps(ast.dump(node_ast))
                    except (SyntaxError, ValueError) as e:
                        # If code is not valid Python, create empty AST
                        logger.warning(
                            f"Failed to parse node code to AST: {e}, code: {code[:100]}"
                        )
                        node_ast_json = json.dumps(
                            ast.dump(ast.Expr(ast.Constant(None)))
                        )
                else:
                    # No code available, create empty AST
                    node_ast_json = json.dumps(ast.dump(ast.Expr(ast.Constant(None))))

                # Create ASTNode for this specific node
                # Note: ASTNode represents a tree node with its AST representation
                ast_node = ASTNode(
                    id=None,  # Node ID, not tree ID
                    file_id=file_id,
                    project_id=file_data[0].get("project_id", ""),
                    ast_json=node_ast_json,
                    ast_hash="",  # Not needed for query results
                )
                ast_nodes.append(ast_node.to_dict())

            return DataResult(data=ast_nodes)

        except ValueError as e:
            logger.error(f"Validation error in handle_query_ast: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_query_ast: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_query_cst(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle query_cst RPC method.

        Args:
            params: Dictionary with 'file_id' and 'filter' keys

        Returns:
            DataResult with list of CST nodes or ErrorResult
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

            # Find nodes using XPath filter
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

            # Convert TreeNodeMetadata to CSTNode format
            cst_nodes = []
            for metadata in metadata_list:
                # Get node code from tree
                node = tree.node_map.get(metadata.node_id)
                code = node.code if node and hasattr(node, "code") else metadata.code

                # Create CSTNode with all metadata fields
                # Note: CSTNode represents a tree node, not the full tree
                # For query results, we include node metadata in cst_code
                cst_node = CSTNode(
                    id=None,  # Node ID in tree, not database ID
                    file_id=file_id,
                    project_id=file_data[0].get("project_id", ""),
                    cst_code=code or "",
                    cst_hash="",  # Not needed for query results
                )
                cst_nodes.append(cst_node.to_dict())

            return DataResult(data=cst_nodes)

        except ValueError as e:
            logger.error(f"Validation error in handle_query_cst: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_query_cst: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
