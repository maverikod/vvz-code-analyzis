"""
Count chunks command for simplified API.

This command counts chunks using the new simplified VectorStoreService.
It accepts ChunkQuery data in serialized form.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, Any

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, SearchError,
    VectorStoreServiceError, UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import CountResult
from mcp_proxy_adapter.commands.result import ErrorResult
from chunk_metadata_adapter.chunk_query import ChunkQuery

logger = logging.getLogger(__name__)


class CountChunksCommand(BaseVectorStoreCommand):
    """
    Count chunks using simplified API.
    
    This command accepts ChunkQuery data in serialized form and uses
    the new simplified VectorStoreService.count() method.
    
    Parameters:
        query (object, required): ChunkQuery data in serialized form
            - Same filtering options as search_chunks
            - Returns only count without loading data
            - More efficient for counting operations
    
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "count": 42
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
        # Count by UUID
        {
            "query": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
        
        # Count by type
        {
            "query": {
                "type": "DocBlock"
            }
        }
        
        # Count with complex filter
        {
            "query": {
                "type": "DocBlock",
                "category": "test",
                "language": "en"
            }
        }
        
        # Count including soft-deleted
        {
            "query": {
                "type": "DocBlock",
                "is_deleted": true
            }
        }
        
        # Count with text search
        {
            "query": {
                "search_query": "python programming"
            }
        }
        
        # Count with vector search
        {
            "query": {
                "embedding": [0.1, 0.2, 0.3, ...]
            }
        }
        
        # Count with AST filter
        {
            "query": {
                "filter_expr": "type = 'DocBlock' AND quality_score > 0.8"
            }
        }
        
        # Count with tags
        {
            "query": {
                "tags": ["python", "tutorial"]
            }
        }
    """

    name = "count_chunks"
    result_class = CountResult

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
                            "description": "Count by specific UUID"
                        },
                        "search_query": {
                            "type": "string",
                            "description": "Text search query for counting"
                        },
                        "embedding": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Vector for similarity counting"
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
                        "is_deleted": {
                            "type": "boolean",
                            "description": "Include soft-deleted records"
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
                        "count": {"type": "integer", "minimum": 0}
                    },
                    "required": ["count"]
                }
            },
            "required": ["success", "data"]
        }

    async def execute(self, query: Dict[str, Any]) -> CountResult:
        """
        Execute count chunks command.

        Args:
            query: ChunkQuery data in serialized form

        Returns:
            CountResult with count of matching chunks

        Raises:
            InvalidParamsError: If query parameter is missing or invalid
            ValidationError: If query data fails validation
            SearchError: If count operation fails
        """
        self._start_execution()
        
        try:
            # Validate input parameters
            if not query:
                raise InvalidParamsError("query parameter is required")
            
            if not isinstance(query, dict):
                raise InvalidParamsError("query must be an object")
            
            self.logger.debug(f"Count chunks with query: {query}")
            
            # Deserialize query data to ChunkQuery
            try:
                chunk_query = ChunkQuery(**query)
            except Exception as e:
                raise ValidationError(f"Invalid query data: {str(e)}")
            
            # Use simplified API
            count = await self.vector_store_service.count(chunk_query)
            
            self.logger.info(f"Count completed: {count} chunks found")
            
            return CountResult(count=count)
            
        except (InvalidParamsError, ValidationError, SearchError) as e:
            self.logger.error(f"Count chunks failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during count: {e}")
            raise SearchError(f"Unexpected error: {str(e)}")
