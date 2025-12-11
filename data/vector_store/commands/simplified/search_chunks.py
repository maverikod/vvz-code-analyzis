"""
Search chunks command for simplified API.

This command searches chunks using the new simplified VectorStoreService.
It accepts ChunkQuery data in serialized form.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, Any, List

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, SearchError,
    VectorStoreServiceError, UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import SearchResult
from mcp_proxy_adapter.commands.result import ErrorResult
from chunk_metadata_adapter.chunk_query import ChunkQuery

logger = logging.getLogger(__name__)


class SearchChunksCommand(BaseVectorStoreCommand):
    """
    Search chunks using simplified API.
    
    This command accepts ChunkQuery data in serialized form and uses
    the new simplified VectorStoreService.search() method.
    
    Parameters:
        query (object, required): ChunkQuery data in serialized form
            - Can include search_query, embedding, metadata filters
            - Supports all ChunkQuery fields for filtering
            - See ChunkQuery for complete field definitions
    
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "chunks": [
                        {
                            "uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "body": "Found content",
                            "similarity": 0.85
                        }
                    ],
                    "total_found": 1
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
        # Search by UUID
        {
            "query": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
        
        # Text search
        {
            "query": {
                "search_query": "python programming",
                "max_results": 10
            }
        }
        
        # Metadata filtering
        {
            "query": {
                "type": "DocBlock",
                "category": "test",
                "language": "en"
            }
        }
        
        # Complex filtering
        {
            "query": {
                "search_query": "tutorial",
                "type": "DocBlock",
                "tags": ["python"],
                "max_results": 5,
                "min_score": 0.7
            }
        }
        
        # Include soft-deleted records
        {
            "query": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "is_deleted": true
            }
        }
        
        # Vector search
        {
            "query": {
                "embedding": [0.1, 0.2, 0.3, ...],
                "max_results": 5
            }
        }
        
        # Hybrid search
        {
            "query": {
                "search_query": "machine learning",
                "hybrid_search": true,
                "bm25_weight": 0.6,
                "semantic_weight": 0.4,
                "max_results": 10
            }
        }
        
        # AST-based filtering
        {
            "query": {
                "filter_expr": "type = 'DocBlock' AND category = 'test' AND quality_score > 0.8"
            }
        }
    """

    name = "search_chunks"
    result_class = SearchResult

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
                            "description": "Search by specific UUID"
                        },
                        "search_query": {
                            "type": "string",
                            "description": "Text search query for BM25 search"
                        },
                        "embedding": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Vector for similarity search"
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
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Maximum number of results"
                        },
                        "min_score": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Minimum similarity score"
                        },
                        "is_deleted": {
                            "type": "boolean",
                            "description": "Include soft-deleted records"
                        },
                        "hybrid_search": {
                            "type": "boolean",
                            "description": "Enable hybrid search"
                        },
                        "bm25_weight": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "BM25 weight for hybrid search"
                        },
                        "semantic_weight": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Semantic weight for hybrid search"
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
                        "chunks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "format": "uuid"},
                                    "body": {"type": "string"},
                                    "similarity": {"type": "number"},
                                    "type": {"type": "string"},
                                    "category": {"type": "string"},
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                },
                                "additionalProperties": True
                            }
                        },
                        "total_count": {"type": "integer", "minimum": 0}
                    },
                    "required": ["chunks", "total_count"]
                }
            },
            "required": ["success", "data"]
        }

    async def execute(self, query: Dict[str, Any]) -> SearchResult:
        """
        Execute search chunks command.

        Args:
            query: ChunkQuery data in serialized form

        Returns:
            SearchResult with found chunks

        Raises:
            InvalidParamsError: If query parameter is missing or invalid
            ValidationError: If query data fails validation
            SearchError: If search operation fails
        """
        self._start_execution()
        
        try:
            # Validate input parameters
            if not query:
                raise InvalidParamsError("query parameter is required")
            
            if not isinstance(query, dict):
                raise InvalidParamsError("query must be an object")
            
            self.logger.debug(f"Search chunks with query: {query}")
            
            # Deserialize query data to ChunkQuery
            try:
                chunk_query = ChunkQuery(**query)
            except Exception as e:
                raise ValidationError(f"Invalid query data: {str(e)}")
            
            # Use simplified API
            results = await self.vector_store_service.search(chunk_query)
            
            # Ensure results is a list
            if results is None:
                results = []
            
            self.logger.info(f"Search completed: {len(results)} results found")
            
            return SearchResult(
                chunks=results,
                total_count=len(results)
            )
            
        except (InvalidParamsError, ValidationError, SearchError) as e:
            self.logger.error(f"Search chunks failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during search: {e}")
            raise SearchError(f"Unexpected error: {str(e)}")
