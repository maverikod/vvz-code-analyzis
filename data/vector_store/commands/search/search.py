"""
Search command implementation following mcp_proxy_adapter framework.

This command provides unified search capabilities for vector store chunks.
It integrates with chunk_metadata_adapter for query validation and processing.
"""

import logging
import time
from typing import Dict, Any, Optional, List, Union

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, SearchError, 
    EmbeddingGenerationError, VectorStoreSearchError, VectorStoreHybridSearchError,
    UnexpectedError
)
from mcp_proxy_adapter.commands.result import ErrorResult

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import SearchResult
from chunk_metadata_adapter.chunk_query import ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator

logger = logging.getLogger(__name__)


class SearchCommand(BaseVectorStoreCommand):
    """
    Unified search command for vector store chunks.

    This command provides four main search capabilities:
    1. **Semantic search** - search by text string (converted to 384-dim embedding)
    2. **Vector search** - search by precomputed 384-dim embedding vector
    3. **Metadata filtering** - filter by chunk metadata fields
    4. **AST-based filtering** - advanced structured query language with operators

    The command supports hybrid search combining any of these approaches.
    At least one search method must be specified.

    Parameters:
        search_str (string, optional): Semantic search string that will be converted to 384-dimensional embedding vector
        embedding (array, optional): Precomputed 384-dim embedding vector for direct similarity search
        metadata_filter (object, optional): Metadata filter for filtering results
        ast_filter (object, optional): AST-based filter expression for advanced structured queries
        limit (integer, optional): Maximum number of results to return (default: 10)
        level_of_relevance (number, optional): Minimum similarity threshold (0.0-1.0, default: 0.0)
        offset (integer, optional): Number of results to skip for pagination (default: 0)

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "chunks": [
                        {
                            "uuid": "123e4567-e89b-12d3-a456-426614174000",
                            "body": "Found chunk content",
                            "similarity": 0.85
                        }
                    ],
                    "total_found": 1,
                    "search_params": {
                        "search_str": "machine learning",
                        "limit": 10
                    }
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "No search method specified",
                    "data": {"required_methods": ["search_str", "embedding", "metadata_filter"]}
                }
            }

    Error codes:
        | Code              | Description                    | When
        |-------------------|--------------------------------|-------------------
        | invalid_params    | Invalid parameters provided    | When parameters are invalid
        | validation_error  | Search validation failed       | When no search method specified
        | search_error      | Search operation failed        | When vector store search fails
        | embedding_error   | Embedding generation failed    | When embedding service fails

    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "chunks": [{"uuid": "123e4567-e89b-12d3-a456-426614174000", "body": "content", "similarity": 0.85}],
                    "total_found": 1
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "No search method specified",
                    "data": {"required_methods": ["search_str", "embedding", "metadata_filter"]}
                }
            }
    """

    name = "search"
    result_class = SearchResult
    
    def __init__(self, vector_store_service, **kwargs):
        """
        Initialize SearchCommand with enhanced chunk_metadata_adapter integration.

        Args:
            vector_store_service: Vector store service instance
            **kwargs: Additional keyword arguments
        """
        super().__init__(vector_store_service, **kwargs)
        
        # Initialize validator
        from vector_store.commands.command_validator import CommandValidator
        self.validator = CommandValidator()
        
        # Initialize query validator for backward compatibility
        self.query_validator = QueryValidator()

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for search command parameters.

        Returns:
            dict: JSON schema with parameter definitions and validation rules
        """
        return {
            "type": "object",
            "properties": {
                "chunk_query": {
                    "type": "object",
                    "description": "ChunkQuery object with search parameters",
                    "additionalProperties": True
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
                        "chunks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "format": "uuid"},
                                    "body": {"type": "string"},
                                    "text": {"type": "string"},
                                    "similarity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                                    "metadata": {"type": "object", "additionalProperties": True}
                                },
                                "required": ["uuid", "body"]
                            }
                        },
                        "total_found": {"type": "integer", "minimum": 0},
                        "search_params": {"type": "object", "additionalProperties": True}
                    },
                    "required": ["chunks", "total_found"]
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
            "invalid_params", "validation_error", "search_error", "embedding_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When parameters are invalid"},
            {"code": "validation_error", "description": "Search validation failed", "when": "When no search method specified"},
            {"code": "search_error", "description": "Search operation failed", "when": "When vector store search fails"},
            {"code": "embedding_error", "description": "Embedding generation failed", "when": "When embedding service fails"}
        ]
        
        examples = {
            "success": {
                "success": True,
                "data": {
                    "chunks": [{"uuid": "123e4567-e89b-12d3-a456-426614174000", "body": "content", "similarity": 0.85}],
                    "total_found": 1
                }
            },
            "error": {
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "No search method specified",
                    "data": {"required_methods": ["search_str", "embedding", "metadata_filter"]}
                }
            }
        }
        
        return super().get_metadata(error_codes, examples)

    async def execute(self, **params) -> Union[SearchResult, ErrorResult]:
        """
        Execute search command using ChunkQuery.

        Args:
            **params: Command parameters including chunk_query

        Returns:
            SearchResult with search results or ErrorResult on error
        """
        try:
            chunk_query = params.get("chunk_query")
            
            if not chunk_query:
                return ErrorResult(
                    code="invalid_params",
                    message="Parameter 'chunk_query' is required",
                    details={"params": params}
                )
            
            # ChunkQuery validation is handled by VectorStoreService
            # No need to validate here as it's already validated in the service layer
            
            # Perform search using ChunkQuery
            results = await self.vector_store_service.search(chunk_query)
            
            return SearchResult(
                chunks=results,
                total_count=len(results),
                metadata={"chunk_query": str(chunk_query)}
            )
        except InvalidParamsError as e:
            msg = str(e)
            if "embedding" in msg and ("384" in msg or "values" in msg):
                return ErrorResult(
                    code="invalid_params",
                    message="Invalid embedding format",
                    details=getattr(e, "data", None)
                )
            return ErrorResult(
                code="invalid_params",
                message=msg if msg else "Invalid parameters",
                details=getattr(e, "data", None)
            )
        except ValidationError as e:
            return ErrorResult(
                code="validation_error",
                message=str(e) if str(e) else "Validation error",
                details=getattr(e, "data", None)
            )
        except CommandError as e:
            msg = str(e)
            if "Multiple records found" in msg:
                return ErrorResult(
                    code="search_error",
                    message="Multiple records found for the same uuid",
                    details=getattr(e, "data", None)
                )
            return ErrorResult(
                code="search_error",
                message="Internal error",
                details=getattr(e, "data", None)
            )
        except SearchError as e:
            return ErrorResult(
                code="search_error",
                message=str(e),
                details=getattr(e, "details", None)
            )
        except VectorStoreSearchError as e:
            return ErrorResult(
                code="vector_search_error",
                message=str(e),
                details=getattr(e, "details", None)
            )
        except VectorStoreHybridSearchError as e:
            return ErrorResult(
                code="hybrid_search_error",
                message=str(e),
                details=getattr(e, "details", None)
            )
        except EmbeddingGenerationError as e:
            return ErrorResult(
                code="embedding_error",
                message=str(e),
                details=getattr(e, "details", None)
            )
        except Exception as e:
            return ErrorResult(
                code="unexpected_error",
                message=f"Unexpected error during search: {e}",
                details={"error": str(e)}
            )


def make_search(vector_store_service) -> SearchCommand:
    """
    Factory function to create SearchCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured SearchCommand instance
    """
    return SearchCommand(vector_store_service)
