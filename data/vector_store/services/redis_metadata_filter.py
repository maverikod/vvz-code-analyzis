"""
Redis Metadata Filter and Search Service

This module provides the RedisMetadataFilterService class, which handles both
metadata filtering and vector search operations for vector store records.

Core Features:
- Unified search interface combining text search, vector search, and metadata filtering
- Support for ChunkQuery objects with complex filtering criteria
- Text vectorization and vector similarity search
- Metadata filtering with type conversion and operator support
- Soft delete handling and pagination
- Performance optimization through batch operations
- AST-based filtering using chunk_metadata_adapter FilterExecutor

Architecture:
- Works with flat dictionary format from Redis
- Integrates with VectorIndexManager for UUID mappings
- Supports SemanticChunk model validation
- Handles ChunkQuery parsing and execution
- Coordinates with FAISS for vector operations
- Coordinates with embedding service for text vectorization
- Uses FilterExecutor for advanced AST-based filtering

Search Strategies:
1. Text search: Vectorize text and perform similarity search
2. Vector search: Direct vector similarity search
3. Metadata filtering: Filter by ChunkQuery criteria using AST
4. Combined search: Intersection of vector and metadata results

Usage:
    service = RedisMetadataFilterService(
        redis_client=redis_client,
        vector_index_manager=vector_index_manager,
        faiss_service=faiss_service,
        embedding_service=embedding_service
    )
    results = await service.search(
        search_text="machine learning",
        chunk_query=ChunkQuery(category="science"),
        limit=10
    )
"""

import logging
import json
import time
import numpy as np
import redis.asyncio as redis
from typing import Dict, List, Any, Optional, Union, Tuple, Set, TYPE_CHECKING
from chunk_metadata_adapter import SemanticChunk
from chunk_metadata_adapter.chunk_query import ChunkQuery
from chunk_metadata_adapter.filter_executor import FilterExecutor
from chunk_metadata_adapter.ast_nodes import FieldCondition, LogicalOperator, TypedValue, ASTNodeFactory

from vector_store.services.faiss_index_service import FaissIndexService
from vector_store.services.filter_type_converter import FilterTypeConverter
from vector_store.utils.redis_utils import ensure_str_key, get_id_to_idx_mapping

if TYPE_CHECKING:
    from vector_store.services.redis_metadata_crud import RedisMetadataCRUDService
from vector_store.exceptions import (
    FaissSearchError, ServiceInitializationError, RedisOperationError
)
from vector_store.services.index_manager.base import (
    IndexManagerError, IndexNotFoundError, IndexAlreadyExistsError, IndexOperationError
)

logger = logging.getLogger("vector_store.redis_metadata_filter")
detailed_logger = logging.getLogger("vector_store.detailed")


