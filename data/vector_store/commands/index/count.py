"""
Chunk counting command with ChunkQuery support.

This command provides counting capabilities using ChunkQuery for unified
filtering across metadata, AST expressions, and search criteria.

Features:
- ChunkQuery-based filtering
- Support for including deleted records
- Accurate counting with complex filters

Architecture:
- Uses RedisMetadataFilterService for filtering
- Supports both metadata and AST-based filtering through ChunkQuery

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-15
Updated: 2024-01-15
"""

import asyncio
from typing import Dict, Any, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from vector_store.exceptions import (
    ValidationError, InvalidParamsError, CommandError
)
from chunk_metadata_adapter.chunk_query import ChunkQuery
from vector_store.services.redis_metadata_crud import RedisMetadataCRUDService


class CountCommand(Command):
    """
    Command for counting chunks using ChunkQuery.
    
    Provides unified counting interface using ChunkQuery for filtering
    across all supported query types with optional inclusion of deleted records.
    """
    
    name: str = "count"
    """Command name."""
    
    description: str = (
        "Count chunks using ChunkQuery. Uses unified ChunkQuery interface "
        "for filtering across metadata, AST expressions, and search criteria. "
        "Supports optional inclusion of deleted records in count."
    )
    """Command description."""

    def __init__(
        self,
        chunk_query: ChunkQuery,
        include_deleted: bool = False
    ) -> None:
        """
        Initialize count command.
        
        Args:
            chunk_query: Unified query object for filtering chunks to count
            include_deleted: Whether to include deleted records in count
        """
        self.chunk_query: ChunkQuery = chunk_query
        """ChunkQuery for filtering chunks to count."""
        
        self.include_deleted: bool = include_deleted
        """Whether to include deleted records."""
        
        self.metadata_service: RedisMetadataCRUDService
        """Service for metadata operations."""

    async def execute(self) -> SuccessResult:
        """
        Execute chunk counting.
        
        Performs counting based on ChunkQuery filter. Returns accurate
        count of chunks matching the query criteria.
        
        Returns:
            SuccessResult with count statistics
            
        Raises:
            ValidationError: When ChunkQuery validation fails
            CommandError: When counting operation fails
        """
        try:
            # Validate ChunkQuery
            if not self.chunk_query:
                raise InvalidParamsError("ChunkQuery is required")
            
            # Initialize service with Redis client
            from vector_store.services.redis_metadata_crud import RedisMetadataCRUDService
            import redis.asyncio as redis
            
            # Get Redis URL from config or use default
            redis_url = "redis://localhost:6380"  # Default for testing
            redis_client = redis.from_url(redis_url)
            
            self.metadata_service = RedisMetadataCRUDService(redis_client=redis_client)
            
            # Count chunks matching the query
            count = await self.metadata_service.count_chunks_by_query(
                self.chunk_query,
                include_deleted=self.include_deleted
            )
            
            return SuccessResult(data={
                "count": count,
                "filter_applied": self.chunk_query.to_dict(),
                "include_deleted": self.include_deleted
            })
            
        except (ValidationError, InvalidParamsError) as e:
            return ErrorResult(
                code="validation_error",
                message=str(e)
            )
        except Exception as e:
            return ErrorResult(
                code="count_error",
                message=f"Count operation failed: {str(e)}"
            )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Returns:
            JSON schema for parameters
        """
        return {
            "type": "object",
            "properties": {
                "chunk_query": {
                    "type": "object",
                    "description": (
                        "ChunkQuery object for filtering chunks to count. Supports "
                        "metadata filtering, AST expressions, and search criteria. "
                        "If not provided, all records will be counted."
                    ),
                    "additionalProperties": True
                },
                "include_deleted": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include records marked for deletion in the count. Default is False."
                }
            },
            "required": ["chunk_query"],
            "additionalProperties": False
        }

    @classmethod
    def get_result_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for command result.

        Returns:
            JSON schema for result
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "minimum": 0},
                        "filter_applied": {"type": "object", "additionalProperties": True},
                        "include_deleted": {"type": "boolean"}
                    },
                    "required": ["count", "filter_applied", "include_deleted"]
                }
            },
            "required": ["success", "data"]
        }
    @classmethod
    def get_error_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for error responses.

        Returns:
            JSON schema for errors
        """
        return super().get_error_schema([
            "invalid_params", "validation_error", "count_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When ChunkQuery format is invalid"},
            {"code": "validation_error", "description": "ChunkQuery validation failed", "when": "When ChunkQuery fails validation"},
            {"code": "count_error", "description": "Count operation failed", "when": "When vector store operation fails"}
        ]
        
        examples = {
            "success": {
                "success": True,
                "data": {
                    "count": 1250,
                    "filter_applied": {"metadata_filter": {"category": {"$eq": "programming"}}},
                    "include_deleted": False
                }
            },
            "error": {
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid ChunkQuery format",
                    "data": {"chunk_query": {"invalid_field": "value"}}
                }
            }
        }
        
        return {
            "name": cls.name,
            "description": cls.__doc__,
            "params": cls.get_schema(),
            "result_schema": cls.get_result_schema(),
            "error_schema": cls.get_error_schema(),
            "error_codes": error_codes,
            "examples": examples
        }
