"""
Delete chunks command for simplified API.

This command deletes chunks using the new simplified VectorStoreService.
It accepts ChunkQuery data in serialized form and performs soft delete.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, Any

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, DeletionError,
    VectorStoreServiceError, UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import DeleteResult
from mcp_proxy_adapter.commands.result import ErrorResult
from chunk_metadata_adapter.chunk_query import ChunkQuery

logger = logging.getLogger(__name__)


class DeleteChunksCommand(BaseVectorStoreCommand):
    """
    Delete chunks using simplified API.
    
    This command accepts ChunkQuery data in serialized form and uses
    the new simplified VectorStoreService.delete() method.
    Performs soft delete by default (sets is_deleted=true).
    
    Parameters:
        query (object, required): ChunkQuery data in serialized form
            - Same filtering options as search_chunks
            - Deletes all chunks matching the filter
            - Uses soft delete (is_deleted=true)
    
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "deleted": true,
                    "deleted_count": 1
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid query: at least one search parameter required"
                }
            }
    
    Examples:
        # Delete by UUID
        {
            "query": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
        
        # Delete by type
        {
            "query": {
                "type": "DocBlock"
            }
        }
        
        # Delete with complex filter
        {
            "query": {
                "type": "DocBlock",
                "category": "test",
                "language": "en"
            }
        }
        
        # Delete specific tags
        {
            "query": {
                "tags": ["deprecated", "old"]
            }
        }
        
        # Delete with text search
        {
            "query": {
                "search_query": "outdated content"
            }
        }
        
        # Delete with AST filter
        {
            "query": {
                "filter_expr": "type = 'DocBlock' AND quality_score < 0.3"
            }
        }
        
        # Delete with date filter
        {
            "query": {
                "created_at": "2024-01-01T00:00:00Z"
            }
        }
        
        # Delete with multiple conditions
        {
            "query": {
                "type": "DocBlock",
                "category": "deprecated",
                "language": "en"
            }
        }
    """

    name = "delete_chunks"
    result_class = DeleteResult

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
                "query": {
                    "type": "object",
                    "description": "ChunkQuery data in serialized form",
                    "properties": {
                        "uuid": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Delete by specific UUID"
                        },
                        "search_query": {
                            "type": "string",
                            "description": "Text search query for deletion"
                        },
                        "embedding": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Vector for similarity deletion"
                        },
                        "type": {
                            "type": "string",
                            "description": "Filter by chunk type"
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter by category"
                        },
                        "language": {
                            "type": "string",
                            "description": "Filter by language"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags"
                        },
                        "filter_expr": {
                            "type": "string",
                            "description": "AST-based filter expression"
                        }
                    },
                    "additionalProperties": True
                }
            },
            "required": ["query"],
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
                        "deleted_uuids": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"}
                        },
                        "deleted_count": {"type": "integer", "minimum": 0},
                        "soft_delete": {"type": "boolean"}
                    },
                    "required": ["deleted_uuids", "deleted_count", "soft_delete"]
                }
            },
            "required": ["success", "data"]
        }

    async def execute(self, query: Dict[str, Any]) -> DeleteResult:
        """
        Execute delete chunks command.

        Args:
            query: ChunkQuery data in serialized form

        Returns:
            DeleteResult with deletion status

        Raises:
            InvalidParamsError: If query parameter is missing or invalid
            ValidationError: If query data fails validation
            DeletionError: If deletion operation fails
        """
        self._start_execution()
        
        try:
            # Validate input parameters
            if not query:
                raise InvalidParamsError("query parameter is required")
            
            if not isinstance(query, dict):
                raise InvalidParamsError("query must be an object")
            
            self.logger.debug(f"Delete chunks with query: {query}")
            
            # Deserialize query data to ChunkQuery
            try:
                chunk_query = ChunkQuery(**query)
            except Exception as e:
                raise ValidationError(f"Invalid query data: {str(e)}")
            
            # Use simplified API
            result = await self.vector_store_service.delete(chunk_query)
            
            # Get count of deleted chunks for reporting
            deleted_count = await self.vector_store_service.count(chunk_query)
            
            self.logger.info(f"Delete completed: {deleted_count} chunks deleted")
            
            return DeleteResult(
                deleted_uuids=[],  # We don't have UUIDs from count operation
                deleted_count=deleted_count,
                soft_delete=True
            )
            
        except (InvalidParamsError, ValidationError, DeletionError) as e:
            self.logger.error(f"Delete chunks failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during deletion: {e}")
            raise DeletionError(f"Unexpected error: {str(e)}")
