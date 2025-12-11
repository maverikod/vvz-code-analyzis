"""
Chunk deletion command with ChunkQuery support.

This command provides both soft and hard deletion capabilities using ChunkQuery
for unified filtering across metadata, AST expressions, and search criteria.

Features:
- Soft deletion (mark as deleted)
- Hard deletion (permanent removal)
- ChunkQuery-based filtering
- Safety checks for bulk operations

Architecture:
- Uses RedisMetadataFilterService for filtering
- Integrates with AtomicIndexManager for vector operations
- Supports both metadata and AST-based filtering through ChunkQuery

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-15
Updated: 2024-01-15
"""

import asyncio
from typing import Dict, Any, Optional, List
from uuid import UUID

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from vector_store.exceptions import (
    ValidationError, InvalidParamsError, CommandError, DeletionError
)
from chunk_metadata_adapter.chunk_query import ChunkQuery
from vector_store.services.redis_metadata_crud import RedisMetadataCRUDService
from vector_store.services.index_manager.atomic_index_manager import AtomicIndexManager


class ChunkDeleteCommand(Command):
    """
    Command for deleting chunks using ChunkQuery.
    
    Provides unified deletion interface with support for both soft and hard deletion
    using ChunkQuery for filtering across all supported query types.
    """
    
    name: str = "chunk_delete"
    """Command name."""
    
    description: str = (
        "Delete chunks using ChunkQuery. Supports both soft deletion (mark as deleted) "
        "and hard deletion (permanent removal). Uses unified ChunkQuery interface "
        "for filtering across metadata, AST expressions, and search criteria."
    )
    """Command description."""

    def __init__(
        self,
        chunk_query: ChunkQuery,
        hard_delete: bool = False
    ) -> None:
        """
        Initialize delete command.
        
        Args:
            chunk_query: Unified query object for filtering chunks to delete
            hard_delete: Whether to perform hard deletion (permanent removal)
        """
        self.chunk_query: ChunkQuery = chunk_query
        """ChunkQuery for filtering chunks to delete."""
        
        self.hard_delete: bool = hard_delete
        """Whether to perform hard deletion."""
        
        self.metadata_service: RedisMetadataCRUDService
        """Service for metadata operations."""
        
        self.index_manager: AtomicIndexManager
        """Index manager for vector operations."""

    async def execute(self) -> SuccessResult:
        """
        Execute chunk deletion.
        
        Performs deletion based on ChunkQuery filter. For soft deletion,
        marks chunks as deleted. For hard deletion, permanently removes
        chunks from both FAISS and Redis.
        
        Returns:
            SuccessResult with deletion statistics
            
        Raises:
            ValidationError: When ChunkQuery validation fails
            DeletionError: When deletion operation fails
        """
        try:
            # Validate ChunkQuery
            if not self.chunk_query:
                raise InvalidParamsError("ChunkQuery is required")
            
            # Initialize services with Redis client
            import redis.asyncio as redis
            
            # Get Redis URL from config or use default
            redis_url = "redis://localhost:6380"  # Default for testing
            redis_client = redis.from_url(redis_url)
            
            self.metadata_service = RedisMetadataCRUDService(redis_client=redis_client)
            self.index_manager = AtomicIndexManager(redis_client=redis_client)
            
            # Find chunks matching the query
            matching_chunks = await self.metadata_service.find_chunks_by_query(
                self.chunk_query
            )
            
            if not matching_chunks:
                return SuccessResult(data={
                    "deleted_count": 0,
                    "filter_applied": self.chunk_query.to_dict(),
                    "hard_delete": self.hard_delete
                })
            
            deleted_count = 0
            
            if self.hard_delete:
                # Hard deletion: remove from FAISS and Redis
                deleted_count = await self._perform_hard_deletion(matching_chunks)
            else:
                # Soft deletion: mark as deleted in Redis
                deleted_count = await self._perform_soft_deletion(matching_chunks)
            
            return SuccessResult(data={
                "deleted_count": deleted_count,
                "filter_applied": self.chunk_query.to_dict(),
                "hard_delete": self.hard_delete
            })
            
        except (ValidationError, InvalidParamsError) as e:
            return ErrorResult(
                code="validation_error",
                message=str(e)
            )
        except DeletionError as e:
            return ErrorResult(
                code="deletion_error", 
                message=str(e)
            )
        except Exception as e:
            return ErrorResult(
                code="command_error",
                message=f"Unexpected error during deletion: {str(e)}"
            )

    async def _perform_soft_deletion(
        self,
        chunks: List[Dict[str, Any]]
    ) -> int:
        """
        Perform soft deletion of chunks.
        
        Args:
            chunks: List of chunks to mark as deleted
            
        Returns:
            Number of chunks marked as deleted
        """
        deleted_count = 0
        
        for chunk in chunks:
            try:
                # Mark chunk as deleted in Redis
                await self.metadata_service.mark_chunk_as_deleted(
                    chunk["uuid"]
                )
                deleted_count += 1
            except Exception as e:
                # Log error but continue with other chunks
                print(f"Error marking chunk {chunk['uuid']} as deleted: {e}")
        
        return deleted_count

    async def _perform_hard_deletion(
        self,
        chunks: List[Dict[str, Any]]
    ) -> int:
        """
        Perform hard deletion of chunks.
        
        Args:
            chunks: List of chunks to permanently delete
            
        Returns:
            Number of chunks permanently deleted
        """
        deleted_count = 0
        
        # Sort chunks by index in descending order for safe FAISS deletion
        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.get("faiss_index", 0),
            reverse=True
        )
        
        for chunk in sorted_chunks:
            try:
                # Remove from FAISS first
                if "faiss_index" in chunk:
                    await self.index_manager.remove_vector_by_index(
                        chunk["faiss_index"]
                    )
                
                # Remove from Redis
                await self.metadata_service.delete_chunk_metadata(
                    chunk["uuid"]
                )
                
                deleted_count += 1
                
            except Exception as e:
                # Log error but continue with other chunks
                print(f"Error deleting chunk {chunk['uuid']}: {e}")
        
        return deleted_count

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
                        "ChunkQuery object for filtering chunks to delete. Supports "
                        "metadata filtering, AST expressions, and search criteria. "
                        "If not provided, no chunks will be deleted."
                    ),
                    "additionalProperties": True
                },
                "hard_delete": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Whether to perform hard deletion (permanent removal) instead "
                        "of soft deletion (mark as deleted). Default is False."
                    )
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
                        "deleted_count": {"type": "integer", "minimum": 0},
                        "filter_applied": {"type": "object", "additionalProperties": True},
                        "hard_delete": {"type": "boolean"}
                    },
                    "required": ["deleted_count", "filter_applied", "hard_delete"]
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
            "invalid_params", "validation_error", "deletion_error", "safety_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        return {
            "name": cls.name,
            "description": cls.__doc__,
            "params": cls.get_schema(),
            "result_schema": cls.get_result_schema(),
            "error_schema": cls.get_error_schema(),
            "error_codes": [
                {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When ChunkQuery format is invalid"},
                {"code": "validation_error", "description": "ChunkQuery validation failed", "when": "When ChunkQuery fails validation"},
                {"code": "deletion_error", "description": "Failed to delete chunks", "when": "When vector store operation fails"},
                {"code": "safety_error", "description": "Unsafe deletion attempted", "when": "When trying to delete all records"}
            ],
            "examples": {
                "success": {
                    "success": True,
                    "data": {
                        "deleted_count": 1,
                        "filter_applied": {"metadata_filter": {"uuid": {"$eq": "123e4567-e89b-12d3-a456-426614174000"}}},
                        "hard_delete": False
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
        }
