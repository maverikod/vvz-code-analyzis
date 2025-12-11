"""
BM25 Index declaration for working with pre-computed tokens.

This file contains the declarative interface for BM25 index functionality,
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

from typing import Dict, List, Any, Optional, Tuple, Set, Union
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
import time

# Constants
DEFAULT_BM25_K1: float = 1.2
"""Default BM25 parameter k1 for term frequency saturation."""

DEFAULT_BM25_B: float = 0.75
"""Default BM25 parameter b for length normalization."""

DEFAULT_MIN_SCORE: float = 0.0
"""Minimum relevance score for search results."""

DEFAULT_MAX_RESULTS: int = 1000
"""Maximum number of search results to return."""

DEFAULT_CACHE_SIZE: int = 10000
"""Default size of in-memory cache for BM25 index."""

DEFAULT_BATCH_SIZE: int = 1000
"""Default batch size for bulk operations."""

# Exceptions
class BM25IndexError(Exception):
    """Exception raised for BM25 index-related errors."""
    pass

class BM25SearchError(Exception):
    """Exception raised for BM25 search errors."""
    pass

# Data structures
@dataclass
class BM25Document:
    """
    Represents a document in the BM25 index.
    
    Attributes:
        doc_id: Unique document identifier
        tokens: List of pre-computed tokens from embed_client
        length: Document length in tokens
        metadata: Additional document metadata
    """
    doc_id: str
    tokens: List[str]
    length: int
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class BM25SearchResult:
    """
    Represents a single BM25 search result.
    
    Attributes:
        doc_id: Document identifier
        score: BM25 relevance score
        rank: Result rank position
        matched_terms: List of query terms found in document
    """
    doc_id: str
    score: float
    rank: int
    matched_terms: List[str]

@dataclass
class BM25IndexStats:
    """
    Statistics about the BM25 index.
    
    Attributes:
        total_documents: Total number of indexed documents
        total_terms: Total number of unique terms
        avg_document_length: Average document length
        index_size_bytes: Size of index in bytes
        last_updated: Timestamp of last index update
    """
    total_documents: int
    total_terms: int
    avg_document_length: float
    index_size_bytes: int
    last_updated: float

class BM25Index(ABC):
    """
    Abstract base class for BM25 index implementation.
    
    Provides interface for BM25 algorithm implementation,
    document indexing, and search functionality using pre-computed tokens.
    
    Features:
    - Term frequency storage and calculation
    - Document frequency tracking
    - BM25 score computation
    - Index serialization and persistence
    - Memory-efficient storage
    - Redis integration for persistence
    
    Architecture:
    - Abstract interface for different storage backends
    - Redis-based persistence
    - In-memory caching for performance
    - Batch processing support
    - Integration with embed_client tokens
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize BM25 index with configuration.
        
        Args:
            config: Index configuration including BM25 parameters,
                   storage settings, and performance options
        """
        self.k1: float = config.get("k1", DEFAULT_BM25_K1)
        """BM25 parameter k1 for term frequency saturation."""
        
        self.b: float = config.get("b", DEFAULT_BM25_B)
        """BM25 parameter b for length normalization."""
        
        self.min_score: float = config.get("min_score", DEFAULT_MIN_SCORE)
        """Minimum relevance score for search results."""
        
        self.max_results: int = config.get("max_results", DEFAULT_MAX_RESULTS)
        """Maximum number of search results to return."""
        
        self.cache_size: int = config.get("cache_size", DEFAULT_CACHE_SIZE)
        """Size of in-memory cache."""
        
        self.batch_size: int = config.get("batch_size", DEFAULT_BATCH_SIZE)
        """Batch size for bulk operations."""
        
        # Index data structures
        self.term_frequencies: Dict[str, Dict[str, int]] = {}
        """Term frequencies per document: {term: {doc_id: frequency}}."""
        
        self.document_frequencies: Dict[str, int] = {}
        """Document frequencies per term: {term: doc_count}."""
        
        self.document_lengths: Dict[str, int] = {}
        """Document lengths: {doc_id: length}."""
        
        self.avg_document_length: float = 0.0
        """Average document length in the collection."""
        
        self.total_documents: int = 0
        """Total number of documents in the index."""
        
        self.redis_client: Any = None
        """Redis client for index persistence."""
        
        self.redis_key_prefix: str = config.get("redis_key_prefix", "bm25:")
        """Prefix for Redis keys."""
    
    @abstractmethod
    async def add_document(self, doc_id: str, tokens: List[str]) -> None:
        """
        Add document to BM25 index using pre-computed tokens.
        
        Args:
            doc_id: Unique document identifier
            tokens: List of pre-computed tokens from embed_client
            
        Raises:
            BM25IndexError: If document addition fails
        """
        pass
    
    @abstractmethod
    async def remove_document(self, doc_id: str) -> None:
        """
        Remove document from BM25 index.
        
        Args:
            doc_id: Document identifier to remove
            
        Raises:
            BM25IndexError: If document removal fails
        """
        pass
    
    @abstractmethod
    async def update_document(self, doc_id: str, tokens: List[str]) -> None:
        """
        Update existing document in BM25 index.
        
        Args:
            doc_id: Document identifier to update
            tokens: New list of pre-computed tokens
            
        Raises:
            BM25IndexError: If document update fails
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def search(
        self, 
        query_tokens: List[str], 
        limit: Optional[int] = None
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
        pass
    
    @abstractmethod
    async def save_index(self, filepath: str) -> None:
        """
        Save BM25 index to file.
        
        Args:
            filepath: Path to save index file
            
        Raises:
            BM25IndexError: If index save fails
        """
        pass
    
    @abstractmethod
    async def load_index(self, filepath: str) -> None:
        """
        Load BM25 index from file.
        
        Args:
            filepath: Path to load index file from
            
        Raises:
            BM25IndexError: If index load fails
        """
        pass
    
    @abstractmethod
    async def save_to_redis(self) -> None:
        """
        Save BM25 index to Redis.
        
        Raises:
            BM25IndexError: If Redis save fails
        """
        pass
    
    @abstractmethod
    async def load_from_redis(self) -> None:
        """
        Load BM25 index from Redis.
        
        Raises:
            BM25IndexError: If Redis load fails
        """
        pass
    
    def get_stats(self) -> BM25IndexStats:
        """
        Get statistics about the BM25 index.
        
        Returns:
            BM25IndexStats object with index statistics
        """
        return BM25IndexStats(
            total_documents=self.total_documents,
            total_terms=len(self.document_frequencies),
            avg_document_length=self.avg_document_length,
            index_size_bytes=0,  # To be implemented
            last_updated=time.time()
        )
    
    def clear_index(self) -> None:
        """Clear all data from the BM25 index."""
        self.term_frequencies.clear()
        self.document_frequencies.clear()
        self.document_lengths.clear()
        self.avg_document_length = 0.0
        self.total_documents = 0

# Utility functions
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
    pass
