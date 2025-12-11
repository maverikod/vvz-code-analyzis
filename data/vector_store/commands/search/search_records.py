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
                "search_str": {
                    "type": "string",
                    "description": (
                        "Semantic search string that will be converted to 384-dimensional embedding vector "
                        "and matched by vector similarity. Use for natural language queries. "
                        "Example: 'machine learning algorithms', 'python programming tips'"
                    )
                },
                "embedding": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 384,
                    "maxItems": 384,
                    "description": (
                        "Precomputed 384-dim embedding vector for direct similarity search. "
                        "Use when you already have the embedding vector. "
                        "Must be exactly 384 float values."
                    )
                },
                "metadata_filter": {
                    "type": "object",
                    "description": (
                        "Metadata filter for filtering results. Supports: $eq, $in, $range, $gte, $lte, $gt, $lt "
                        "for scalar and array fields. Can be combined with search_str or embedding."
                    ),
                    "additionalProperties": True
                },
                "ast_filter": {
                    "type": "object",
                    "description": (
                        "AST-based filter expression for advanced filtering. Provides structured query language "
                        "with operators like AND, OR, NOT, comparison operators, and field-specific filters. "
                        "Example: {\"operator\": \"AND\", \"left\": {\"field\": \"category\", \"operator\": \"=\", \"value\": \"technical\"}, "
                        "\"right\": {\"field\": \"language\", \"operator\": \"=\", \"value\": \"en\"}}"
                    ),
                    "additionalProperties": True
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 10,
                    "description": "Maximum number of results to return (1-1000)"
                },
                "level_of_relevance": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                    "description": "Minimum similarity threshold (0.0-1.0)"
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Number of results to skip for pagination"
                },
                "search_query": {
                    "type": "string",
                    "description": "BM25 search query for keyword-based search"
                },
                "search_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fields to search in for BM25 (e.g., ['text', 'body'])"
                },
                "bm25_k1": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 3.0,
                    "default": 1.2,
                    "description": "BM25 k1 parameter for term frequency saturation"
                },
                "bm25_b": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.75,
                    "description": "BM25 b parameter for length normalization"
                },
                "hybrid_search": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable hybrid search combining BM25 and semantic search"
                },
                "bm25_weight": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                    "description": "Weight for BM25 scores in hybrid search"
                },
                "semantic_weight": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.5,
                    "description": "Weight for semantic scores in hybrid search"
                },
                "min_score": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                    "description": "Minimum score threshold for results"
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 10,
                    "description": "Maximum number of results to return"
                }
            },
            "required": [],
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

    async def execute(
        self,
        search_str: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        ast_filter: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        level_of_relevance: Optional[float] = None,
        offset: int = 0,
        search_query: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        bm25_k1: Optional[float] = None,
        bm25_b: Optional[float] = None,
        hybrid_search: Optional[bool] = None,
        bm25_weight: Optional[float] = None,
        semantic_weight: Optional[float] = None,
        min_score: Optional[float] = None,
        max_results: Optional[int] = None,
        **params
    ) -> Union[SearchResult, ErrorResult]:
        """
        Execute search command.

        Args:
            search_str: Semantic search string
            embedding: Precomputed embedding vector
            metadata_filter: Metadata filter for filtering
            limit: Maximum number of results
            level_of_relevance: Minimum similarity threshold
            offset: Number of results to skip
            **params: Additional parameters

        Returns:
            SearchResult with search results or ErrorResult on error
        """
        try:
            if limit is None:
                limit = 10
            if level_of_relevance is None:
                level_of_relevance = 0.0
            self.validator.validate_search_advanced_params(search_str, embedding, limit, level_of_relevance, offset)
            if not search_str and not embedding and metadata_filter is None and ast_filter is None and not search_query:
                return ErrorResult(
                    code="validation_error",
                    message="Missing required parameter: provide at least one of search_str, embedding, metadata_filter, ast_filter, or search_query",
                    details={"required_methods": ["search_str", "embedding", "metadata_filter", "ast_filter", "search_query"]}
                )
            if metadata_filter:
                await self.validator.validate_filter_simple(metadata_filter)
            if ast_filter:
                await self.validator.validate_ast_filter(ast_filter)
            results = await self._perform_search(
                search_str=search_str,
                embedding=embedding,
                metadata_filter=metadata_filter,
                ast_filter=ast_filter,
                limit=limit,
                level_of_relevance=level_of_relevance,
                offset=offset,
                search_query=search_query,
                search_fields=search_fields,
                bm25_k1=bm25_k1,
                bm25_b=bm25_b,
                hybrid_search=hybrid_search,
                bm25_weight=bm25_weight,
                semantic_weight=semantic_weight,
                min_score=min_score,
                max_results=max_results
            )
            
            # Check if _perform_search returned ErrorResult
            if isinstance(results, ErrorResult):
                return results
                
            return SearchResult(
                chunks=results["chunks"],
                total_count=results["total_found"],
                metadata={
                    "search_params": {
                        "search_str": search_str,
                        "embedding_provided": embedding is not None,
                        "metadata_filter": metadata_filter,
                        "ast_filter": ast_filter,
                        "limit": limit,
                        "level_of_relevance": level_of_relevance,
                        "offset": offset
                    }
                }
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
                details={"search_params": {
                    "search_str": search_str,
                    "embedding_provided": embedding is not None,
                    "metadata_filter": metadata_filter,
                    "limit": limit,
                    "level_of_relevance": level_of_relevance,
                    "offset": offset
                }}
            )



    async def _perform_search(
        self,
        search_str: Optional[str],
        embedding: Optional[List[float]],
        metadata_filter: Optional[Dict[str, Any]],
        ast_filter: Optional[Dict[str, Any]],
        limit: int,
        level_of_relevance: float,
        offset: int,
        search_query: Optional[str] = None,
        search_fields: Optional[List[str]] = None,
        bm25_k1: Optional[float] = None,
        bm25_b: Optional[float] = None,
        hybrid_search: Optional[bool] = None,
        bm25_weight: Optional[float] = None,
        semantic_weight: Optional[float] = None,
        min_score: Optional[float] = None,
        max_results: Optional[int] = None
    ) -> Union[Dict[str, Any], ErrorResult]:
        """
        Perform the actual search operation.

        Args:
            search_str: Search string
            embedding: Embedding vector
            metadata_filter: Metadata filter
            limit: Maximum results
            level_of_relevance: Similarity threshold
            offset: Results offset

        Returns:
            Search results with chunks and total count or ErrorResult on failure
        """
        try:
            # Import ChunkQuery here to avoid circular imports
            from chunk_metadata_adapter.chunk_query import ChunkQuery
            
            # Create ChunkQuery based on search parameters
            chunk_query = ChunkQuery()
            
            if search_str:
                chunk_query.text = search_str
                # Generate embedding for search_str if not provided
                if not embedding and hasattr(self.vector_store_service, 'embedding_service') and self.vector_store_service.embedding_service:
                    try:
                        search_embedding = await self.vector_store_service.embedding_service.get_embedding(search_str)
                        chunk_query.embedding = search_embedding
                        logger.info(f"Generated embedding for search string: {len(search_embedding)} values")
                    except EmbeddingGenerationError as e:
                        logger.error(f"Failed to generate embedding for search string: {e}")
                        raise e
                    except Exception as e:
                        logger.error(f"Unexpected error generating embedding: {e}")
                        raise EmbeddingGenerationError(f"Failed to generate embedding for search: {e}", text=search_str)
                elif embedding:
                    chunk_query.embedding = embedding
            elif embedding:
                chunk_query.embedding = embedding
                
            # Set BM25 parameters
            if search_query:
                chunk_query.search_query = search_query
            if search_fields:
                chunk_query.search_fields = search_fields
            if bm25_k1 is not None:
                chunk_query.bm25_k1 = bm25_k1
            if bm25_b is not None:
                chunk_query.bm25_b = bm25_b
            if hybrid_search is not None:
                chunk_query.hybrid_search = hybrid_search
            if bm25_weight is not None:
                chunk_query.bm25_weight = bm25_weight
            if semantic_weight is not None:
                chunk_query.semantic_weight = semantic_weight
            if min_score is not None:
                chunk_query.min_score = min_score
            if max_results is not None:
                chunk_query.max_results = max_results
                
            if metadata_filter:
                # Set specific fields in ChunkQuery instead of using non-existent metadata field
                logger.info(f"Setting metadata_filter fields in ChunkQuery: {metadata_filter}")
                for field_name, field_value in metadata_filter.items():
                    if hasattr(chunk_query, field_name):
                        setattr(chunk_query, field_name, field_value)
                        logger.info(f"Set field '{field_name}' = '{field_value}' in ChunkQuery")
                    else:
                        logger.warning(f"Field '{field_name}' not found in ChunkQuery, skipping")
                
                # Debug: Check what fields are actually set
                logger.info(f"ChunkQuery model_dump after setting fields: {chunk_query.model_dump()}")
            if ast_filter:
                chunk_query.filter_expr = ast_filter
            
            # Use vector store service for search
            logger.debug(f"Calling vector_store_service.search with include_vectors=True")
            
            # Check if hybrid search is requested
            if hybrid_search and search_query:
                logger.info("Performing hybrid search with BM25 and semantic search")
                results = await self.vector_store_service.hybrid_search(chunk_query)
            else:
                results = await self.vector_store_service.search(
                    chunk_query=chunk_query,
                    limit=limit,
                    offset=offset,
                    include_vectors=True,
                    include_deleted=False
                )
            
            logger.debug(f"Search returned {len(results)} results")

            return {
                "chunks": results,
                "total_found": len(results)
            }

        except SearchError as e:
            raise e
        except VectorStoreSearchError as e:
            raise e
        except VectorStoreHybridSearchError as e:
            raise e
        except EmbeddingGenerationError as e:
            raise e
        except Exception as e:
            raise UnexpectedError(f"Unexpected error during search operation", original_error=e)


def make_search(vector_store_service) -> SearchCommand:
    """
    Factory function to create SearchCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured SearchCommand instance
    """
    return SearchCommand(vector_store_service)
