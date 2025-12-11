"""
BM25 Search Service for integration with embed_client.

This module provides the BM25 search service that integrates
with embed_client to get pre-computed tokens and BM25Index
for document ranking and search.

Features:
- Integration with embed_client for token extraction
- BM25 search with relevance ranking
- Integration with chunk_metadata_adapter SearchResult
- Redis-based index persistence and caching
- Support for hybrid search with semantic scores

Architecture:
- BM25Index: Core BM25 algorithm implementation
- embed_client integration: Token extraction
- Redis client: Index persistence and caching
- Async operations: Non-blocking search and indexing
- Error handling: Graceful degradation and recovery

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime

from embed_client.async_client import EmbeddingServiceAsyncClient, EmbeddingServiceError
from chunk_metadata_adapter import SearchResult, HybridSearchConfig, HybridSearchHelper

from .bm25_index import BM25Index, BM25IndexError, BM25SearchError, BM25SearchResult
from .bm25_index_decl import BM25IndexStats
from vector_store.exceptions import (
    BM25ServiceError, BM25IndexError as VectorStoreBM25IndexError, 
    BM25SearchError as VectorStoreBM25SearchError, BM25ConfigurationError,
    UnexpectedError
)

logger = logging.getLogger(__name__)


class BM25SearchService:
    """
    BM25 search service for integration with embed_client.
    
    This service provides high-level interface for BM25 operations including
    document indexing, search, and integration with existing vector store components.
    
    Features:
    - Document indexing with automatic token extraction from embed_client
    - BM25 search with relevance ranking
    - Integration with chunk_metadata_adapter SearchResult
    - Redis-based index persistence and caching
    - Support for hybrid search with semantic scores
    - Batch processing for large datasets
    - Performance monitoring and optimization
    
    Architecture:
    - BM25Index: Core BM25 algorithm implementation
    - embed_client: Token extraction and processing
    - Redis client: Index persistence and caching
    - Async operations: Non-blocking search and indexing
    - Error handling: Graceful degradation and recovery
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize BM25 search service.
        
        Args:
            config: Service configuration including BM25 parameters,
                   embed_client settings, and Redis connection details
        """
        self.config: Dict[str, Any] = config
        """Service configuration."""
        
        # BM25 index
        bm25_config = config.copy()
        if config.get("redis_client"):
            bm25_config["redis_client"] = config["redis_client"]
        self.bm25_index: BM25Index = BM25Index(bm25_config)
        """BM25 index instance for document storage and search."""
        
        # Embedding client for token extraction
        self.embedding_client: Optional[EmbeddingServiceAsyncClient] = None
        """Embedding client for token extraction."""
        
        # Redis client
        self.redis_client: Any = config.get("redis_client")
        """Redis client for index persistence and caching."""
        
        # Embedding service configuration
        self.embedding_base_url: str = config.get("embedding_base_url", "http://localhost")
        """Base URL for embedding service."""
        
        self.embedding_port: int = config.get("embedding_port", 8001)
        """Port for embedding service."""
        
        self.embedding_timeout: float = config.get("embedding_timeout", 30.0)
        """Timeout for embedding service requests."""
        
        # Service state
        self.is_initialized: bool = False
        """Whether the service has been properly initialized."""
        
        # Performance tracking
        self.stats: Dict[str, Any] = {
            "total_searches": 0,
            "total_documents_indexed": 0,
            "total_errors": 0,
            "avg_search_time": 0.0,
            "avg_indexing_time": 0.0,
            "last_search_time": 0.0,
            "last_indexing_time": 0.0
        }
        
        logger.info("BM25SearchService initialized")
    
    async def initialize(self) -> None:
        """
        Initialize BM25 search service.
        
        Sets up BM25 index, embedding client, and Redis connection.
        Loads existing index data if available.
        
        Raises:
            BM25IndexError: If initialization fails
        """
        try:
            # Initialize embedding client
            self.embedding_client = EmbeddingServiceAsyncClient(
                base_url=self.embedding_base_url,
                port=self.embedding_port,
                timeout=self.embedding_timeout
            )
            await self.embedding_client.__aenter__()
            
            # Test embedding service connection
            try:
                health = await self.embedding_client.health()
                logger.info(f"Embedding service health: {health}")
            except EmbeddingServiceError as e:
                logger.warning(f"Embedding service health check failed: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error during embedding service health check: {e}")
            
            # Load existing index from Redis if available
            if self.redis_client:
                try:
                    await self.bm25_index.load_from_redis()
                    logger.info("Loaded existing BM25 index from Redis")
                except BM25IndexError as e:
                    logger.warning(f"Failed to load BM25 index from Redis: {e}")
                except Exception as e:
                    logger.warning(f"Unexpected error loading BM25 index from Redis: {e}")
            
            self.is_initialized = True
            logger.info("BM25SearchService initialized successfully")
            
        except BM25ServiceError as e:
            logger.error(f"BM25 service error during initialization: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error initializing BM25SearchService: {e}")
            raise BM25ServiceError(f"Failed to initialize BM25SearchService: {e}") from e
    
    async def _get_tokens_from_text(self, text: str) -> List[str]:
        """
        Get BM25 tokens from text using embed_client.
        
        Args:
            text: Input text to tokenize
            
        Returns:
            List of BM25 tokens
            
        Raises:
            BM25IndexError: If token extraction fails
        """
        try:
            if not self.embedding_client:
                raise BM25IndexError("Embedding client not initialized")
            
            # Get tokens from embedding service
            result = await self.embedding_client.cmd("embed", params={"texts": [text]})
            
            # Extract BM25 tokens from response
            bm25_tokens = self.embedding_client.extract_bm25_tokens(result)
            
            if not bm25_tokens or not bm25_tokens[0]:
                logger.warning(f"No BM25 tokens extracted for text: {text[:50]}...")
                return []
            
            return bm25_tokens[0]
            
        except EmbeddingServiceError as e:
            logger.error(f"Embedding service error: {e}")
            raise BM25IndexError(f"Embedding service error: {e}") from e
        except Exception as e:
            logger.error(f"Failed to get tokens from text: {e}")
            raise BM25IndexError(f"Failed to get tokens from text: {e}") from e
    
    async def index_document(self, chunk_id: str, text: str) -> None:
        """
        Index a document for BM25 search.
        
        Args:
            chunk_id: Unique chunk identifier
            text: Document text content to index
            
        Raises:
            BM25IndexError: If indexing fails
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Get BM25 tokens from text
            tokens = await self._get_tokens_from_text(text)
            
            if not tokens:
                logger.warning(f"No tokens extracted for document {chunk_id}")
                return
            
            # Add document to BM25 index
            await self.bm25_index.add_document(chunk_id, tokens)
            
            # Update stats
            self.stats["total_documents_indexed"] += 1
            indexing_time = asyncio.get_event_loop().time() - start_time
            self.stats["last_indexing_time"] = indexing_time
            self.stats["avg_indexing_time"] = (
                (self.stats["avg_indexing_time"] * (self.stats["total_documents_indexed"] - 1) + indexing_time) /
                self.stats["total_documents_indexed"]
            )
            
            logger.debug(f"Indexed document {chunk_id} with {len(tokens)} tokens")
            
        except Exception as e:
            self.stats["total_errors"] += 1
            logger.error(f"Failed to index document {chunk_id}: {e}")
            raise BM25IndexError(f"Failed to index document {chunk_id}: {e}") from e
    
    async def search(
        self, 
        query: str, 
        limit: Optional[int] = None,
        min_score: Optional[float] = None,
        k1: Optional[float] = None,
        b: Optional[float] = None
    ) -> List[BM25SearchResult]:
        """
        Search documents using BM25 algorithm.
        
        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_score: Minimum relevance score threshold
            
        Returns:
            List of BM25SearchResult objects ranked by relevance
            
        Raises:
            BM25SearchError: If search operation fails
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Get BM25 tokens from query
            query_tokens = await self._get_tokens_from_text(query)
            
            if not query_tokens:
                logger.warning("No tokens extracted for query")
                return []
            
            # Search in BM25 index with custom parameters
            search_results = await self.bm25_index.search(
                query_tokens, 
                limit,
                k1=k1,
                b=b
            )
            
            # Convert to BM25SearchResult objects
            results = []
            for rank, (doc_id, score) in enumerate(search_results, 1):
                if min_score is not None and score < min_score:
                    continue
                
                # Find matched terms
                matched_terms = [term for term in query_tokens 
                               if term in self.bm25_index.term_frequencies 
                               and doc_id in self.bm25_index.term_frequencies[term]]
                
                result = BM25SearchResult(
                    doc_id=doc_id,
                    score=score,
                    rank=rank,
                    matched_terms=matched_terms
                )
                results.append(result)
            
            # Update stats
            self.stats["total_searches"] += 1
            search_time = asyncio.get_event_loop().time() - start_time
            self.stats["last_search_time"] = search_time
            self.stats["avg_search_time"] = (
                (self.stats["avg_search_time"] * (self.stats["total_searches"] - 1) + search_time) /
                self.stats["total_searches"]
            )
            
            logger.debug(f"Search returned {len(results)} results")
            return results
            
        except Exception as e:
            self.stats["total_errors"] += 1
            logger.error(f"Search failed: {e}")
            raise BM25SearchError(f"Search failed: {e}") from e
    
    async def update_document(self, chunk_id: str, text: str) -> None:
        """
        Update indexed document.
        
        Args:
            chunk_id: Chunk identifier to update
            text: New document text content
            
        Raises:
            BM25IndexError: If update fails
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Get BM25 tokens from text
            tokens = await self._get_tokens_from_text(text)
            
            if not tokens:
                logger.warning(f"No tokens extracted for document {chunk_id}")
                return
            
            # Update document in BM25 index
            await self.bm25_index.update_document(chunk_id, tokens)
            
            logger.debug(f"Updated document {chunk_id}")
            
        except Exception as e:
            self.stats["total_errors"] += 1
            logger.error(f"Failed to update document {chunk_id}: {e}")
            raise BM25IndexError(f"Failed to update document {chunk_id}: {e}") from e
    
    async def delete_document(self, chunk_id: str) -> None:
        """
        Remove document from index.
        
        Args:
            chunk_id: Chunk identifier to remove
            
        Raises:
            BM25IndexError: If deletion fails
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            # Remove document from BM25 index
            await self.bm25_index.remove_document(chunk_id)
            
            logger.debug(f"Deleted document {chunk_id}")
            
        except Exception as e:
            self.stats["total_errors"] += 1
            logger.error(f"Failed to delete document {chunk_id}: {e}")
            raise BM25IndexError(f"Failed to delete document {chunk_id}: {e}") from e
    
    async def batch_index_documents(
        self, 
        documents: List[Tuple[str, str]]
    ) -> None:
        """
        Index multiple documents in batch.
        
        Args:
            documents: List of (chunk_id, text) tuples
            
        Raises:
            BM25IndexError: If batch indexing fails
        """
        try:
            if not self.is_initialized:
                await self.initialize()
            
            batch_size = self.config.get("batch_size", 100)
            
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                # Process batch
                tasks = []
                for chunk_id, text in batch:
                    task = self.index_document(chunk_id, text)
                    tasks.append(task)
                
                # Wait for all tasks to complete
                await asyncio.gather(*tasks, return_exceptions=True)
                
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(documents) + batch_size - 1)//batch_size}")
            
            logger.info(f"Batch indexed {len(documents)} documents")
            
        except Exception as e:
            self.stats["total_errors"] += 1
            logger.error(f"Batch indexing failed: {e}")
            raise BM25IndexError(f"Batch indexing failed: {e}") from e
    
    async def get_index_stats(self) -> BM25IndexStats:
        """
        Get BM25 index statistics.
        
        Returns:
            BM25IndexStats object with current index statistics
        """
        return self.bm25_index.get_stats()
    
    async def clear_index(self) -> None:
        """
        Clear all documents from BM25 index.
        
        Removes all indexed documents and resets index statistics.
        """
        try:
            self.bm25_index.clear_index()
            logger.info("BM25 index cleared")
        except Exception as e:
            logger.error(f"Failed to clear BM25 index: {e}")
            raise BM25IndexError(f"Failed to clear BM25 index: {e}") from e
    
    async def save_index(self, filepath: Optional[str] = None) -> None:
        """
        Save BM25 index to persistent storage.
        
        Args:
            filepath: Optional custom filepath for index storage
            
        Raises:
            BM25IndexError: If index save fails
        """
        try:
            if filepath:
                await self.bm25_index.save_index(filepath)
            elif self.redis_client:
                await self.bm25_index.save_to_redis()
            else:
                raise BM25IndexError("No storage method specified")
            
            logger.info("BM25 index saved")
            
        except Exception as e:
            logger.error(f"Failed to save BM25 index: {e}")
            raise BM25IndexError(f"Failed to save BM25 index: {e}") from e
    
    async def load_index(self, filepath: Optional[str] = None) -> None:
        """
        Load BM25 index from persistent storage.
        
        Args:
            filepath: Optional custom filepath for index loading
            
        Raises:
            BM25IndexError: If index load fails
        """
        try:
            if filepath:
                await self.bm25_index.load_index(filepath)
            elif self.redis_client:
                await self.bm25_index.load_from_redis()
            else:
                raise BM25IndexError("No storage method specified")
            
            logger.info("BM25 index loaded")
            
        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")
            raise BM25IndexError(f"Failed to load BM25 index: {e}") from e
    
    def get_service_stats(self) -> Dict[str, Any]:
        """
        Get service statistics and metrics.
        
        Returns:
            Dictionary with service performance metrics
        """
        stats = self.stats.copy()
        stats.update({
            "is_initialized": self.is_initialized,
            "index_stats": self.bm25_index.get_stats().__dict__,
            "timestamp": datetime.now().isoformat()
        })
        return stats
    
    async def close(self) -> None:
        """
        Close the service and cleanup resources.
        """
        try:
            if self.embedding_client:
                await self.embedding_client.__aexit__(None, None, None)
                self.embedding_client = None
            
            logger.info("BM25SearchService closed")
            
        except Exception as e:
            logger.error(f"Error closing BM25SearchService: {e}")


def create_bm25_service(
    config: Dict[str, Any]
) -> BM25SearchService:
    """
    Factory function to create BM25 search service.
    
    Args:
        config: Service configuration
        
    Returns:
        BM25SearchService instance
        
    Raises:
        ValueError: If configuration is invalid
    """
    if not config:
        raise ValueError("Configuration is required")
    
    return BM25SearchService(config)
