"""
RPC method handlers for database driver operations.

Handles individual RPC method calls by delegating to driver.
Uses BaseRequest and BaseResult classes for type safety and validation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver
from .request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)
from .result import DataResult, ErrorResult, SuccessResult
from .rpc_protocol import ErrorCode

logger = logging.getLogger(__name__)


class RPCHandlers:
    """RPC method handlers for database operations.

    All handlers use BaseRequest and BaseResult classes for type safety
    and proper validation.
    """

    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize RPC handlers.

        Args:
            driver: Database driver instance
        """
        self.driver = driver

    def handle_create_table(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle create_table RPC method.

        Args:
            params: Dictionary with 'schema' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            schema = params.get("schema")
            if not schema:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="schema parameter is required",
                )
            success = self.driver.create_table(schema)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_create_table: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_drop_table(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle drop_table RPC method.

        Args:
            params: Dictionary with 'table_name' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            table_name = params.get("table_name")
            if not table_name:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="table_name parameter is required",
                )
            success = self.driver.drop_table(table_name)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_drop_table: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_insert(self, request: InsertRequest) -> SuccessResult | ErrorResult:
        """Handle insert RPC method using InsertRequest.

        Args:
            request: InsertRequest instance

        Returns:
            SuccessResult with row_id or ErrorResult
        """
        try:
            request.validate()
            row_id = self.driver.insert(request.table_name, request.data)
            return SuccessResult(data={"row_id": row_id})
        except ValueError as e:
            logger.error(f"Validation error in handle_insert: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_insert: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_update(self, request: UpdateRequest) -> SuccessResult | ErrorResult:
        """Handle update RPC method using UpdateRequest.

        Args:
            request: UpdateRequest instance

        Returns:
            SuccessResult with affected_rows or ErrorResult
        """
        try:
            request.validate()
            affected_rows = self.driver.update(
                request.table_name, request.where, request.data
            )
            return SuccessResult(data={"affected_rows": affected_rows})
        except ValueError as e:
            logger.error(f"Validation error in handle_update: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_update: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_delete(self, request: DeleteRequest) -> SuccessResult | ErrorResult:
        """Handle delete RPC method using DeleteRequest.

        Args:
            request: DeleteRequest instance

        Returns:
            SuccessResult with affected_rows or ErrorResult
        """
        try:
            request.validate()
            affected_rows = self.driver.delete(request.table_name, request.where)
            return SuccessResult(data={"affected_rows": affected_rows})
        except ValueError as e:
            logger.error(f"Validation error in handle_delete: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_delete: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_select(self, request: SelectRequest) -> DataResult | ErrorResult:
        """Handle select RPC method using SelectRequest.

        Args:
            request: SelectRequest instance

        Returns:
            DataResult with rows or ErrorResult
        """
        try:
            request.validate()
            rows = self.driver.select(
                table_name=request.table_name,
                where=request.where,
                columns=request.columns,
                limit=request.limit,
                offset=request.offset,
                order_by=request.order_by,
            )
            return DataResult(data=rows)
        except ValueError as e:
            logger.error(f"Validation error in handle_select: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            logger.error(f"Error in handle_select: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_execute(
        self, params: Dict[str, Any]
    ) -> SuccessResult | DataResult | ErrorResult:
        """Handle execute RPC method.

        Args:
            params: Dictionary with 'sql' and optional 'params' keys

        Returns:
            SuccessResult, DataResult, or ErrorResult
        """
        try:
            sql = params.get("sql")
            if not sql:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="sql parameter is required",
                )
            params_tuple = params.get("params")
            result = self.driver.execute(sql, params_tuple)
            # If result contains data, return DataResult, otherwise SuccessResult
            if "data" in result:
                return DataResult(data=result["data"])
            return SuccessResult(data=result)
        except Exception as e:
            logger.error(f"Error in handle_execute: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_begin_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle begin_transaction RPC method.

        Args:
            params: Empty dictionary (no parameters)

        Returns:
            SuccessResult with transaction_id or ErrorResult
        """
        try:
            transaction_id = self.driver.begin_transaction()
            return SuccessResult(data={"transaction_id": transaction_id})
        except Exception as e:
            logger.error(f"Error in handle_begin_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_commit_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle commit_transaction RPC method.

        Args:
            params: Dictionary with 'transaction_id' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            transaction_id = params.get("transaction_id")
            if not transaction_id:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="transaction_id parameter is required",
                )
            success = self.driver.commit_transaction(transaction_id)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_commit_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_rollback_transaction(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Handle rollback_transaction RPC method.

        Args:
            params: Dictionary with 'transaction_id' key

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            transaction_id = params.get("transaction_id")
            if not transaction_id:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="transaction_id parameter is required",
                )
            success = self.driver.rollback_transaction(transaction_id)
            return SuccessResult(data={"success": success})
        except Exception as e:
            logger.error(f"Error in handle_rollback_transaction: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.TRANSACTION_ERROR,
                description=str(e),
            )

    def handle_get_table_info(self, params: Dict[str, Any]) -> DataResult | ErrorResult:
        """Handle get_table_info RPC method.

        Args:
            params: Dictionary with 'table_name' key

        Returns:
            DataResult with table info or ErrorResult
        """
        try:
            table_name = params.get("table_name")
            if not table_name:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="table_name parameter is required",
                )
            info = self.driver.get_table_info(table_name)
            return DataResult(data=info)
        except Exception as e:
            logger.error(f"Error in handle_get_table_info: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )

    def handle_sync_schema(self, params: Dict[str, Any]) -> SuccessResult | ErrorResult:
        """Handle sync_schema RPC method.

        Args:
            params: Dictionary with 'schema_definition' and optional 'backup_dir' keys

        Returns:
            SuccessResult with sync results or ErrorResult
        """
        try:
            schema_definition = params.get("schema_definition")
            if not schema_definition:
                return ErrorResult(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    description="schema_definition parameter is required",
                )
            backup_dir = params.get("backup_dir")
            result = self.driver.sync_schema(schema_definition, backup_dir)
            return SuccessResult(data=result)
        except Exception as e:
            logger.error(f"Error in handle_sync_schema: {e}", exc_info=True)
            return ErrorResult(
                error_code=ErrorCode.SCHEMA_ERROR,
                description=str(e),
            )

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

            # Import here to avoid circular dependencies
            from ...database_client.objects.xpath_filter import XPathFilter

            # Validate filter (will be used when AST filtering is implemented)
            _ = XPathFilter.from_dict(filter_dict)

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
            ast_tree_data = ast_tree_rows[0]

            # For now, return the AST tree data
            # TODO: Implement proper AST node filtering using XPath filter
            # This requires parsing AST JSON and filtering nodes
            # For CST, we can use CSTQuery engine, but for AST we need different approach
            return DataResult(data=[ast_tree_data])

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

            # Import here to avoid circular dependencies
            from ...database_client.objects.xpath_filter import XPathFilter
            from ...cst_tree.tree_builder import load_file_to_tree
            from ...cst_tree.tree_finder import find_nodes

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
            from ...database_client.objects.ast_cst import CSTNode

            cst_nodes = []
            for metadata in metadata_list:
                # Get node code from tree
                node = tree.node_map.get(metadata.node_id)
                code = node.code if node else None

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

            # Import here to avoid circular dependencies
            from ...database_client.objects.tree_action import TreeAction
            from ...database_client.objects.xpath_filter import XPathFilter
            from ...cst_tree.tree_builder import load_file_to_tree
            from ...cst_tree.tree_finder import find_nodes
            from ...cst_tree.tree_modifier import modify_tree
            from ...cst_tree.models import TreeOperation, TreeOperationType
            import ast
            import json
            import hashlib
            import time

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
            from pathlib import Path

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
            # Use execute to call save_ast_tree method
            # Note: We need to use the database methods, but we're in driver context
            # For now, we'll use direct SQL
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
            from ...database_client.objects.ast_cst import ASTNode

            ast_node = ASTNode(
                id=existing_ast[0]["id"] if existing_ast else None,
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

            # Import here to avoid circular dependencies
            from ...database_client.objects.tree_action import TreeAction
            from ...database_client.objects.xpath_filter import XPathFilter
            from ...cst_tree.tree_builder import load_file_to_tree
            from ...cst_tree.tree_finder import find_nodes
            from ...cst_tree.tree_modifier import modify_tree
            from ...cst_tree.models import TreeOperation, TreeOperationType

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
                    for node_data in nodes:
                        code = node_data.get("cst_code", "")
                        operations.append(
                            TreeOperation(
                                action=op_type,
                                node_id=metadata.node_id,
                                code=code,
                                position="after",  # Default position
                            )
                        )

            # Apply modifications
            modified_tree = modify_tree(tree.tree_id, operations)

            # Convert modified tree to CSTNode format
            from ...database_client.objects.ast_cst import CSTNode

            cst_node = CSTNode(
                id=None,
                file_id=file_id,
                project_id=file_data[0].get("project_id", ""),
                cst_code=modified_tree.module.code,
                cst_hash="",  # Would need to compute hash
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
