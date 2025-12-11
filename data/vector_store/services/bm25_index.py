"""
BM25 Index implementation for working with pre-computed tokens.

This module provides the implementation of BM25 index functionality,
designed to work with tokens provided by embed_client service.

Features:
- BM25 algorithm implementation for pre-computed tokens
- Document indexing with term frequency calculation
- BM25 score computation and ranking
- Redis-based index storage and persistence
- Integration with chunk_metadata_adapter SearchResult

Architecture:
- BM25Index: Core BM25 algorithm implementation
- Redis integration for index persistence
- In-memory caching for performance optimization
- Support for pre-computed tokens from embed_client

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import json
import pickle
import time
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from collections import defaultdict, Counter
import math
import asyncio

from .bm25_index_decl import (
    BM25Index as BM25IndexBase,
    BM25IndexError,
    BM25SearchError,
    BM25Document,
    BM25SearchResult,
    BM25IndexStats,
    DEFAULT_BM25_K1,
    DEFAULT_BM25_B,
    DEFAULT_MIN_SCORE,
    DEFAULT_MAX_RESULTS,
    DEFAULT_CACHE_SIZE,
    DEFAULT_BATCH_SIZE
)

logger = logging.getLogger(__name__)


class BM25Index(BM25IndexBase):
    """
    BM25 index implementation for pre-computed tokens.
    
    This class implements the BM25 algorithm for document ranking
    using pre-computed tokens from the embed_client service.
    
    Features:
    - Term frequency storage and calculation
    - Document frequency tracking
    - BM25 score computation
    - Redis integration for persistence
    - Memory-efficient storage
    - Batch processing support
    
    Architecture:
    - In-memory data structures for fast access
    - Redis persistence for durability
    - BM25 algorithm implementation
    - Integration with embed_client tokens
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize BM25 index with configuration.
        
        Args:
            config: Index configuration including BM25 parameters,
                   storage settings, and performance options
        """
        super().__init__(config)
        
        # Initialize Redis client if provided
        self.redis_client = config.get("redis_client")
        if self.redis_client:
            logger.info("BM25Index initialized with Redis client")
        else:
            logger.warning("BM25Index initialized without Redis client - persistence disabled")
        
        # Performance tracking
        self.stats: Dict[str, Any] = {
            "indexing_time": 0.0,
            "search_time": 0.0,
            "total_searches": 0,
            "total_documents_indexed": 0
        }
        
        logger.info(f"BM25Index initialized with k1={self.k1}, b={self.b}")
    
    async def add_document(self, doc_id: str, tokens: List[str]) -> None:
        """
        Add document to BM25 index using pre-computed tokens.
        
        Args:
            doc_id: Unique document identifier
            tokens: List of pre-computed tokens from embed_client
            
        Raises:
            BM25IndexError: If document addition fails
        """
        start_time = time.time()
        
        try:
            if not doc_id or not tokens:
                raise BM25IndexError("Document ID and tokens are required")
            
            # Remove existing document if it exists
            if doc_id in self.document_lengths:
                await self.remove_document(doc_id)
            
            # Calculate term frequencies
            term_freq = Counter(tokens)
            doc_length = len(tokens)
            
            # Update index data structures
            self.document_lengths[doc_id] = doc_length
            
            # Update term frequencies
            for term, freq in term_freq.items():
                if term not in self.term_frequencies:
                    self.term_frequencies[term] = {}
                self.term_frequencies[term][doc_id] = freq
            
            # Update document frequencies
            for term in term_freq.keys():
                self.document_frequencies[term] = self.document_frequencies.get(term, 0) + 1
            
            # Update collection statistics
            self.total_documents += 1
            total_length = sum(self.document_lengths.values())
            self.avg_document_length = total_length / self.total_documents
            
            # Update stats
            self.stats["total_documents_indexed"] += 1
            self.stats["indexing_time"] += time.time() - start_time
            
            logger.debug(f"Added document {doc_id} with {len(tokens)} tokens")
            
        except Exception as e:
            logger.error(f"Failed to add document {doc_id}: {e}")
            raise BM25IndexError(f"Failed to add document {doc_id}: {e}") from e
    
    async def remove_document(self, doc_id: str) -> None:
        """
        Remove document from BM25 index.
        
        Args:
            doc_id: Document identifier to remove
            
        Raises:
            BM25IndexError: If document removal fails
        """
        try:
            if doc_id not in self.document_lengths:
                logger.warning(f"Document {doc_id} not found in index")
                return
            
            # Get document length
            doc_length = self.document_lengths[doc_id]
            
            # Remove from term frequencies
            for term in list(self.term_frequencies.keys()):
                if doc_id in self.term_frequencies[term]:
                    del self.term_frequencies[term][doc_id]
                    # Remove term if no documents contain it
                    if not self.term_frequencies[term]:
                        del self.term_frequencies[term]
                        if term in self.document_frequencies:
                            del self.document_frequencies[term]
                    else:
                        # Update document frequency
                        self.document_frequencies[term] -= 1
                        if self.document_frequencies[term] <= 0:
                            del self.document_frequencies[term]
            
            # Remove document length
            del self.document_lengths[doc_id]
            
            # Update collection statistics
            self.total_documents -= 1
            if self.total_documents > 0:
                total_length = sum(self.document_lengths.values())
                self.avg_document_length = total_length / self.total_documents
            else:
                self.avg_document_length = 0.0
            
            logger.debug(f"Removed document {doc_id}")
            
        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {e}")
            raise BM25IndexError(f"Failed to remove document {doc_id}: {e}") from e
    
    async def update_document(self, doc_id: str, tokens: List[str]) -> None:
        """
        Update existing document in BM25 index.
        
        Args:
            doc_id: Document identifier to update
            tokens: New list of pre-computed tokens
            
        Raises:
            BM25IndexError: If document update fails
        """
        try:
            # Remove existing document and add new one
            await self.remove_document(doc_id)
            await self.add_document(doc_id, tokens)
            
            logger.debug(f"Updated document {doc_id}")
            
        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            raise BM25IndexError(f"Failed to update document {doc_id}: {e}") from e
    
    def calculate_bm25_score(
        self, 
        query_tokens: List[str], 
        doc_id: str
    ) -> float:
        """
        Calculate BM25 score for document given query tokens.
        
        Args:
            query_tokens: List of pre-computed query tokens
            doc_id: Document identifier
            
        Returns:
            BM25 relevance score
            
        Raises:
            BM25IndexError: If score calculation fails
        """
        try:
            if doc_id not in self.document_lengths:
                return 0.0
            
            doc_length = self.document_lengths[doc_id]
            score = 0.0
            
            for term in query_tokens:
                if term not in self.term_frequencies or doc_id not in self.term_frequencies[term]:
                    continue
                
                # Term frequency in document
                tf = self.term_frequencies[term][doc_id]
                
                # Document frequency
                df = self.document_frequencies.get(term, 0)
                if df == 0:
                    continue
                
                # Inverse document frequency (using BM25 formula)
                idf = math.log((self.total_documents + 1) / (df + 0.5))
                
                # BM25 score component
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_document_length))
                
                score += idf * (numerator / denominator)
            
            return score
            
        except Exception as e:
            logger.error(f"Failed to calculate BM25 score for document {doc_id}: {e}")
            raise BM25IndexError(f"Failed to calculate BM25 score for document {doc_id}: {e}") from e

    def calculate_bm25_score_with_params(
        self, 
        query_tokens: List[str], 
        doc_id: str,
        k1: float,
        b: float
    ) -> float:
        """
        Calculate BM25 score for document given query tokens with custom parameters.
        
        Args:
            query_tokens: List of pre-computed query tokens
            doc_id: Document identifier
            k1: BM25 k1 parameter
            b: BM25 b parameter
            
        Returns:
            BM25 relevance score
            
        Raises:
            BM25IndexError: If score calculation fails
        """
        try:
            if doc_id not in self.document_lengths:
                return 0.0
            
            doc_length = self.document_lengths[doc_id]
            score = 0.0
            
            for term in query_tokens:
                if term not in self.term_frequencies or doc_id not in self.term_frequencies[term]:
                    continue
                
                # Term frequency in document
                tf = self.term_frequencies[term][doc_id]
                
                # Document frequency
                df = self.document_frequencies.get(term, 0)
                if df == 0:
                    continue
                
                # Inverse document frequency (using BM25 formula)
                idf = math.log((self.total_documents + 1) / (df + 0.5))
                
                # BM25 score component with custom parameters
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_length / self.avg_document_length))
                
                score += idf * (numerator / denominator)
            
            return score
            
        except Exception as e:
            logger.error(f"Failed to calculate BM25 score for document {doc_id}: {e}")
            raise BM25IndexError(f"Failed to calculate BM25 score for document {doc_id}: {e}") from e
    
    async def search(
        self, 
        query_tokens: List[str], 
        limit: Optional[int] = None,
        k1: Optional[float] = None,
        b: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        """
        Search documents and return ranked results.
        
        Args:
            query_tokens: List of pre-computed query tokens
            limit: Maximum number of results to return
            
        Returns:
            List of (doc_id, score) tuples ranked by relevance
            
        Raises:
            BM25SearchError: If search operation fails
        """
        start_time = time.time()
        
        try:
            if not query_tokens:
                return []
            
            limit = limit or self.max_results
            
            # Use custom k1 and b parameters if provided
            search_k1 = k1 if k1 is not None else self.k1
            search_b = b if b is not None else self.b
            
            # Calculate scores for all documents
            scores = []
            for doc_id in self.document_lengths.keys():
                score = self.calculate_bm25_score_with_params(query_tokens, doc_id, search_k1, search_b)
                if score > 0.0:  # Only include documents with positive scores
                    scores.append((doc_id, score))
            
            # Sort by score (descending) and limit results
            scores.sort(key=lambda x: x[1], reverse=True)
            results = scores[:limit]
            
            # Update stats
            self.stats["search_time"] += time.time() - start_time
            self.stats["total_searches"] += 1
            
            logger.debug(f"Search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise BM25SearchError(f"Search failed: {e}") from e
    
    async def save_index(self, filepath: str) -> None:
        """
        Save BM25 index to file.
        
        Args:
            filepath: Path to save index file
            
        Raises:
            BM25IndexError: If index save fails
        """
        try:
            index_data = {
                "term_frequencies": self.term_frequencies,
                "document_frequencies": self.document_frequencies,
                "document_lengths": self.document_lengths,
                "avg_document_length": self.avg_document_length,
                "total_documents": self.total_documents,
                "stats": self.stats
            }
            
            with open(filepath, 'wb') as f:
                pickle.dump(index_data, f)
            
            logger.info(f"BM25 index saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save BM25 index to {filepath}: {e}")
            raise BM25IndexError(f"Failed to save BM25 index to {filepath}: {e}") from e
    
    async def load_index(self, filepath: str) -> None:
        """
        Load BM25 index from file.
        
        Args:
            filepath: Path to load index file from
            
        Raises:
            BM25IndexError: If index load fails
        """
        try:
            with open(filepath, 'rb') as f:
                index_data = pickle.load(f)
            
            self.term_frequencies = index_data["term_frequencies"]
            self.document_frequencies = index_data["document_frequencies"]
            self.document_lengths = index_data["document_lengths"]
            self.avg_document_length = index_data["avg_document_length"]
            self.total_documents = index_data["total_documents"]
            self.stats = index_data.get("stats", self.stats)
            
            logger.info(f"BM25 index loaded from {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to load BM25 index from {filepath}: {e}")
            raise BM25IndexError(f"Failed to load BM25 index from {filepath}: {e}") from e
    
    async def save_to_redis(self) -> None:
        """
        Save BM25 index to Redis.
        
        Raises:
            BM25IndexError: If Redis save fails
        """
        if not self.redis_client:
            raise BM25IndexError("Redis client not available")
        
        try:
            # Save index data to Redis
            index_data = {
                "term_frequencies": self.term_frequencies,
                "document_frequencies": self.document_frequencies,
                "document_lengths": self.document_lengths,
                "avg_document_length": self.avg_document_length,
                "total_documents": self.total_documents,
                "stats": self.stats
            }
            
            # Serialize to JSON for Redis storage
            serialized_data = json.dumps(index_data, default=str)
            
            # Save to Redis with key prefix
            key = f"{self.redis_key_prefix}index"
            await self.redis_client.set(key, serialized_data)
            
            logger.info("BM25 index saved to Redis")
            
        except Exception as e:
            logger.error(f"Failed to save BM25 index to Redis: {e}")
            raise BM25IndexError(f"Failed to save BM25 index to Redis: {e}") from e
    
    async def load_from_redis(self) -> None:
        """
        Load BM25 index from Redis.
        
        Raises:
            BM25IndexError: If Redis load fails
        """
        if not self.redis_client:
            raise BM25IndexError("Redis client not available")
        
        try:
            # Load from Redis with key prefix
            key = f"{self.redis_key_prefix}index"
            serialized_data = await self.redis_client.get(key)
            
            if not serialized_data:
                logger.warning("No BM25 index found in Redis")
                return
            
            # Deserialize from JSON
            index_data = json.loads(serialized_data)
            
            self.term_frequencies = index_data["term_frequencies"]
            self.document_frequencies = index_data["document_frequencies"]
            self.document_lengths = index_data["document_lengths"]
            self.avg_document_length = index_data["avg_document_length"]
            self.total_documents = index_data["total_documents"]
            self.stats = index_data.get("stats", self.stats)
            
            logger.info("BM25 index loaded from Redis")
            
        except Exception as e:
            logger.error(f"Failed to load BM25 index from Redis: {e}")
            raise BM25IndexError(f"Failed to load BM25 index from Redis: {e}") from e
    
    def get_stats(self) -> BM25IndexStats:
        """
        Get statistics about the BM25 index.
        
        Returns:
            BM25IndexStats object with index statistics
        """
        # Calculate index size in bytes (approximate)
        index_size = 0
        for term, docs in self.term_frequencies.items():
            index_size += len(term) + sum(len(doc_id) + 8 for doc_id in docs)  # 8 bytes for frequency
        
        return BM25IndexStats(
            total_documents=self.total_documents,
            total_terms=len(self.document_frequencies),
            avg_document_length=self.avg_document_length,
            index_size_bytes=index_size,
            last_updated=time.time()
        )


def create_bm25_index(
    config: Optional[Dict[str, Any]] = None
) -> BM25Index:
    """
    Factory function to create BM25 index.
    
    Args:
        config: Optional index configuration
        
    Returns:
        BM25Index instance with specified configuration
    """
    if config is None:
        config = {}
    
    return BM25Index(config)
