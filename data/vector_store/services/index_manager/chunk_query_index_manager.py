"""
ChunkQuery integration with AtomicIndexManager.

This module provides integration between chunk_metadata_adapter.ChunkQuery
and AtomicIndexManager for efficient search and filtering operations.

Features:
- Integration with chunk_metadata_adapter.ChunkQuery
- Support for all ChunkQuery parameters and capabilities
- LUA script generation for different search types
- Hybrid search (BM25 + semantic)
- Metadata filtering with complex expressions
- Performance optimization and caching
- Comprehensive error handling

Architecture:
- Extends AtomicIndexManager with ChunkQuery support
- Uses LUA scripts for efficient Redis operations
- Supports multiple search strategies
- Implements caching for performance
- Provides unified search interface

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

import redis.asyncio as redis
from chunk_metadata_adapter import ChunkQuery

# Logger
logger = logging.getLogger(__name__)

# Constants
DEFAULT_SEARCH_LIMIT: int = 100
"""Default limit for search results."""

DEFAULT_SEARCH_OFFSET: int = 0
"""Default offset for search results."""

DEFAULT_SEMANTIC_WEIGHT: float = 0.5
"""Default weight for semantic search in hybrid mode."""

DEFAULT_BM25_WEIGHT: float = 0.5
"""Default weight for BM25 search in hybrid mode."""

# Search result dataclass
@dataclass
class SearchResult:
    """Result of a search operation."""
    uuid: str
    """Unique identifier of the chunk."""
    score: float
    """Relevance score of the result."""
    metadata: Dict[str, Any]
    """Metadata of the chunk."""
    search_type: str
    """Type of search that produced this result."""
    execution_time: float
    """Time taken to execute the search."""

# Search type enumeration
class SearchType:
    """Types of search operations."""
    TEXT = "text"
    """Text-based search using BM25."""
    VECTOR = "vector"
    """Vector-based semantic search."""
    METADATA = "metadata"
    """Metadata filtering search."""
    HYBRID = "hybrid"
    """Hybrid search combining text and vector."""
    COMBINED = "combined"
    """Combined search using multiple strategies."""

# Base search strategy
class BaseSearchStrategy(ABC):
    """
    Base class for search strategies.
    
    Defines the interface for different search implementations
    with support for LUA script generation and execution.
    """
    
    def __init__(self, redis_client: redis.Redis) -> None:
        """
        Initialize search strategy.
        
        Args:
            redis_client: Redis client for operations
        """
        self.redis_client = redis_client
        """Redis client for operations."""
        
        self._script_cache: Dict[str, str] = {}
        """Cache for generated LUA scripts."""
    
    @abstractmethod
    def generate_script(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate LUA script for search operation.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            LUA script string for execution
        """
        raise NotImplementedError
    
    @abstractmethod
    async def execute_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute search operation.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of search results
        """
        raise NotImplementedError
    
    def _parse_search_results(
        self,
        redis_result: Any,
        search_type: str
    ) -> List[SearchResult]:
        """
        Parse search results from Redis.
        
        Args:
            redis_result: Raw result from Redis
            search_type: Type of search that produced results
            
        Returns:
            List of parsed search results
        """
        if not redis_result:
            return []
        
        try:
            results_data = json.loads(redis_result)
            search_results = []
            
            for item in results_data:
                # Get chunk metadata
                chunk_key = f"chunk:{item['uuid']}"
                metadata = self.redis_client.hgetall(chunk_key)
                
                search_result = SearchResult(
                    uuid=item['uuid'],
                    score=item['score'],
                    metadata=metadata,
                    search_type=search_type,
                    execution_time=0.0
                )
                search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Failed to parse search results: {e}")
            return []
    
    def _get_cached_script(self, cache_key: str) -> Optional[str]:
        """
        Get cached LUA script.
        
        Args:
            cache_key: Cache key for the script
            
        Returns:
            Cached script or None if not found
        """
        return self._script_cache.get(cache_key)
    
    def _cache_script(self, cache_key: str, script: str) -> None:
        """
        Cache LUA script.
        
        Args:
            cache_key: Cache key for the script
            script: LUA script to cache
        """
        self._script_cache[cache_key] = script

# Text search strategy
class TextSearchStrategy(BaseSearchStrategy):
    """
    Text-based search strategy using BM25.
    
    Implements BM25 algorithm for text search with tokenization
    and relevance scoring.
    """
    
    def generate_script(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate LUA script for BM25 text search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            LUA script for BM25 search
        """
        search_text = chunk_query.search_query or chunk_query.text or ""
        if not search_text:
            return ""
        
        limit = limit or chunk_query.max_results or DEFAULT_SEARCH_LIMIT
        offset = offset or 0
        
        return f"""
-- BM25 Text Search Script
local search_text = "{search_text}"
local limit = {limit}
local offset = {offset}
local k1 = {chunk_query.bm25_k1 or 1.2}
local b = {chunk_query.bm25_b or 0.75}

-- Tokenize search text
local tokens = {{}}
for token in string.gmatch(search_text:lower(), "%w+") do
    if #token > 2 then  -- Skip very short tokens
        table.insert(tokens, token)
    end
end

-- Get total document count
local total_docs = redis.call('GET', 'total_documents') or 0
if total_docs == 0 then
    total_docs = 1  -- Avoid division by zero
end

-- Search for each token
local results = {{}}
local doc_scores = {{}}

for _, token in ipairs(tokens) do
    local token_key = "bm25_token_index:" .. token
    local docs = redis.call('SMEMBERS', token_key)
    
    for _, doc_uuid in ipairs(docs) do
        if not doc_scores[doc_uuid] then
            doc_scores[doc_uuid] = 0
        end
        
        -- Calculate BM25 score for this token
        local doc_freq = redis.call('HGET', 'bm25_doc_freq:' .. doc_uuid, token) or 0
        local avg_doc_length = redis.call('GET', 'avg_doc_length') or 100
        local doc_length = redis.call('HGET', 'doc_lengths', doc_uuid) or avg_doc_length
        
        local idf = math.log((total_docs - #docs + 0.5) / (#docs + 0.5))
        local tf = doc_freq / (doc_freq + k1 * (1 - b + b * doc_length / avg_doc_length))
        
        doc_scores[doc_uuid] = doc_scores[doc_uuid] + idf * tf
    end
end

-- Convert to results array
for doc_uuid, score in pairs(doc_scores) do
    table.insert(results, {{uuid = doc_uuid, score = score}})
end

-- Sort by score (descending)
table.sort(results, function(a, b) return a.score > b.score end)

-- Apply pagination
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)
"""
    
    async def execute_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute BM25 text search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of search results
        """
        script = self.generate_script(chunk_query, limit, offset)
        if not script:
            return []
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, SearchType.TEXT)
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

# Vector search strategy
class VectorSearchStrategy(BaseSearchStrategy):
    """
    Vector-based semantic search strategy.
    
    Implements cosine similarity search for semantic matching
    using embedding vectors.
    """
    
    def generate_script(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate LUA script for vector search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            LUA script for vector search
        """
        embedding = chunk_query.embedding
        if not embedding:
            return ""
        
        # Handle both single vector and list of vectors
        if isinstance(embedding[0], list):
            embedding = embedding[0]  # Take first vector if list
        
        embedding_json = json.dumps(embedding)
        limit = limit or chunk_query.max_results or DEFAULT_SEARCH_LIMIT
        offset = offset or 0
        
        return f"""
-- Vector Search Script
local search_embedding = cjson.decode('{embedding_json}')
local limit = {limit}
local offset = {offset}
local min_score = {chunk_query.min_score or 0.0}

-- Get all vector keys
local vector_keys = redis.call('KEYS', 'vector_data:*')
local results = {{}}

for _, key in ipairs(vector_keys) do
    local uuid = string.sub(key, 13)  -- Remove 'vector_data:' prefix
    local vector_data = redis.call('GET', key)
    
    if vector_data then
        local vector = cjson.decode(vector_data)
        local similarity = calculate_cosine_similarity(search_embedding, vector)
        
        if similarity >= min_score then
            table.insert(results, {{uuid = uuid, score = similarity}})
        end
    end
end

-- Sort by similarity (descending)
table.sort(results, function(a, b) return a.score > b.score end)

-- Apply pagination
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)

function calculate_cosine_similarity(vec1, vec2)
    local dot_product = 0
    local norm1 = 0
    local norm2 = 0
    
    for i = 1, #vec1 do
        dot_product = dot_product + vec1[i] * vec2[i]
        norm1 = norm1 + vec1[i] * vec1[i]
        norm2 = norm2 + vec2[i] * vec2[i]
    end
    
    if norm1 == 0 or norm2 == 0 then
        return 0
    end
    
    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
end
"""
    
    async def execute_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute vector search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of search results
        """
        script = self.generate_script(chunk_query, limit, offset)
        if not script:
            return []
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, SearchType.VECTOR)
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

# Metadata search strategy
class MetadataSearchStrategy(BaseSearchStrategy):
    """
    Metadata filtering search strategy.
    
    Implements filtering based on chunk metadata fields
    with support for complex expressions.
    """
    
    def generate_script(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate LUA script for metadata filtering.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            LUA script for metadata filtering
        """
        # Convert ChunkQuery to flat dict for filtering
        flat_query = chunk_query.to_flat_dict(for_redis=True)
        
        # Remove search-specific fields
        search_fields = ['search_query', 'embedding', 'bm25_k1', 'bm25_b', 
                        'hybrid_search', 'bm25_weight', 'semantic_weight', 
                        'min_score', 'max_results']
        for field in search_fields:
            flat_query.pop(field, None)
        
        if not flat_query:
            return ""
        
        filters_json = json.dumps(flat_query)
        limit = limit or chunk_query.max_results or DEFAULT_SEARCH_LIMIT
        offset = offset or 0
        
        return f"""
-- Metadata Filter Script
local metadata_filters = cjson.decode('{filters_json}')
local limit = {limit}
local offset = {offset}

local results = {{}}
local candidate_uuids = {{}}

-- Collect candidates for each filter
for field, value in pairs(metadata_filters) do
    if type(value) == "table" then
        -- Array values
        for _, item in ipairs(value) do
            local index_key = "array_element_index:" .. field .. ":" .. tostring(item)
            local uuids = redis.call('SMEMBERS', index_key)
            for _, uuid in ipairs(uuids) do
                candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
            end
        end
    else
        -- Scalar values
        local index_key = "field_index:" .. field .. ":" .. tostring(value)
        local uuids = redis.call('SMEMBERS', index_key)
        for _, uuid in ipairs(uuids) do
            candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
        end
    end
end

-- Filter by number of matches
local required_filters = 0
for _ in pairs(metadata_filters) do
    required_filters = required_filters + 1
end

for uuid, match_count in pairs(candidate_uuids) do
    if match_count >= required_filters then
        table.insert(results, {{uuid = uuid, score = match_count / required_filters}})
    end
end

-- Sort by relevance
table.sort(results, function(a, b) return a.score > b.score end)

-- Apply pagination
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)
"""
    
    async def execute_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute metadata filtering search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of search results
        """
        script = self.generate_script(chunk_query, limit, offset)
        if not script:
            return []
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, SearchType.METADATA)
        except Exception as e:
            logger.error(f"Metadata search failed: {e}")
            return []

# Hybrid search strategy
class HybridSearchStrategy(BaseSearchStrategy):
    """
    Hybrid search strategy combining text and vector search.
    
    Implements weighted combination of BM25 and semantic search
    for improved relevance.
    """
    
    def __init__(self, redis_client: redis.Redis, embedding_service=None):
        """
        Initialize hybrid search strategy.
        
        Args:
            redis_client: Redis client for operations
            embedding_service: Service for generating embeddings
        """
        super().__init__(redis_client)
        self.embedding_service = embedding_service
        """Service for generating embeddings."""
    
    def generate_script(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate LUA script for hybrid search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            LUA script for hybrid search
        """
        search_text = chunk_query.search_query or chunk_query.text or ""
        if not search_text:
            return ""
        
        # Get embedding for search text
        embedding = chunk_query.embedding
        if not embedding and self.embedding_service:
            # This would need to be handled in execute_search
            embedding = None
        
        embedding_json = json.dumps(embedding) if embedding else "null"
        bm25_weight = chunk_query.bm25_weight or DEFAULT_BM25_WEIGHT
        semantic_weight = chunk_query.semantic_weight or DEFAULT_SEMANTIC_WEIGHT
        limit = limit or chunk_query.max_results or DEFAULT_SEARCH_LIMIT
        offset = offset or 0
        
        return f"""
-- Hybrid Search Script
local search_text = "{search_text}"
local search_embedding = {embedding_json}
local bm25_weight = {bm25_weight}
local semantic_weight = {semantic_weight}
local limit = {limit}
local offset = {offset}

local results = {{}}

-- BM25 search
local bm25_results = {{}}
local tokens = {{}}
for token in string.gmatch(search_text:lower(), "%w+") do
    if #token > 2 then
        table.insert(tokens, token)
    end
end

for _, token in ipairs(tokens) do
    local token_key = "bm25_token_index:" .. token
    local uuids = redis.call('SMEMBERS', token_key)
    
    for _, uuid in ipairs(uuids) do
        if not bm25_results[uuid] then
            bm25_results[uuid] = 0
        end
        bm25_results[uuid] = bm25_results[uuid] + 1
    end
end

-- Normalize BM25 scores
local max_bm25_score = 0
for uuid, score in pairs(bm25_results) do
    if score > max_bm25_score then
        max_bm25_score = score
    end
end

if max_bm25_score > 0 then
    for uuid, score in pairs(bm25_results) do
        bm25_results[uuid] = score / max_bm25_score
    end
end

-- Semantic search
local semantic_results = {{}}
if search_embedding then
    local vector_keys = redis.call('KEYS', 'vector_data:*')
    
    for _, key in ipairs(vector_keys) do
        local uuid = string.sub(key, 13)
        local vector_data = redis.call('GET', key)
        
        if vector_data then
            local vector = cjson.decode(vector_data)
            local similarity = calculate_cosine_similarity(search_embedding, vector)
            semantic_results[uuid] = similarity
        end
    end
end

-- Combine results
local all_uuids = {{}}
for uuid in pairs(bm25_results) do
    all_uuids[uuid] = true
end
for uuid in pairs(semantic_results) do
    all_uuids[uuid] = true
end

for uuid in pairs(all_uuids) do
    local bm25_score = bm25_results[uuid] or 0
    local semantic_score = semantic_results[uuid] or 0
    
    local combined_score = bm25_weight * bm25_score + semantic_weight * semantic_score
    
    table.insert(results, {{uuid = uuid, score = combined_score}})
end

-- Sort by combined score
table.sort(results, function(a, b) return a.score > b.score end)

-- Apply pagination
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)

function calculate_cosine_similarity(vec1, vec2)
    local dot_product = 0
    local norm1 = 0
    local norm2 = 0
    
    for i = 1, #vec1 do
        dot_product = dot_product + vec1[i] * vec2[i]
        norm1 = norm1 + vec1[i] * vec1[i]
        norm2 = norm2 + vec2[i] * vec2[i]
    end
    
    if norm1 == 0 or norm2 == 0 then
        return 0
    end
    
    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
end
"""
    
    async def execute_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute hybrid search.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of search results
        """
        # Handle embedding generation if needed
        if not chunk_query.embedding and self.embedding_service:
            search_text = chunk_query.search_query or chunk_query.text
            if search_text:
                try:
                    embedding = await self.embedding_service.get_embedding(search_text)
                    chunk_query.embedding = embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {e}")
        
        script = self.generate_script(chunk_query, limit, offset)
        if not script:
            return []
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, SearchType.HYBRID)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

# Main ChunkQuery index manager
class ChunkQueryIndexManager:
    """
    Index manager with ChunkQuery integration.
    
    Provides unified interface for searching and filtering chunks
    using chunk_metadata_adapter.ChunkQuery with multiple strategies.
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        embedding_service=None,
        config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize ChunkQuery index manager.
        
        Args:
            redis_client: Redis client for operations
            embedding_service: Service for generating embeddings
            config: Optional configuration
        """
        self.redis_client = redis_client
        """Redis client for operations."""
        
        self.embedding_service = embedding_service
        """Service for generating embeddings."""
        
        self.config = config or {}
        """Configuration for the manager."""
        
        # Initialize search strategies
        self.text_strategy = TextSearchStrategy(redis_client)
        """Text search strategy."""
        
        self.vector_strategy = VectorSearchStrategy(redis_client)
        """Vector search strategy."""
        
        self.metadata_strategy = MetadataSearchStrategy(redis_client)
        """Metadata search strategy."""
        
        self.hybrid_strategy = HybridSearchStrategy(redis_client, embedding_service)
        """Hybrid search strategy."""
        
        # Cache for search results
        self._search_cache: Dict[str, List[SearchResult]] = {}
        """Cache for search results."""
        
        # Performance metrics
        self._performance_metrics: List[Dict[str, Any]] = []
        """Performance metrics for search operations."""
    
    def _determine_search_type(self, chunk_query: ChunkQuery) -> str:
        """
        Determine the appropriate search type for ChunkQuery.
        
        Args:
            chunk_query: ChunkQuery object to analyze
            
        Returns:
            Search type string
        """
        has_text = bool(chunk_query.search_query or chunk_query.text)
        has_embedding = bool(chunk_query.embedding)
        
        # Get metadata filters (excluding search-specific fields)
        flat_query = chunk_query.to_flat_dict(for_redis=True)
        search_fields = ['search_query', 'embedding', 'bm25_k1', 'bm25_b', 
                        'hybrid_search', 'bm25_weight', 'semantic_weight', 
                        'min_score', 'max_results', 'search_fields', 'created_at']
        for field in search_fields:
            flat_query.pop(field, None)
        has_metadata = bool(flat_query)
        
        is_hybrid = getattr(chunk_query, 'hybrid_search', False)
        
        if is_hybrid and has_text:
            return SearchType.HYBRID
        elif has_text and not has_metadata and not has_embedding:
            return SearchType.TEXT
        elif has_embedding and not has_text and not has_metadata:
            return SearchType.VECTOR
        elif has_metadata and not has_text and not has_embedding:
            return SearchType.METADATA
        else:
            return SearchType.COMBINED
    
    async def search_by_chunk_query(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        use_cache: bool = True
    ) -> List[SearchResult]:
        """
        Search using ChunkQuery object.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            use_cache: Whether to use result caching
            
        Returns:
            List of search results
        """
        import time
        start_time = time.time()
        
        try:
            # Check cache first
            if use_cache:
                cache_key = self._generate_cache_key(chunk_query, limit, offset)
                cached_results = self._get_cached_results(cache_key)
                if cached_results:
                    logger.debug(f"Cache hit for search: {cache_key}")
                    return cached_results
            
            # Determine search type
            search_type = self._determine_search_type(chunk_query)
            
            # Execute appropriate search strategy
            if search_type == SearchType.TEXT:
                results = await self.text_strategy.execute_search(chunk_query, limit, offset)
            elif search_type == SearchType.VECTOR:
                results = await self.vector_strategy.execute_search(chunk_query, limit, offset)
            elif search_type == SearchType.METADATA:
                results = await self.metadata_strategy.execute_search(chunk_query, limit, offset)
            elif search_type == SearchType.HYBRID:
                results = await self.hybrid_strategy.execute_search(chunk_query, limit, offset)
            else:
                results = await self._execute_combined_search(chunk_query, limit, offset)
            
            # Cache results
            if use_cache and results:
                cache_key = self._generate_cache_key(chunk_query, limit, offset)
                self._cache_results(cache_key, results)
            
            # Record performance metrics
            execution_time = time.time() - start_time
            self._record_metrics(search_type, execution_time, len(results))
            
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def _execute_combined_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Execute combined search using multiple strategies.
        
        Args:
            chunk_query: ChunkQuery object with search parameters
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of combined search results
        """
        all_results = []
        
        # Execute text search if applicable
        if chunk_query.search_query or chunk_query.text:
            text_results = await self.text_strategy.execute_search(chunk_query, limit, offset)
            all_results.extend(text_results)
        
        # Execute vector search if applicable
        if chunk_query.embedding:
            vector_results = await self.vector_strategy.execute_search(chunk_query, limit, offset)
            all_results.extend(vector_results)
        
        # Execute metadata search if applicable
        flat_query = chunk_query.to_flat_dict(for_redis=True)
        if flat_query:
            metadata_results = await self.metadata_strategy.execute_search(chunk_query, limit, offset)
            all_results.extend(metadata_results)
        
        # Combine and rank results
        return self._combine_and_rank_results(all_results, limit, offset)
    
    def _combine_and_rank_results(
        self,
        results: List[SearchResult],
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Combine and rank search results.
        
        Args:
            results: List of search results to combine
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            Combined and ranked results
        """
        # Group results by UUID
        uuid_scores = {}
        uuid_metadata = {}
        uuid_search_types = {}
        
        for result in results:
            if result.uuid not in uuid_scores:
                uuid_scores[result.uuid] = []
                uuid_metadata[result.uuid] = result.metadata
                uuid_search_types[result.uuid] = result.search_type
            
            uuid_scores[result.uuid].append(result.score)
        
        # Calculate average scores
        combined_results = []
        for uuid, scores in uuid_scores.items():
            avg_score = sum(scores) / len(scores)
            combined_results.append(SearchResult(
                uuid=uuid,
                score=avg_score,
                metadata=uuid_metadata[uuid],
                search_type=uuid_search_types[uuid],
                execution_time=0.0
            ))
        
        # Sort by score (descending)
        combined_results.sort(key=lambda x: x.score, reverse=True)
        
        # Apply pagination
        start = offset or 0
        end = start + (limit or len(combined_results))
        
        return combined_results[start:end]
    
    def _generate_cache_key(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Generate cache key for search results.
        
        Args:
            chunk_query: ChunkQuery object
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            Cache key string
        """
        import hashlib
        
        # Create cache key from query parameters
        cache_data = {
            'query': chunk_query.to_json_dict(),
            'limit': limit,
            'offset': offset
        }
        
        cache_json = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_json.encode()).hexdigest()
    
    def _get_cached_results(self, cache_key: str) -> Optional[List[SearchResult]]:
        """
        Get cached search results.
        
        Args:
            cache_key: Cache key for results
            
        Returns:
            Cached results or None if not found
        """
        return self._search_cache.get(cache_key)
    
    def _cache_results(self, cache_key: str, results: List[SearchResult]) -> None:
        """
        Cache search results.
        
        Args:
            cache_key: Cache key for results
            results: Search results to cache
        """
        self._search_cache[cache_key] = results
    
    def _record_metrics(
        self,
        search_type: str,
        execution_time: float,
        result_count: int
    ) -> None:
        """
        Record performance metrics.
        
        Args:
            search_type: Type of search executed
            execution_time: Time taken for execution
            result_count: Number of results returned
        """
        import time
        
        metric = {
            'search_type': search_type,
            'execution_time': execution_time,
            'result_count': result_count,
            'timestamp': time.time()
        }
        
        self._performance_metrics.append(metric)
        
        # Keep only recent metrics
        if len(self._performance_metrics) > 1000:
            self._performance_metrics = self._performance_metrics[-500:]
    
    def get_performance_metrics(self) -> List[Dict[str, Any]]:
        """
        Get performance metrics.
        
        Returns:
            List of performance metrics
        """
        return self._performance_metrics.copy()
    
    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._search_cache.clear()
        logger.info("Search cache cleared")
    
    def clear_metrics(self) -> None:
        """Clear performance metrics."""
        self._performance_metrics.clear()
        logger.info("Performance metrics cleared")

# Factory function
def create_chunk_query_index_manager(
    redis_client: redis.Redis,
    embedding_service=None,
    config: Optional[Dict[str, Any]] = None
) -> ChunkQueryIndexManager:
    """
    Factory function to create ChunkQueryIndexManager.
    
    Args:
        redis_client: Redis client for operations
        embedding_service: Service for generating embeddings
        config: Optional configuration
        
    Returns:
        Configured ChunkQueryIndexManager instance
    """
    return ChunkQueryIndexManager(redis_client, embedding_service, config)
