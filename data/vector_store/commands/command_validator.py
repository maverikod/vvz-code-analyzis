"""
Command parameter and data validator for vector store commands.

Provides the CommandValidator for parameter, ChunkQuery, and SemanticChunk validation.

Features:
- Parameter validation
- ChunkQuery validation
- SemanticChunk validation
- UUID validation
- Security validation

Architecture:
- Used by command classes for input validation

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import uuid
from typing import Dict, List, Any, Optional, Union
from vector_store.exceptions import ValidationError, InvalidParamsError
from mcp_proxy_adapter.commands.result import ErrorResult

class CommandValidator:
    """
    Validator for command parameters and data.
    
    Provides comprehensive validation for command parameters,
    ChunkQuery objects, and SemanticChunk data.
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger("vector_store.commands.validator")
    
    def validate_search_params(
        self,
        params: Dict[str, Any]
    ) -> bool:
        """
        Validate search parameters.
        
        Args:
            params: Parameters to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidParamsError: If parameters are invalid
        """
        required_params = ["search_str"]
        missing_params = [p for p in required_params if p not in params or params[p] is None]
        if missing_params:
            raise InvalidParamsError(
                f"Missing required search parameters: {', '.join(missing_params)}"
            )
        if not isinstance(params["search_str"], str):
            raise InvalidParamsError(
                "Parameter 'search_str' must be a string"
            )
        if "limit" in params and params["limit"] is not None:
            if not isinstance(params["limit"], int) or params["limit"] <= 0:
                raise InvalidParamsError(
                    "Parameter 'limit' must be a positive integer"
                )
        return True
    
    def validate_search_advanced_params(
        self,
        search_str: Optional[str],
        embedding: Optional[List[float]],
        limit: int,
        level_of_relevance: float,
        offset: int
    ) -> None:
        """
        Validate advanced search parameters.
        
        Args:
            search_str: Search string to validate
            embedding: Embedding vector to validate
            limit: Limit to validate
            level_of_relevance: Similarity threshold to validate
            offset: Offset to validate
            
        Raises:
            InvalidParamsError: If parameters are invalid
        """
        # Validate search_str
        if search_str is not None and not isinstance(search_str, str):
            raise InvalidParamsError("Parameter 'search_str' must be a string")

        # Validate embedding
        if embedding is not None:
            if not isinstance(embedding, list):
                raise InvalidParamsError("Parameter 'embedding' must be an array")
            if len(embedding) != 384:
                raise InvalidParamsError(f"Parameter 'embedding' must have exactly 384 values, got {len(embedding)}")
            if not all(isinstance(x, (int, float)) for x in embedding):
                raise InvalidParamsError("Parameter 'embedding' must contain only numbers")

        # Validate limit
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise InvalidParamsError("Parameter 'limit' must be an integer between 1 and 1000")

        # Validate level_of_relevance
        if not isinstance(level_of_relevance, (int, float)) or level_of_relevance < 0.0 or level_of_relevance > 1.0:
            raise InvalidParamsError("Parameter 'level_of_relevance' must be a number between 0.0 and 1.0")

        # Validate offset
        if not isinstance(offset, int) or offset < 0:
            raise InvalidParamsError("Parameter 'offset' must be a non-negative integer")
    
    def validate_create_params(
        self,
        params: Dict[str, Any]
    ) -> bool:
        """
        Validate create parameters.
        
        Args:
            params: Parameters to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidParamsError: If parameters are invalid
        """
        required_params = ["chunks"]
        missing_params = [p for p in required_params if p not in params or params[p] is None]
        if missing_params:
            raise InvalidParamsError(
                f"Missing required create parameters: {', '.join(missing_params)}"
            )
        if not isinstance(params["chunks"], list):
            raise InvalidParamsError(
                "Parameter 'chunks' must be a list"
            )
        if len(params["chunks"]) == 0:
            raise InvalidParamsError(
                "Parameter 'chunks' cannot be empty"
            )
        return True
    
    def validate_delete_params(
        self,
        params: Dict[str, Any]
    ) -> bool:
        """
        Validate delete parameters.
        
        Args:
            params: Parameters to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidParamsError: If parameters are invalid
        """
        required_params = ["uuids"]
        missing_params = [p for p in required_params if p not in params or params[p] is None]
        if missing_params:
            raise InvalidParamsError(
                f"Missing required delete parameters: {', '.join(missing_params)}"
            )
        if not isinstance(params["uuids"], list):
            raise InvalidParamsError(
                "Parameter 'uuids' must be a list"
            )
        if len(params["uuids"]) == 0:
            raise InvalidParamsError(
                "Parameter 'uuids' cannot be empty"
            )
        return True
    
    def validate_count_params(
        self,
        metadata_filter: Optional[Dict[str, Any]],
        include_deleted: bool
    ) -> None:
        """
        Validate count parameters.
        
        Args:
            metadata_filter: Filter to validate
            include_deleted: Include deleted flag to validate
            
        Raises:
            InvalidParamsError: If parameters are invalid
        """
        # Validate metadata_filter
        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise InvalidParamsError("Parameter 'metadata_filter' must be an object")

        # Validate include_deleted
        if not isinstance(include_deleted, bool):
            raise InvalidParamsError("Parameter 'include_deleted' must be a boolean")
    
    def validate_uuids(
        self,
        uuids: List[str]
    ) -> bool:
        """
        Validate list of UUIDs.
        
        Args:
            uuids: List of UUID strings to validate
            
        Returns:
            True if valid
            
        Raises:
            InvalidParamsError: If any UUID is invalid
        """
        if not isinstance(uuids, list):
            raise InvalidParamsError(
                "Parameter 'uuids' must be a list"
            )
        for i, uuid_str in enumerate(uuids):
            try:
                uuid.UUID(uuid_str)
            except (ValueError, TypeError):
                raise InvalidParamsError(
                    f"Invalid UUID at index {i}: {uuid_str}"
                )
        return True
    
    async def validate_filter_simple(
        self,
        metadata_filter: Dict[str, Any]
    ) -> None:
        """
        Simple filter validation.
        
        Args:
            metadata_filter: Filter to validate
            
        Raises:
            ValidationError: If filter is invalid
        """
        if not isinstance(metadata_filter, dict):
            raise ValidationError(
                "Filter validation failed: Filter must be a dictionary",
                data={"filter": metadata_filter}
            )
    
    async def validate_filter_advanced(
        self,
        metadata_filter: Dict[str, Any]
    ) -> Optional[ErrorResult]:
        """
        Advanced filter validation using ChunkQuery.
        
        Args:
            metadata_filter: Filter to validate
            
        Returns:
            None if valid, ErrorResult if invalid
        """
        try:
            # Import ChunkQuery here to avoid circular imports
            from chunk_metadata_adapter.chunk_query import ChunkQuery
            
            # Create ChunkQuery with metadata field for validation
            chunk_query = ChunkQuery(metadata=metadata_filter)
            
            # Validate query
            validation_result = chunk_query.validate()
            if not validation_result.is_valid:
                return ErrorResult(
                    code="validation_error",
                    message=f"Invalid filter expression: {validation_result.errors}",
                    details={"filter": metadata_filter, "details": validation_result.errors}
                )

        except Exception as e:
            return ErrorResult(
                code="validation_error",
                message=f"Invalid filter expression: {e}",
                details={"filter": metadata_filter}
            )
        
        return None
    
    async def validate_ast_filter(
        self,
        ast_filter: Dict[str, Any]
    ) -> None:
        """
        Validate AST-based filter expression.
        
        Args:
            ast_filter: AST filter to validate
            
        Raises:
            ValidationError: If AST filter is invalid
        """
        if not isinstance(ast_filter, dict):
            raise ValidationError(
                "AST filter validation failed: Filter must be a dictionary",
                data={"ast_filter": ast_filter}
            )
        
        # Basic structure validation
        if "operator" not in ast_filter:
            raise ValidationError(
                "AST filter validation failed: Missing 'operator' field",
                data={"ast_filter": ast_filter}
            )
        
        # Validate operator
        valid_operators = ["AND", "OR", "NOT", "=", "!=", ">", ">=", "<", "<=", "IN", "NOT_IN"]
        operator = ast_filter.get("operator")
        if operator not in valid_operators:
            raise ValidationError(
                f"AST filter validation failed: Invalid operator '{operator}'. Valid operators: {valid_operators}",
                data={"ast_filter": ast_filter}
            )
        
        # Validate field for comparison operators
        if operator in ["=", "!=", ">", ">=", "<", "<=", "IN", "NOT_IN"]:
            if "field" not in ast_filter:
                raise ValidationError(
                    "AST filter validation failed: Missing 'field' for comparison operator",
                    data={"ast_filter": ast_filter}
                )
            if "value" not in ast_filter:
                raise ValidationError(
                    "AST filter validation failed: Missing 'value' for comparison operator",
                    data={"ast_filter": ast_filter}
                )
        
        # Validate left/right for logical operators
        if operator in ["AND", "OR"]:
            if "left" not in ast_filter or "right" not in ast_filter:
                raise ValidationError(
                    "AST filter validation failed: Missing 'left' or 'right' for logical operator",
                    data={"ast_filter": ast_filter}
                )
            # Recursively validate left and right
            await self.validate_ast_filter(ast_filter["left"])
            await self.validate_ast_filter(ast_filter["right"])
        
        # Validate operand for NOT operator
        if operator == "NOT":
            if "operand" not in ast_filter:
                raise ValidationError(
                    "AST filter validation failed: Missing 'operand' for NOT operator",
                    data={"ast_filter": ast_filter}
                )
            # Recursively validate operand
            await self.validate_ast_filter(ast_filter["operand"]) 