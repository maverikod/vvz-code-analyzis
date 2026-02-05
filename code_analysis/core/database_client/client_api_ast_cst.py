"""
Client API mixin for AST/CST tree operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List

from .objects.ast_cst import ASTNode, CSTNode
from .objects.tree_action import TreeAction
from .objects.xpath_filter import XPathFilter
from .protocol import ErrorCode, RPCResponse
from .result import Result


class _ClientAPIASTCSTMixin:
    """Mixin for AST/CST tree operations."""

    def query_ast(self, file_id: int, filter: XPathFilter) -> Result[List[ASTNode]]:
        """Query AST tree nodes using XPath filter.

        Args:
            file_id: File identifier
            filter: XPath filter for node selection

        Returns:
            Result containing list of matching AST nodes
        """
        params: Dict[str, Any] = {
            "file_id": file_id,
            "filter": filter.to_dict(),
        }
        response = self.rpc_client.call("query_ast", params)
        return self._parse_result_response(response, List[ASTNode])

    def query_cst(self, file_id: int, filter: XPathFilter) -> Result[List[CSTNode]]:
        """Query CST tree nodes using XPath filter.

        Args:
            file_id: File identifier
            filter: XPath filter for node selection

        Returns:
            Result containing list of matching CST nodes
        """
        params: Dict[str, Any] = {
            "file_id": file_id,
            "filter": filter.to_dict(),
        }
        response = self.rpc_client.call("query_cst", params)
        return self._parse_result_response(response, List[CSTNode])

    def modify_ast(
        self,
        file_id: int,
        filter: XPathFilter,
        action: TreeAction,
        nodes: List[ASTNode],
    ) -> Result[ASTNode]:
        """Modify AST tree nodes.

        Args:
            file_id: File identifier
            filter: XPath filter for node selection
            action: Action to perform (REPLACE, DELETE, INSERT)
            nodes: List of nodes for modification (required for REPLACE/INSERT)

        Returns:
            Result containing modified AST tree
        """
        params: Dict[str, Any] = {
            "file_id": file_id,
            "filter": filter.to_dict(),
            "action": action.value,
            "nodes": [node.to_dict() for node in nodes],
        }
        response = self.rpc_client.call("modify_ast", params)
        return self._parse_result_response(response, ASTNode)

    def modify_cst(
        self,
        file_id: int,
        filter: XPathFilter,
        action: TreeAction,
        nodes: List[CSTNode],
    ) -> Result[CSTNode]:
        """Modify CST tree nodes.

        Args:
            file_id: File identifier
            filter: XPath filter for node selection
            action: Action to perform (REPLACE, DELETE, INSERT)
            nodes: List of nodes for modification (required for REPLACE/INSERT)

        Returns:
            Result containing modified CST tree
        """
        params: Dict[str, Any] = {
            "file_id": file_id,
            "filter": filter.to_dict(),
            "action": action.value,
            "nodes": [node.to_dict() for node in nodes],
        }
        response = self.rpc_client.call("modify_cst", params)
        return self._parse_result_response(response, CSTNode)

    def _parse_result_response(
        self, response: RPCResponse, data_type: Any
    ) -> Result[Any]:
        """Parse RPC response into Result object.

        Args:
            response: RPC response object
            data_type: Expected data type (for deserialization)

        Returns:
            Result object
        """
        if response.is_error():
            error = response.error
            if error:
                error_code = error.code
                description = error.message
                details = error.data
            else:
                error_code = ErrorCode.INTERNAL_ERROR
                description = "Unknown error"
                details = None
            return Result.error(
                error_code=error_code, description=description, details=details
            )

        # Extract data from result
        result_data = response.result
        if result_data and isinstance(result_data, dict):
            # Handle both SuccessResult and DataResult formats
            data = result_data.get("data")
        else:
            data = None

        # Deserialize data if needed
        if data and data_type:
            if data_type == List[ASTNode]:
                data = [ASTNode.from_dict(item) for item in data]
            elif data_type == List[CSTNode]:
                data = [CSTNode.from_dict(item) for item in data]
            elif data_type == ASTNode:
                data = ASTNode.from_dict(data)
            elif data_type == CSTNode:
                data = CSTNode.from_dict(data)

        return Result.create_success(data=data)