class RedisMetadataFilterService:
    """
    Unified search and filtering service for vector store.
    
    Combines text search, vector search, and metadata filtering to provide
    comprehensive search capabilities.
    
    Features:
    - Text search with automatic vectorization
    - Vector similarity search with FAISS
    - Metadata filtering with ChunkQuery support
    - Combined search with intersection logic
    - Soft delete handling
    - Pagination support
    - Type-safe ChunkQuery processing
    - AST-based filtering using FilterExecutor
    
    Architecture:
    - VectorIndexManager: UUID ↔ FAISS idx mappings
    - FaissIndexService: Vector operations (search)
    - RedisMetadataCRUDService: Metadata CRUD operations
    - EmbeddingService: Text vectorization
    - FilterExecutor: AST-based filtering evaluation
    
    Search Logic:
    1. Text search: Vectorize text → FAISS search → get UUIDs
    2. Vector search: Direct FAISS search → get UUIDs
    3. Metadata filtering: Filter by ChunkQuery → get UUIDs
    4. Combined: Intersection of vector UUIDs and metadata UUIDs
    """

    def __init__(self,
                 redis_client: redis.Redis,
                 faiss_service: FaissIndexService,
                 embedding_service=None,
                 crud_service: Optional['RedisMetadataCRUDService'] = None,
                 vector_store_service=None):
        """
        Initialize filter service with required components.

        Args:
            redis_client: Redis client for metadata operations and UUID mappings
            faiss_service: FAISS service for vector operations
            embedding_service: Service for text vectorization (optional)
            crud_service: CRUD service for metadata operations (optional)
            vector_store_service: Vector store service for BM25 operations (optional)

        Raises:
            ServiceInitializationError: If initialization fails
        """
        if not redis_client:
            raise ServiceInitializationError("RedisMetadataFilterService", "Redis client is required")
        if not faiss_service:
            raise ServiceInitializationError("RedisMetadataFilterService", "FAISS service is required")
        
        self.redis = redis_client
        self.faiss_service = faiss_service
        self.embedding_service = embedding_service
        self.crud_service = crud_service
        self.vector_store_service = vector_store_service
        
        # Initialize FilterExecutor for AST-based filtering
        self.filter_executor = FilterExecutor(regex_timeout=1.0)
        
        logger.info("RedisMetadataFilterService initialized successfully")

    # Properties
    @property
    def vector_size(self) -> int:
        """
        Get vector dimension from FAISS service.
        
        Returns:
            Vector dimension (typically 384)
        """
        return getattr(self.faiss_service, 'vector_size', 384)

    # Core Search Method
    async def search(self,
                    chunk_query: ChunkQuery,
                    limit: Optional[int] = None,
                    offset: Optional[int] = None,
                    include_vectors: bool = True,
                    include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Единый метод поиска с пересечением результатов.

        Алгоритм поиска:
        1. Если задана строка поиска - BM25 поиск
        2. Если задан коэффициент для семантического поиска - поиск по векторам
        3. Если задан коэффициент для BM25 - поиск по индексу BM25
        4. Если заданы условия фильтрации - поиск по фильтру
        5. Если заданы сразу несколько вариантов - берем пересечение

        Args:
            chunk_query: ChunkQuery с критериями поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            include_vectors: Включать ли векторы в результаты
            include_deleted: Включать ли удаленные записи

        Returns:
            Список найденных записей с метаданными

        Raises:
            ValueError: Если ChunkQuery не предоставлен
        """
        if not chunk_query:
            raise ValueError("ChunkQuery must be provided")
        
        if limit is not None and limit < 0:
            raise ValueError("Limit must be non-negative if specified")
        if offset is not None and offset < 0:
            raise ValueError("Offset must be non-negative if specified")
        
        logger.info(f"Starting search with ChunkQuery: text='{chunk_query.text}', has_embedding={chunk_query.embedding is not None}, limit={limit}, offset={offset}")
        
        # Сбор результатов от разных методов поиска
        result_sets = []
        
        # 1. BM25 поиск (если задана строка поиска И коэффициент > 0)
        if (chunk_query.search_query or chunk_query.text) and getattr(chunk_query, 'bm25_k1', 0) > 0:
            search_text = chunk_query.search_query or chunk_query.text
            logger.info(f"Performing BM25 search with query: {search_text}, k1: {getattr(chunk_query, 'bm25_k1', 1.2)}")
            try:
                bm25_results = await self._bm25_search(search_text, limit=None, include_deleted=include_deleted)
                bm25_uuids = {result['uuid'] for result in bm25_results}
                result_sets.append(bm25_uuids)
                logger.info(f"BM25 search returned {len(bm25_uuids)} UUIDs")
            except Exception as e:
                logger.warning(f"BM25 search failed: {e}")
        
        # 2. Семантический поиск (если задан эмбеддинг И коэффициент > 0)
        if chunk_query.embedding and getattr(chunk_query, 'semantic_weight', 0) > 0:
            logger.info(f"Performing semantic search with weight: {getattr(chunk_query, 'semantic_weight', 1.0)}")
            try:
                semantic_results = await self._vector_search(chunk_query.embedding, limit=None, include_deleted=include_deleted)
                semantic_uuids = set(semantic_results)
                result_sets.append(semantic_uuids)
                logger.info(f"Semantic search returned {len(semantic_uuids)} UUIDs")
            except Exception as e:
                logger.warning(f"Semantic search failed: {e}")
        
        # 3. Фильтрация по метаданным (если есть хотя бы один фильтр)
        metadata_filters = {}
        if chunk_query.metadata:
            metadata_filters.update(chunk_query.metadata)
        if chunk_query.category:
            metadata_filters['category'] = chunk_query.category
        if chunk_query.tags:
            metadata_filters['tags'] = chunk_query.tags
        if chunk_query.type:
            metadata_filters['type'] = chunk_query.type
        if chunk_query.language:
            metadata_filters['language'] = chunk_query.language
        if chunk_query.is_deleted is not None:
            metadata_filters['is_deleted'] = chunk_query.is_deleted
        
        if metadata_filters:
            logger.info(f"Performing metadata filtering with filters: {metadata_filters}")
            try:
                metadata_results = await self._metadata_filter_search(chunk_query, limit=None, include_deleted=include_deleted)
                metadata_uuids = {result['uuid'] for result in metadata_results}
                result_sets.append(metadata_uuids)
                logger.info(f"Metadata filtering returned {len(metadata_uuids)} UUIDs")
            except Exception as e:
                logger.warning(f"Metadata filtering failed: {e}")
        
        # 4. Проверка наличия условий отбора
        if len(result_sets) == 0:
            raise ValueError("No search criteria provided. At least one search condition must be specified (text with bm25_k1 > 0, embedding with semantic_weight > 0, or metadata filters including is_deleted)")
        
        # 5. Оптимизированное вычисление пересечения результатов
        if len(result_sets) > 1:
            # Оптимизация: сортируем множества по размеру для эффективного пересечения
            sorted_sets = sorted(result_sets, key=len)
            final_uuids = sorted_sets[0]  # Начинаем с самого маленького множества
            
            # Последовательно вычисляем пересечение
            for current_set in sorted_sets[1:]:
                final_uuids = final_uuids.intersection(current_set)
                if not final_uuids:  # Раннее прерывание если пересечение пустое
                    break
            
            logger.info(f"Optimized intersection of {len(result_sets)} search methods: {len(final_uuids)} results")
        else:
            # Один метод - используем его результаты
            final_uuids = result_sets[0]
            logger.info(f"Using single search method results: {len(final_uuids)} results")
        
        # 6. Оптимизированная пагинация и получение результатов
        results = []
        if final_uuids:
            # Оптимизированная пагинация: применяем лимиты до получения метаданных
            uuids_list = self._optimized_pagination(list(final_uuids), limit, offset)
            
            # Получение метаданных только для нужных UUID
            results = await self._get_metadata_for_uuids(uuids_list, include_vectors=include_vectors)
        
        logger.info(f"Search completed: {len(results)} results")
        return results
        if include_vectors and results:
            await self._restore_vectors_from_redis(results)
        
        logger.info(f"Search completed: {len(results)} results")
        return results

    # Internal Search Methods
    async def _vectorize_text(self, text: str) -> Optional[np.ndarray]:
        """
        Vectorize text using embedding service.

        Args:
            text: Text to vectorize

        Returns:
            Vector as numpy array, or None if vectorization fails

        Raises:
            FaissSearchError: If vectorization fails
        """
        if not self.embedding_service:
            logger.warning("[_vectorize_text] No embedding service available")
            return None
        
        try:
            vector = await self.embedding_service.get_embedding(text)
            if vector is not None:
                return np.array(vector, dtype=np.float32)
            return None
        except Exception as e:
            logger.error(f"[_vectorize_text] Vectorization failed: {e}")
            raise FaissSearchError(f"Text vectorization failed: {e}", "_vectorize_text")

    async def _text_search(self,
                          search_text: str,
                          limit: Optional[int] = None,
                          include_deleted: bool = False) -> List[str]:
        """
        Perform text search by vectorizing text and searching in FAISS.

        Args:
            search_text: Text to search for
            limit: Maximum number of results
            include_deleted: Whether to include soft-deleted records

        Returns:
            List of UUIDs matching the text search

        Raises:
            FaissSearchError: If vectorization or search fails
        """
        # Vectorize the search text
        query_vector = await self._vectorize_text(search_text)
        if query_vector is None:
            logger.warning(f"Failed to vectorize search text: {search_text}")
            return []
        
        # Perform vector search
        return await self._vector_search(query_vector, limit, include_deleted)

    async def _vector_search(self,
                           query_vector: np.ndarray,
                           limit: Optional[int] = None,
                           include_deleted: bool = False) -> List[str]:
        """
        Perform vector similarity search in FAISS and map indices to UUIDs via faiss_idx:{idx} in Redis.

        Args:
            query_vector: Query vector for similarity search (numpy array)
            limit: Maximum number of results
            include_deleted: Whether to include soft-deleted records

        Returns:
            List of UUIDs matching the vector search

        Raises:
            FaissSearchError: If vector search fails
        """
        try:
            # Perform FAISS search to get indices
            search_result = await self.faiss_service.search_vector(query_vector, limit or 100)
            if not search_result or len(search_result) != 2:
                logger.warning(f"FAISS search returned invalid result: {search_result}")
                return []
                
            distances, indices = search_result
            logger.info(f"FAISS search returned {len(indices)} indices: {indices[:5]}...")
            uuids = []
            for idx in indices:
                if idx >= 0:
                    uuid = await self.redis.get(f"faiss_idx:{idx}")
                    if uuid:
                        if isinstance(uuid, bytes):
                            uuid = uuid.decode("utf-8")
                        uuids.append(uuid)
            # Remove duplicates while preserving order
            seen = set()
            unique_uuids = []
            for uuid in uuids:
                if uuid not in seen:
                    seen.add(uuid)
                    unique_uuids.append(uuid)
            logger.info(f"Found {len(unique_uuids)} unique UUIDs from vector search")
            # Filter out deleted records if needed
            if not include_deleted and unique_uuids:
                metadata_list = await self._get_metadata_for_uuids(unique_uuids, include_vectors=False)
                filtered_uuids = []
                for metadata in metadata_list:
                    if metadata and not metadata.get('is_deleted', False):
                        filtered_uuids.append(metadata.get('uuid'))
                logger.info(f"After filtering deleted records: {len(filtered_uuids)} UUIDs")
                return filtered_uuids
            return unique_uuids
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise FaissSearchError(f"Vector search failed: {e}", "_vector_search")

    async def _metadata_filter_search(self,
                                    chunk_query: ChunkQuery,
                                    limit: Optional[int] = None,
                                    include_deleted: bool = False) -> List[str]:
        """
        Perform metadata filtering using ChunkQuery criteria with AST-based evaluation.

        Args:
            chunk_query: ChunkQuery with filtering criteria
            limit: Maximum number of results
            include_deleted: Whether to include soft-deleted records

        Returns:
            List of UUIDs matching the metadata criteria

        Raises:
            RedisOperationError: If metadata filtering fails
        """
        try:
            logger.info(f"_metadata_filter_search called with chunk_query: {chunk_query}")
            # Try to use field indexes for simple field filters first
            if self.crud_service and chunk_query:
                field_filters = self._extract_simple_field_filters(chunk_query)
                if field_filters:
                    # Use optimized field index search via IndexManager
                    logger.info(f"Using field filters: {field_filters}")
                    
                    # Check if IndexManager is available
                    if not hasattr(self.crud_service, 'index_manager') or not self.crud_service.index_manager:
                        logger.warning("IndexManager not available - falling back to full scan")
                        matching_uuids = []
                    else:
                        # Use IndexManager's search methods directly
                        if len(field_filters) > 1:
                            # Multiple field filters - use combined search
                            matching_uuids = await self.crud_service.index_manager.search_combined(field_filters)
                        else:
                            # Single field filter - use field search
                            field_name, field_value = next(iter(field_filters.items()))
                            matching_uuids = await self.crud_service.index_manager.search_by_field(field_name, field_value)
                    
                    logger.info(f"Found {len(matching_uuids)} UUIDs using field indexes: {matching_uuids[:5] if matching_uuids else 'none'}")
                    
                    # Apply additional filtering if needed
                    if matching_uuids and self._has_complex_filters(chunk_query):
                        logger.info("Has complex filters - applying additional filtering")
                        # Get metadata for additional filtering
                        logger.info(f"Getting metadata for {len(matching_uuids)} UUIDs: {matching_uuids}")
                        metadata_list = await self._get_metadata_for_uuids(matching_uuids, include_vectors=False)
                        filtered_uuids = []
                        
                        for i, metadata in enumerate(metadata_list):
                            if not metadata:
                                continue
                            
                            uuid = matching_uuids[i]
                            logger.info(f"Processing metadata for {uuid}: {metadata}")
                            
                            # Check if deleted (unless include_deleted=True)
                            if not include_deleted and metadata.get('is_deleted', False):
                                logger.info(f"Skipping {uuid} - marked as deleted")
                                continue
                            
                            # Apply complex ChunkQuery filters
                            matches = self._matches_chunk_query_ast(metadata, chunk_query)
                            logger.info(f"ChunkQuery match for {uuid}: {matches}")
                            if matches:
                                filtered_uuids.append(uuid)
                                
                                # Apply limit if specified
                                if limit and len(filtered_uuids) >= limit:
                                    return filtered_uuids
                        
                        logger.info(f"Complex filtering returned {len(filtered_uuids)} UUIDs")
                        return filtered_uuids
                    else:
                        logger.info("No complex filters - returning simple field filter results")
                        # Simple field filters only - return results directly
                        logger.info(f"Returning {len(matching_uuids)} UUIDs from simple field filters")
                        if limit:
                            result = matching_uuids[:limit]
                            logger.info(f"Limited to {len(result)} UUIDs")
                            return result
                        return matching_uuids
                else:
                    logger.info("No field filters found")
            
            # FALLBACK: When no field filters, get ALL records from Redis
            logger.info("No field filters found - getting all records from Redis")
            if self.crud_service:
                try:
                    all_uuids = await self.crud_service.get_all_record_ids()
                    logger.info(f"Retrieved {len(all_uuids)} UUIDs from Redis")
                    
                    # Filter out soft-deleted records if needed
                    if not include_deleted and all_uuids:
                        # Get deletion status for all UUIDs
                        deletion_status = await self._get_deletion_status(all_uuids)
                        all_uuids = [uuid for uuid, is_deleted in zip(all_uuids, deletion_status) if not is_deleted]
                        logger.info(f"After filtering deleted records: {len(all_uuids)} UUIDs")
                    
                    # Apply ChunkQuery filtering if needed
                    if all_uuids and self._has_complex_filters(chunk_query):
                        logger.info("Applying complex filters to all records")
                        metadata_list = await self._get_metadata_for_uuids(all_uuids, include_vectors=False)
                        filtered_uuids = []
                        
                        for i, metadata in enumerate(metadata_list):
                            if not metadata:
                                continue
                            
                            uuid = all_uuids[i]
                            
                            # Check if deleted (unless include_deleted=True)
                            if not include_deleted and metadata.get('is_deleted', False):
                                continue
                            
                            # Apply complex ChunkQuery filters
                            matches = self._matches_chunk_query_ast(metadata, chunk_query)
                            if matches:
                                filtered_uuids.append(uuid)
                                
                                # Apply limit if specified
                                if limit and len(filtered_uuids) >= limit:
                                    return filtered_uuids
                        
                        logger.info(f"Complex filtering returned {len(filtered_uuids)} UUIDs")
                        return filtered_uuids
                    else:
                        logger.info("No complex filters - returning all records")
                        if limit:
                            result = all_uuids[:limit]
                            logger.info(f"Limited to {len(result)} UUIDs")
                            return result
                        return all_uuids
                except RedisOperationError as e:
                    logger.error(f"Redis operation failed while getting all UUIDs: {e}")
                    return []
                except Exception as e:
                    logger.error(f"Unexpected error while getting all UUIDs: {e}")
                    return []
            else:
                logger.warning("No CRUD service available - returning empty result")
                return []
                
        except RedisOperationError as e:
            logger.error(f"Redis operation failed during metadata filtering: {e}")
            raise e
        except IndexNotFoundError as e:
            logger.error(f"Required indexes not found for metadata filtering: {e}")
            raise RedisOperationError("index_not_found", f"Required indexes not found: {e}")
        except IndexOperationError as e:
            logger.error(f"Index operation failed during metadata filtering: {e}")
            raise RedisOperationError("index_operation_failed", f"Index operation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during metadata filtering: {e}")
            raise RedisOperationError("metadata_filtering_failed", f"Unexpected error: {e}")
    
    async def _get_deletion_status(self, uuids: List[str]) -> List[bool]:
        """
        Get deletion status for a list of UUIDs.
        
        Args:
            uuids: List of UUIDs to check
            
        Returns:
            List of boolean values indicating deletion status
        """
        try:
            if not uuids:
                return []
            
            # Get metadata for all UUIDs
            metadata_list = await self._get_metadata_for_uuids(uuids, include_vectors=False)
            deletion_status = []
            
            for metadata in metadata_list:
                if metadata is None:
                    deletion_status.append(False)  # Treat missing records as not deleted
                else:
                    deletion_status.append(metadata.get('is_deleted', False))
            
            return deletion_status
            
        except Exception as e:
            logger.error(f"Failed to get deletion status: {e}")
            # Return all False in case of error
            return [False] * len(uuids)

    # Helper Methods
    async def _get_metadata_for_uuids(self,
                                    uuids: List[str],
                                    include_vectors: bool = True) -> List[Dict[str, Any]]:
        """
        Retrieve metadata for list of UUIDs.

        Args:
            uuids: List of UUIDs to retrieve metadata for
            include_vectors: Whether to include vectors in results

        Returns:
            List of metadata dictionaries (None for not found records)

        Raises:
            RedisOperationError: If metadata retrieval fails
        """
        if not uuids:
            return []
        
        try:
            # Use CRUD service if available, otherwise direct Redis access
            if self.crud_service:
                try:
                    logger.info(f"Using CRUD service to get metadata for {len(uuids)} UUIDs")
                    metadata_list = await self.crud_service.get_chunks(uuids, include_vectors=include_vectors)
                    logger.info(f"CRUD service returned {len(metadata_list)} metadata items")
                except Exception as e:
                    logger.error(f"Failed to get metadata for UUIDs via CRUD service: {e}")
                    raise RedisOperationError("get_chunks", f"Failed to get metadata for UUIDs: {e}")
            else:
                # Direct Redis access
                metadata_list = []
                for uuid in uuids:
                    try:
                        # Get hash data
                        hash_key = f"vector:{uuid}"
                        hash_data = await self.redis.hgetall(hash_key)
                        
                        if not hash_data:
                            metadata_list.append(None)
                            continue
                        
                        # Check if hash_data is a dict
                        if not isinstance(hash_data, dict):
                            logger.warning(f"Hash data for {uuid} is not a dict: {type(hash_data)}")
                            metadata_list.append(None)
                            continue
                        
                        # Decode bytes to strings
                        meta = {}
                        for k, v in hash_data.items():
                            key = k.decode('utf-8') if isinstance(k, bytes) else k
                            value = v.decode('utf-8') if isinstance(v, bytes) else v
                            meta[key] = value
                        
                        # Get list fields
                        list_keys = await self.redis.keys(f"*:{uuid}")
                        for list_key in list_keys:
                            if isinstance(list_key, bytes):
                                list_key = list_key.decode('utf-8')
                            # Skip the main hash key
                            if list_key == hash_key:
                                continue
                            field_name = list_key.split(':', 1)[0]
                            try:
                                # Check key type and get data accordingly
                                key_type = await self.redis.type(list_key)
                                if isinstance(key_type, bytes):
                                    key_type = key_type.decode('utf-8')
                                
                                if key_type == 'list':
                                    # For LIST type, use LRANGE
                                    list_data = await self.redis.lrange(list_key, 0, -1)
                                    meta[field_name] = [v.decode('utf-8') if isinstance(v, bytes) else v for v in list_data]
                                elif key_type == 'set':
                                    # For SET type, use SMEMBERS
                                    set_data = await self.redis.smembers(list_key)
                                    meta[field_name] = [v.decode('utf-8') if isinstance(v, bytes) else v for v in set_data]
                                elif key_type == 'string':
                                    # For STRING type, use GET
                                    string_data = await self.redis.get(list_key)
                                    if string_data:
                                        if isinstance(string_data, bytes):
                                            string_data = string_data.decode('utf-8')
                                        meta[field_name] = string_data
                            except Exception as e:
                                logger.warning(f"Failed to get data for {list_key}: {e}")
                                continue
                        
                        # Restore types using SemanticChunk
                        try:
                            from chunk_metadata_adapter import SemanticChunk
                            logger.info(f"Restoring types for {uuid}, meta keys: {list(meta.keys())}")
                            if 'uuid' in meta:
                                logger.info(f"UUID in meta: type={type(meta['uuid'])}, value={meta['uuid']}")
                            flat_meta = SemanticChunk.from_flat_dict(meta, from_redis=True).model_dump()
                            metadata_list.append(flat_meta)
                        except Exception as e:
                            logger.warning(f"Failed to restore types for {uuid}: {e}")
                            metadata_list.append(meta)
                            
                    except Exception as e:
                        logger.error(f"Failed to get metadata for {uuid}: {e}")
                        # For direct Redis access, raise the error instead of returning None
                        raise RedisOperationError("hgetall", f"Failed to get metadata for {uuid}: {e}")
            
            # Remove vectors if not requested
            if not include_vectors:
                for metadata in metadata_list:
                    if metadata:
                        metadata.pop('embedding', None)
            
            return metadata_list
            
        except RedisOperationError:
            # Re-raise RedisOperationError
            raise
        except Exception as e:
            logger.error(f"Failed to get metadata for UUIDs: {e}")
            raise RedisOperationError("get_metadata_for_uuids", f"Failed to get metadata for UUIDs: {e}")

    async def _apply_pagination(self,
                              results: List[Dict[str, Any]],
                              limit: Optional[int],
                              offset: Optional[int]) -> List[Dict[str, Any]]:
        """
        Apply pagination to search results.

        Args:
            results: List of search results
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Paginated list of results
        """
        if offset:
            results = results[offset:]
        if limit:
            results = results[:limit]
        return results

    def _extract_vectors_from_chunk_query(self, chunk_query: ChunkQuery) -> List[np.ndarray]:
        """
        Extract vectors from ChunkQuery if present.

        Args:
            chunk_query: ChunkQuery with potential embedding field

        Returns:
            List of numpy arrays if embeddings are present and valid, empty list otherwise
        """
        vectors = []
        if chunk_query.embedding is not None:
            try:
                # Handle single vector (list of floats)
                if isinstance(chunk_query.embedding, list):
                    # Check if it's a list of numbers (single vector)
                    if all(isinstance(x, (int, float)) for x in chunk_query.embedding):
                        vector = np.array(chunk_query.embedding, dtype=np.float32)
                        vectors.append(vector)
                    else:
                        # Check if it's a list of lists (multiple vectors)
                        if all(isinstance(x, (list, tuple)) for x in chunk_query.embedding):
                            for i, emb in enumerate(chunk_query.embedding):
                                try:
                                    vector = np.array(emb, dtype=np.float32)
                                    vectors.append(vector)
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"Invalid embedding at index {i}: {e}")
                        else:
                            logger.warning(f"Invalid embedding format: expected list of numbers or list of lists")
                # Handle tuple of vectors
                elif isinstance(chunk_query.embedding, tuple):
                    for i, emb in enumerate(chunk_query.embedding):
                        if isinstance(emb, (list, tuple)):
                            try:
                                vector = np.array(emb, dtype=np.float32)
                                vectors.append(vector)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Invalid embedding at index {i}: {e}")
                        else:
                            logger.warning(f"Invalid embedding format at index {i}: expected list, got {type(emb)}")
                else:
                    logger.warning(f"Invalid embedding type: {type(chunk_query.embedding)}")
            except Exception as e:
                logger.error(f"Failed to extract vectors from ChunkQuery: {e}")
        
        return vectors

    def _has_metadata_criteria(self, chunk_query: ChunkQuery) -> bool:
        """
        Check if ChunkQuery has metadata filtering criteria.

        Args:
            chunk_query: ChunkQuery to check

        Returns:
            True if query has metadata criteria (non-None values excluding embedding), False otherwise
        """
        # Check if ChunkQuery has filter_expr (AST-based filtering)
        if hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr:
            logger.info(f"Found filter_expr in _has_metadata_criteria: {chunk_query.filter_expr}")
            return True
        
        # Convert to dict and check for non-None values (excluding embedding)
        query_dict = chunk_query.model_dump()
        
        # Remove embedding field as it's handled separately
        query_dict.pop('embedding', None)
        
        # Check if any field has a value
        has_criteria = any(value is not None for value in query_dict.values())
        logger.info(f"Metadata criteria check: {has_criteria} (fields: {list(query_dict.keys())})")
        return has_criteria

    def _matches_chunk_query_ast(self, chunk_metadata: Dict[str, Any], chunk_query: ChunkQuery) -> bool:
        """
        Check if chunk metadata matches ChunkQuery criteria using AST-based evaluation.

        This method uses the FilterExecutor from chunk_metadata_adapter to evaluate
        complex filter expressions with full operator support.

        Args:
            chunk_metadata: Chunk metadata dictionary
            chunk_query: ChunkQuery with filtering criteria

        Returns:
            True if metadata matches query criteria, False otherwise
        """
        if not chunk_query:
            return True
        
        logger.info(f"_matches_chunk_query_ast called with metadata: {chunk_metadata}")
        logger.info(f"ChunkQuery has filter_expr: {hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr}")
        logger.info(f"ChunkQuery metadata: {getattr(chunk_query, 'metadata', None)}")
        
        try:
            # Check if ChunkQuery has a filter_expr (AST-based filtering)
            if hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr:
                # Use the built-in AST evaluation from ChunkQuery
                logger.debug("Using AST-based filtering")
                try:
                    result = chunk_query.matches(chunk_metadata)
                    logger.debug(f"AST-based filtering result: {result}")
                    return result
                except Exception as ast_error:
                    logger.warning(f"AST-based filtering failed: {ast_error}, falling back to legacy method")
                    return self._matches_chunk_query_legacy(chunk_metadata, chunk_query)
            
            # Fallback to legacy field-based filtering
            logger.debug("Using legacy field-based filtering")
            result = self._matches_chunk_query_legacy(chunk_metadata, chunk_query)
            logger.debug(f"Legacy filtering result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"AST-based filtering failed: {e}, falling back to legacy method")
            return self._matches_chunk_query_legacy(chunk_metadata, chunk_query)

    def _matches_chunk_query_legacy(self, chunk_metadata: Dict[str, Any], chunk_query: ChunkQuery) -> bool:
        """
        Legacy method for checking if chunk metadata matches ChunkQuery criteria.
        
        This is a fallback method that handles simple field-based filtering
        when AST-based filtering is not available or fails.

        Args:
            chunk_metadata: Chunk metadata dictionary
            chunk_query: ChunkQuery with filtering criteria

        Returns:
            True if metadata matches query criteria, False otherwise
        """
        if not chunk_query:
            return True
        
        # Handle None metadata
        if chunk_metadata is None:
            chunk_metadata = {}
        
        # Get query data - prefer model_dump, fallback to direct access
        if hasattr(chunk_query, 'model_dump'):
            query_dict = chunk_query.model_dump()
        else:
            # For ChunkQuery, we need to access fields directly
            query_dict = {}
            # Add metadata if present
            if hasattr(chunk_query, 'metadata') and chunk_query.metadata:
                query_dict['metadata'] = chunk_query.metadata
            # Add other fields that might be set
            for field in ['search_text', 'embedding', 'text', 'body', 'category', 'title']:
                if hasattr(chunk_query, field) and getattr(chunk_query, field) is not None:
                    query_dict[field] = getattr(chunk_query, field)
        

        
                    # Handle metadata field specifically
            if 'metadata' in query_dict and query_dict['metadata']:
                metadata_query = query_dict['metadata']
                logger.debug(f"Processing metadata query: {metadata_query}")
                if isinstance(metadata_query, dict):
                    for field, query_value in metadata_query.items():
                        metadata_value = chunk_metadata.get(field)
                        
                        # Debug logging
                        logger.debug(f"Comparing field '{field}': query_value={query_value}, metadata_value={metadata_value}")
                    
                        # Skip if metadata_value is None and query_value is not None
                        if metadata_value is None and query_value is not None:
                            logger.debug(f"Field '{field}' not found in metadata")
                            return False
                        
                        # Handle different field types
                        if isinstance(query_value, str):
                            # String comparison - case-insensitive substring search
                            if not isinstance(metadata_value, str):
                                return False
                            if query_value.lower() not in metadata_value.lower():
                                return False
                                
                        elif isinstance(query_value, dict):
                            # Handle MongoDB-style operators
                            if '$in' in query_value:
                                # Handle $in operator
                                if not isinstance(metadata_value, (list, tuple)):
                                    metadata_value = [metadata_value] if metadata_value is not None else []
                                
                                # Convert all values to strings for comparison
                                query_values = [str(qv).lower() for qv in query_value['$in']]
                                metadata_values = [str(mv).lower() for mv in metadata_value if mv is not None]
                                
                                if not any(qv in metadata_values for qv in query_values):
                                    return False
                            elif '$eq' in query_value:
                                # Handle $eq operator - exact match
                                expected_value = query_value['$eq']
                                if metadata_value != expected_value:
                                    logger.debug(f"$eq comparison failed: {metadata_value} != {expected_value}")
                                    return False
                            elif '$gte' in query_value:
                                # Handle $gte operator - greater than or equal
                                expected_value = query_value['$gte']
                                try:
                                    if isinstance(metadata_value, str):
                                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                    else:
                                        metadata_num = metadata_value
                                    if metadata_num < expected_value:
                                        return False
                                except (ValueError, TypeError):
                                    return False
                            elif '$gt' in query_value:
                                # Handle $gt operator - greater than
                                expected_value = query_value['$gt']
                                try:
                                    if isinstance(metadata_value, str):
                                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                    else:
                                        metadata_num = metadata_value
                                    if metadata_num <= expected_value:
                                        return False
                                except (ValueError, TypeError):
                                    return False
                            elif '$lt' in query_value:
                                # Handle $lt operator - less than
                                expected_value = query_value['$lt']
                                try:
                                    if isinstance(metadata_value, str):
                                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                    else:
                                        metadata_num = metadata_value
                                    if metadata_num >= expected_value:
                                        return False
                                except (ValueError, TypeError):
                                    return False
                            elif '$lte' in query_value:
                                # Handle $lte operator - less than or equal
                                expected_value = query_value['$lte']
                                try:
                                    if isinstance(metadata_value, str):
                                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                    else:
                                        metadata_num = metadata_value
                                    if metadata_num > expected_value:
                                        return False
                                except (ValueError, TypeError):
                                    return False
                            elif '$range' in query_value:
                                # Handle $range operator - range check
                                range_values = query_value['$range']
                                if len(range_values) != 2:
                                    return False
                                min_val, max_val = range_values
                                try:
                                    if isinstance(metadata_value, str):
                                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                    else:
                                        metadata_num = metadata_value
                                    if metadata_num < min_val or metadata_num > max_val:
                                        return False
                                except (ValueError, TypeError):
                                    return False
                            elif '$contains' in query_value:
                                # Handle $contains operator - substring search
                                expected_value = query_value['$contains']
                                if not isinstance(metadata_value, str):
                                    return False
                                if expected_value.lower() not in metadata_value.lower():
                                    return False
                            elif '$starts_with' in query_value:
                                # Handle $starts_with operator
                                expected_value = query_value['$starts_with']
                                if not isinstance(metadata_value, str):
                                    return False
                                if not metadata_value.lower().startswith(expected_value.lower()):
                                    return False
                            elif '$ends_with' in query_value:
                                # Handle $ends_with operator
                                expected_value = query_value['$ends_with']
                                if not isinstance(metadata_value, str):
                                    return False
                                if not metadata_value.lower().endswith(expected_value.lower()):
                                    return False
                            elif '$all' in query_value:
                                # Handle $all operator - all values must be present
                                expected_values = query_value['$all']
                                if not isinstance(metadata_value, (list, tuple)):
                                    metadata_value = [metadata_value] if metadata_value is not None else []
                                
                                # Convert all values to strings for comparison
                                query_values = [str(qv).lower() for qv in expected_values]
                                metadata_values = [str(mv).lower() for mv in metadata_value if mv is not None]
                                
                                if not all(qv in metadata_values for qv in query_values):
                                    return False
                            else:
                                # Unknown operator
                                logger.warning(f"Unknown operator in query_value: {query_value}")
                                return False
                                
                        elif isinstance(query_value, (list, tuple)):
                            # List comparison - check if any query value is in metadata
                            if not isinstance(metadata_value, (list, tuple)):
                                metadata_value = [metadata_value] if metadata_value is not None else []
                            
                            # Convert all values to strings for comparison
                            query_values = [str(qv).lower() for qv in query_value]
                            metadata_values = [str(mv).lower() for mv in metadata_value if mv is not None]
                            
                            if not any(qv in metadata_values for qv in query_values):
                                return False
                                
                        elif isinstance(query_value, bool):
                            # Boolean comparison
                            logger.debug(f"Boolean comparison: query_value={query_value}, metadata_value={metadata_value}, type={type(metadata_value)}")
                            if not isinstance(metadata_value, bool):
                                # Try to convert metadata value to boolean
                                if isinstance(metadata_value, str):
                                    metadata_bool = metadata_value.lower() in ['true', '1', 'yes', 'on']
                                else:
                                    metadata_bool = bool(metadata_value)
                                logger.debug(f"Converted metadata_value to boolean: {metadata_bool}")
                                if metadata_bool != query_value:
                                    logger.debug(f"Boolean comparison failed: {metadata_bool} != {query_value}")
                                    return False
                            elif metadata_value != query_value:
                                logger.debug(f"Boolean comparison failed: {metadata_value} != {query_value}")
                                return False
                            logger.debug("Boolean comparison passed")
                                
                        elif isinstance(query_value, (int, float)):
                            # Numeric comparison
                            try:
                                if isinstance(metadata_value, str):
                                    metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                                else:
                                    metadata_num = metadata_value
                                
                                if metadata_num != query_value:
                                    return False
                            except (ValueError, TypeError):
                                return False
                                
                        else:
                            # Direct comparison for other types
                            if metadata_value != query_value:
                                return False
        
        # Handle other fields (skip metadata as it's handled above)
        # Skip automatically populated fields that shouldn't be compared
        skip_fields = [
            'embedding', 'metadata', 'filter_expr', 'created_at', 'modified_at',
            'search_fields', 'bm25_k1', 'bm25_b', 'hybrid_search', 'bm25_weight', 
            'semantic_weight', 'min_score', 'max_results', 'search_query'
        ]
        for field, query_value in query_dict.items():
            if field in skip_fields or query_value is None:
                continue
            
            metadata_value = chunk_metadata.get(field)
            
            # Debug logging for other fields
            logger.debug(f"Checking other field '{field}': query_value={query_value}, metadata_value={metadata_value}")
            
            # Skip if metadata_value is None and query_value is not None
            if metadata_value is None and query_value is not None:
                logger.debug(f"Field '{field}' not found in metadata")
                return False
            
            # Handle different field types
            if isinstance(query_value, str):
                # String comparison - exact match for direct fields
                if not isinstance(metadata_value, str):
                    logger.debug(f"String comparison failed: metadata_value is not string")
                    return False
                if query_value != metadata_value:
                    logger.debug(f"String comparison failed: '{query_value}' != '{metadata_value}'")
                    return False
                    
            elif isinstance(query_value, (list, tuple)):
                # List comparison - check if any query value is in metadata
                if not isinstance(metadata_value, (list, tuple)):
                    metadata_value = [metadata_value] if metadata_value is not None else []
                
                # Convert all values to strings for comparison
                query_values = [str(qv).lower() for qv in query_value]
                metadata_values = [str(mv).lower() for mv in metadata_value if mv is not None]
                
                if not any(qv in metadata_values for qv in query_values):
                    logger.debug(f"List comparison failed: no match found")
                    return False
                    
            elif isinstance(query_value, bool):
                # Boolean comparison
                if not isinstance(metadata_value, bool):
                    # Try to convert metadata value to boolean
                    if isinstance(metadata_value, str):
                        metadata_bool = metadata_value.lower() in ['true', '1', 'yes', 'on']
                    else:
                        metadata_bool = bool(metadata_value)
                    if metadata_bool != query_value:
                        logger.debug(f"Boolean comparison failed: {metadata_bool} != {query_value}")
                        return False
                elif metadata_value != query_value:
                    logger.debug(f"Boolean comparison failed: {metadata_value} != {query_value}")
                    return False
                    
            elif isinstance(query_value, (int, float)):
                # Numeric comparison
                try:
                    if isinstance(metadata_value, str):
                        metadata_num = float(metadata_value) if '.' in metadata_value else int(metadata_value)
                    else:
                        metadata_num = metadata_value
                    
                    if metadata_num != query_value:
                        logger.debug(f"Numeric comparison failed: {metadata_num} != {query_value}")
                        return False
                except (ValueError, TypeError):
                    logger.debug(f"Numeric comparison failed: conversion error")
                    return False
                    
            else:
                # Direct comparison for other types
                if metadata_value != query_value:
                    logger.debug(f"Direct comparison failed: {metadata_value} != {query_value}")
                    return False
        
        logger.debug("All comparisons passed, returning True")
        return True

    def _determine_search_type(self,
                             search_text: Optional[str],
                             chunk_query: Optional[ChunkQuery]) -> str:
        """
        Determine search type based on provided parameters.

        Args:
            search_text: Optional search text
            chunk_query: Optional ChunkQuery object

        Returns:
            Search type: 'text_only', 'vector_only', 'metadata_only', 'combined', or 'invalid'

        Raises:
            ValueError: If neither search_text nor chunk_query is provided
        """
        has_text = search_text is not None and search_text.strip()
        has_vectors = chunk_query and chunk_query.embedding is not None
        has_metadata = chunk_query and self._has_metadata_criteria(chunk_query)
        
        if not has_text and not has_vectors and not has_metadata:
            raise ValueError("At least one of search_text or chunk_query must be provided")
        
        if has_text and not has_vectors and not has_metadata:
            return 'text_only'
        elif has_vectors and not has_text and not has_metadata:
            return 'vector_only'
        elif has_metadata and not has_text and not has_vectors:
            return 'metadata_only'
        elif has_text and has_vectors and not has_metadata:
            return 'text_vector_only'
        elif has_text and has_metadata and not has_vectors:
            return 'text_metadata_only'
        elif has_vectors and has_metadata and not has_text:
            return 'vector_metadata_only'
        else:  # has_text and has_vectors and has_metadata
            return 'combined'

    # Utility Methods
    async def get_id_to_idx_mapping(self) -> Dict[str, int]:
        """
        Get UUID to index mapping from Redis.
        
        Returns:
            Dictionary mapping UUIDs to their corresponding indices
            
        Raises:
            Exception: If mapping retrieval fails
        """
        try:
            return await get_id_to_idx_mapping(self.redis)
        except Exception as e:
            logger.error(f"Failed to get ID to index mapping: {e}")
            raise

    async def ping(self) -> bool:
        """
        Check Redis connection health.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            return await self.redis.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    def safe_json_parse(self, json_str: str) -> Any:
        """
        Safely parse JSON string, returning the original string if parsing fails.

        Args:
            json_str: JSON string to parse

        Returns:
            Parsed JSON object or original string if parsing fails
        """
        if not json_str:
            return json_str
        
        try:
            import json
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError, ValueError):
            return json_str

    async def get_search_stats(self) -> Dict[str, Any]:
        """
        Get search service statistics.

        Returns:
            Dictionary with search service statistics
        """
        try:
            # Get total number of records
            all_keys = await self.redis.keys("vector:*")
            total_records = len(all_keys)
            
            # Get deleted records count
            deleted_count = 0
            if total_records > 0:
                # Sample some records to estimate deleted count
                sample_size = min(100, total_records)
                sample_keys = all_keys[:sample_size]
                sample_uuids = [key.decode('utf-8').replace('vector:', '') if isinstance(key, bytes) else key.replace('vector:', '') 
                               for key in sample_keys]
                
                sample_metadata = await self._get_metadata_for_uuids(sample_uuids, include_vectors=False)
                deleted_count = sum(1 for meta in sample_metadata if meta and meta.get('is_deleted', False))
                
                # Estimate total deleted
                if sample_size > 0:
                    deleted_count = int((deleted_count / sample_size) * total_records)
            
            # Get FAISS index info
            faiss_info = {}
            try:
                if hasattr(self.faiss_service, 'get_index_info'):
                    faiss_info = await self.faiss_service.get_index_info()
            except Exception as e:
                logger.warning(f"Failed to get FAISS info: {e}")
            
            return {
                "total_records": total_records,
                "deleted_records": deleted_count,
                "active_records": total_records - deleted_count,
                "faiss_info": faiss_info,
                "vector_size": self.vector_size,
                "has_embedding_service": self.embedding_service is not None,
                "has_crud_service": self.crud_service is not None,
                "filter_executor_available": self.filter_executor is not None
            }
            
        except Exception as e:
            logger.error(f"Failed to get search stats: {e}")
            return {"error": str(e)}



    # Field Index Helper Methods
    def _extract_simple_field_filters(self, chunk_query: ChunkQuery) -> Dict[str, Any]:
        """
        Extract simple field filters that can use field indexes.
        
        Args:
            chunk_query: ChunkQuery with filtering criteria
            
        Returns:
            Dictionary of simple field filters
        """
        if not chunk_query:
            return {}
        
        try:
            simple_filters = {}
            
            # Check if ChunkQuery has metadata field
            if hasattr(chunk_query, 'metadata') and chunk_query.metadata:
                metadata_dict = chunk_query.metadata
                logger.info(f"Found metadata in ChunkQuery: {metadata_dict}")
                if isinstance(metadata_dict, dict):
                    # Extract simple field filters from metadata
                    simple_field_types = {
                        'uuid', 'type', 'language', 'status', 'category', 'title', 
                        'source_id', 'source_path', 'task_id', 'subtask_id', 'unit_id', 'block_id',
                        'is_code_chunk', 'year', 'is_public', 'is_deleted', 'project', 'summary', 
                        'source', 'chunking_version', 'sha256', 'created_at', 'ordinal', 'start', 
                        'end', 'block_index', 'source_lines_start', 'source_lines_end', 'role', 
                        'block_type', 'used_in_generation', 'feedback_accepted', 'feedback_rejected', 
                        'feedback_modifications', 'quality_score', 'coverage', 'cohesion', 
                        'boundary_prev', 'boundary_next', 'tags_flat', 'link_related', 'link_parent'
                    }
                    
                    for field_name, field_value in metadata_dict.items():
                        logger.info(f"Processing field {field_name} = {field_value} (type: {type(field_value)})")
                        if (field_name in simple_field_types and 
                            field_value is not None and 
                            field_value != ""):
                            
                            # Handle simple equality filters
                            if isinstance(field_value, (str, int, bool)):
                                simple_filters[field_name] = str(field_value)
                                logger.info(f"Added simple filter: {field_name} = {field_value}")
                            elif isinstance(field_value, dict) and '$eq' in field_value:
                                simple_filters[field_name] = str(field_value['$eq'])
                                logger.info(f"Added $eq filter: {field_name} = {field_value['$eq']}")
                            elif isinstance(field_value, dict) and '$in' in field_value:
                                # Handle $in operator for list values
                                if isinstance(field_value['$in'], list):
                                    simple_filters[field_name] = field_value['$in']
                                    logger.info(f"Added $in filter: {field_name} = {field_value['$in']}")
                else:
                    logger.warning(f"Metadata is not a dict: {type(metadata_dict)}")
            else:
                logger.info("No metadata found in ChunkQuery")
            
            # Also check direct fields on ChunkQuery for backward compatibility
            query_dict = chunk_query.model_dump() if hasattr(chunk_query, 'model_dump') else chunk_query.__dict__
            simple_field_types = {
                'uuid', 'type', 'language', 'status', 'category', 'title', 
                'source_id', 'source_path', 'task_id', 'subtask_id', 'unit_id', 'block_id',
                'is_code_chunk', 'year', 'is_public', 'is_deleted', 'project', 'summary', 
                'source', 'chunking_version', 'sha256', 'created_at', 'ordinal', 'start', 
                'end', 'block_index', 'source_lines_start', 'source_lines_end', 'role', 
                'block_type', 'used_in_generation', 'feedback_accepted', 'feedback_rejected', 
                'feedback_modifications', 'quality_score', 'coverage', 'cohesion', 
                'boundary_prev', 'boundary_next', 'tags_flat', 'link_related', 'link_parent'
            }
            
            for field_name, field_value in query_dict.items():
                if (field_name in simple_field_types and 
                    field_value is not None and 
                    field_value != "" and
                    field_name not in simple_filters):  # Don't override metadata filters
                    
                    # Handle simple equality filters
                    if isinstance(field_value, (str, int, bool)):
                        simple_filters[field_name] = str(field_value)
                    elif isinstance(field_value, dict) and '$eq' in field_value:
                        simple_filters[field_name] = str(field_value['$eq'])
            
            # Check if ChunkQuery has filter_expr (AST-based filtering)
            if hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr:
                logger.info(f"Found filter_expr: {chunk_query.filter_expr}")
                ast_filters = self._extract_simple_filters_from_ast(chunk_query.filter_expr)
                logger.info(f"Extracted AST filters: {ast_filters}")
                simple_filters.update(ast_filters)
                logger.info(f"Updated simple_filters: {simple_filters}")
            else:
                logger.info("No filter_expr found in ChunkQuery")
            
            logger.debug(f"Extracted simple field filters: {simple_filters}")
            
            # Log detailed information about what was found
            if hasattr(chunk_query, 'metadata') and chunk_query.metadata:
                logger.debug(f"ChunkQuery metadata: {chunk_query.metadata}")
            else:
                logger.debug("ChunkQuery has no metadata field")
            
            if hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr:
                logger.debug(f"ChunkQuery has filter_expr: {chunk_query.filter_expr}")
            else:
                logger.debug("ChunkQuery has no filter_expr field")
            
            query_dict = chunk_query.model_dump() if hasattr(chunk_query, 'model_dump') else chunk_query.__dict__
            logger.debug(f"ChunkQuery fields: {list(query_dict.keys())}")
            
            return simple_filters
            
        except Exception as e:
            logger.error(f"Failed to extract simple field filters: {e}")
            return {}

    def _extract_simple_filters_from_ast(self, ast_filter: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract simple field filters from AST expression.
        
        Args:
            ast_filter: AST filter expression
            
        Returns:
            Dictionary of simple field filters
        """
        simple_filters = {}
        
        def extract_from_node(node):
            """Recursively extract simple filters from AST node."""
            if not isinstance(node, dict):
                return
            
            # Check if this is a field condition
            if node.get("node_type") == "field_condition" or "field" in node:
                field = node.get("field")
                operator = node.get("operator")
                value = node.get("value")
                
                # Handle simple equality
                if operator == "=" and field and value:
                    if isinstance(value, dict) and "value" in value:
                        simple_filters[field] = str(value["value"])
                    elif isinstance(value, (str, int, bool)):
                        simple_filters[field] = str(value)
            
            # Recursively check children
            for key, child in node.items():
                if isinstance(child, dict):
                    extract_from_node(child)
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, dict):
                            extract_from_node(item)
        
        extract_from_node(ast_filter)
        return simple_filters

    def _has_complex_filters(self, chunk_query: ChunkQuery) -> bool:
        """
        Check if ChunkQuery has complex filters that require full metadata evaluation.
        
        Args:
            chunk_query: ChunkQuery to check
            
        Returns:
            True if complex filters are present
        """
        logger.info(f"_has_complex_filters called with chunk_query: {chunk_query}")
        if not chunk_query:
            logger.info("No chunk_query provided")
            return False
        
        try:
            query_dict = chunk_query.model_dump() if hasattr(chunk_query, 'model_dump') else chunk_query.__dict__
            
            # Check for complex filter types
            for field_name, field_value in query_dict.items():
                # Skip non-filter fields
                if field_name in ['search_fields', 'bm25_k1', 'bm25_b', 'bm25_weight', 'semantic_weight', 'min_score', 'max_results', 'hybrid_search', 'created_at']:
                    continue
                
                if isinstance(field_value, dict):
                    # Complex operators like $in, $gte, $lte, etc.
                    if any(op in field_value for op in ['$in', '$gte', '$lte', '$gt', '$lt', '$ne']):
                        logger.info(f"Found complex operator in field {field_name}: {field_value}")
                        return True
                elif isinstance(field_value, (list, tuple)):
                    # List-based filters
                    logger.info(f"Found list-based filter in field {field_name}: {field_value}")
                    return True
            
            # Check for metadata field with complex structure
            if 'metadata' in query_dict and isinstance(query_dict['metadata'], dict):
                return True
            
            # Check if ChunkQuery has filter_expr (AST-based filtering)
            if hasattr(chunk_query, 'filter_expr') and chunk_query.filter_expr:
                # Check if AST contains complex operators
                ast_filter = chunk_query.filter_expr
                if self._is_complex_ast_filter(ast_filter):
                    logger.info(f"AST filter is complex: {ast_filter}")
                    return True
                else:
                    logger.info(f"AST filter is simple: {ast_filter}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check for complex filters: {e}")
            return True  # Assume complex if error

    def _is_complex_ast_filter(self, ast_filter: Dict[str, Any]) -> bool:
        """
        Check if AST filter contains complex operators.
        
        Args:
            ast_filter: AST filter expression
            
        Returns:
            True if filter contains complex operators, False if simple equality only
        """
        def check_node(node):
            """Recursively check AST node for complex operators."""
            if not isinstance(node, dict):
                return False
            
            # Check for logical operators (AND, OR, NOT)
            if node.get("node_type") in ["logical_operator", "and", "or", "not"]:
                return True
            
            # Check for field condition with complex operators
            if node.get("node_type") == "field_condition" or "field" in node:
                operator = node.get("operator")
                # Simple equality is not complex
                if operator == "=":
                    return False
                # Other operators are complex
                if operator in ["!=", ">", "<", ">=", "<=", "in", "not_in", "contains", "starts_with", "ends_with"]:
                    return True
            
            # Recursively check children
            for key, child in node.items():
                if isinstance(child, dict):
                    if check_node(child):
                        return True
                elif isinstance(child, list):
                    for item in child:
                        if isinstance(item, dict) and check_node(item):
                            return True
            
            return False
        
        return check_node(ast_filter) 

    async def find_chunks_by_query(
        self,
        chunk_query: ChunkQuery,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find chunks matching ChunkQuery criteria.
        
        Args:
            chunk_query: ChunkQuery object with filtering criteria
            include_deleted: Whether to include deleted records
            
        Returns:
            List of chunk dictionaries matching the query
        """
        try:
            # Use the main search method with no limit to get all matching chunks
            results = await self.search(
                chunk_query=chunk_query,
                limit=None,  # No limit to get all results
                offset=None,
                include_vectors=False,  # Don't include vectors for efficiency
                include_deleted=include_deleted
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error finding chunks by query: {e}")
            raise

    async def count_chunks_by_query(
        self,
        chunk_query: ChunkQuery,
        include_deleted: bool = False
    ) -> int:
        """
        Count chunks matching ChunkQuery criteria.
        
        Args:
            chunk_query: ChunkQuery object with filtering criteria
            include_deleted: Whether to include deleted records
            
        Returns:
            Number of chunks matching the query
        """
        try:
            # Find chunks and return count
            chunks = await self.find_chunks_by_query(chunk_query, include_deleted)
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Error counting chunks by query: {e}")
            raise

    async def mark_chunk_as_deleted(self, uuid: str) -> None:
        """
        Mark a chunk as deleted (soft delete).
        
        Args:
            uuid: UUID of the chunk to mark as deleted
        """
        try:
            if self.crud_service:
                # Use CRUD service if available
                await self.crud_service.mark_chunk_as_deleted(uuid)
            else:
                # Direct Redis operation
                chunk_key = f"vector:{uuid}"
                await self.redis.hset(chunk_key, "is_deleted", "true")
                await self.redis.hset(chunk_key, "deleted_at", str(int(time.time())))
                
        except Exception as e:
            logger.error(f"Error marking chunk {uuid} as deleted: {e}")
            raise

    async def delete_chunk_metadata(self, uuid: str) -> None:
        """
        Permanently delete chunk metadata from Redis.
        
        Args:
            uuid: UUID of the chunk to delete
        """
        try:
            if self.crud_service:
                # Use CRUD service if available
                await self.crud_service.delete_chunk(uuid)
            else:
                # Direct Redis operation
                chunk_key = f"vector:{uuid}"
                await self.redis.delete(chunk_key)
                
        except Exception as e:
            logger.error(f"Error deleting chunk metadata {uuid}: {e}")
            raise
    
    def _optimized_pagination(
        self,
        uuids: List[str],
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[str]:
        """
        Оптимизированная пагинация результатов.
        
        Args:
            uuids: Список UUID для пагинации
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список UUID с примененной пагинацией
        """
        # Применение смещения
        if offset:
            uuids = uuids[offset:]
        
        # Применение лимита
        if limit:
            uuids = uuids[:limit]
        
        return uuids
    
    async def _cached_search_results(
        self,
        chunk_query: ChunkQuery,
        cache_ttl: int = 300
    ) -> Dict[str, Set[str]]:
        """
        Кэширование результатов поиска.
        
        Args:
            chunk_query: Запрос для поиска
            cache_ttl: Время жизни кэша в секундах
            
        Returns:
            Кэшированные результаты поиска
        """
        try:
            # Создание ключа кэша на основе параметров запроса
            cache_key = f"search_cache:{hash(str(chunk_query.__dict__))}"
            
            # Проверка кэша
            cached_results = await self.redis.get(cache_key)
            if cached_results:
                logger.info(f"Cache hit for search query: {cache_key}")
                return json.loads(cached_results)
            
            # Выполнение поиска
            logger.info(f"Cache miss for search query: {cache_key}")
            results = await self._perform_search(chunk_query)
            
            # Сохранение в кэш
            await self.redis.setex(cache_key, cache_ttl, json.dumps(results))
            
            return results
            
        except Exception as e:
            logger.warning(f"Cache operation failed: {e}")
            # Возвращаем результаты без кэширования при ошибке
            return await self._perform_search(chunk_query)
    
    async def _perform_search(self, chunk_query: ChunkQuery) -> Dict[str, Set[str]]:
        """
        Выполнение поиска без кэширования.
        
        Args:
            chunk_query: Запрос для поиска
            
        Returns:
            Результаты поиска по типам
        """
        results = {}
        
        # BM25 поиск
        if (chunk_query.search_query or chunk_query.text) and getattr(chunk_query, 'bm25_k1', 0) > 0:
            search_text = chunk_query.search_query or chunk_query.text
            bm25_results = await self._bm25_search(search_text, limit=None, include_deleted=False)
            results['bm25'] = {result['uuid'] for result in bm25_results}
        
        # Семантический поиск
        if chunk_query.embedding and getattr(chunk_query, 'semantic_weight', 0) > 0:
            semantic_results = await self._vector_search(chunk_query.embedding, limit=None, include_deleted=False)
            results['semantic'] = set(semantic_results)
        
        # Фильтрация метаданных
        metadata_filters = {}
        if chunk_query.metadata:
            metadata_filters.update(chunk_query.metadata)
        if chunk_query.category:
            metadata_filters['category'] = chunk_query.category
        if chunk_query.tags:
            metadata_filters['tags'] = chunk_query.tags
        if chunk_query.type:
            metadata_filters['type'] = chunk_query.type
        if chunk_query.language:
            metadata_filters['language'] = chunk_query.language
        if chunk_query.is_deleted is not None:
            metadata_filters['is_deleted'] = chunk_query.is_deleted
        
        if metadata_filters:
            metadata_results = await self._metadata_filter_search(chunk_query, limit=None, include_deleted=False)
            results['metadata'] = {result['uuid'] for result in metadata_results}
        
        return results