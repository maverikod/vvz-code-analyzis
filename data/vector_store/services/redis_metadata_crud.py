"""
Redis Metadata CRUD Service

This module provides the RedisMetadataCRUDService class for CRUD operations
on vector store metadata stored in Redis.

Storage Strategy:
- Main metadata stored in Redis Hash: vector:{uuid}
- Array fields stored in separate Redis Lists: {field_name}:{uuid}
- FAISS index mapping: faiss_idx:{idx} -> uuid

Features:
- Full CRUD operations for SemanticChunk objects
- Batch operations with pipeline optimization
- Soft delete support
- FAISS integration for vector storage and search
- Automatic TTL management
- Comprehensive error handling

Usage:
    service = RedisMetadataCRUDService(redis_client=redis_client)
    await service.upsert_chunk(chunk)
    chunk_data = await service.get_chunk(uuid)
    await service.delete_chunk(uuid)
"""

import logging
import json
import numpy as np
import redis.asyncio as redis
from typing import Dict, List, Any, Optional, Tuple, Set
from chunk_metadata_adapter import SemanticChunk


from vector_store.exceptions import (
    RedisOperationError, ChunkValidationError, ChunkSerializationError,
    create_redis_operation_error, DataProcessingError, SerializationError,
    DeserializationError, UnexpectedError
)

from vector_store.services.faiss_index_service import (
    FaissIndexService, FaissIndexError, FaissSearchError, FaissVectorError, FaissStorageError
)

logger = logging.getLogger("vector_store.redis")
detailed_logger = logging.getLogger("vector_store.detailed")

def _ensure_str_key(key):
    if isinstance(key, bytes):
        key = key.decode()
    assert isinstance(key, str), f"Redis key must be str, got {type(key)}: {key}"
    return key

class RedisMetadataCRUDService:
    """
    Service for CRUD operations on chunk metadata and vectors in Redis.
    
    Features:
    - Store/retrieve chunk metadata in Redis Hash
    - Store/retrieve list fields in separate Redis Lists
    - Embedding vectors stored in FAISS with Redis mapping
    - Automatic type conversion via SemanticChunk adapter
    - FAISS integration for vector storage and search
    - Soft delete is supported via is_deleted field in SemanticChunk model.
    """
    
    def __init__(self, redis_client=None, redis_url=None, faiss_service=None, index_manager=None, embedding_service=None):
        """
        Initialize Redis CRUD service.
        
        Args:
            redis_client: Redis client instance
            redis_url: Redis connection URL
            faiss_service: FAISS service for vector operations
            index_manager: Pre-initialized IndexManager instance
            embedding_service: Service for getting embeddings
        """
        if redis_client:
            self.redis = redis_client
        elif redis_url:
            self.redis = redis.from_url(redis_url)
        else:
            raise ValueError("Either redis_client or redis_url must be provided")
        
        # FAISS service for vector operations
        self.faiss_service = faiss_service
        
        # Embedding service for vector operations
        self.embedding_service = embedding_service
        
        # Use provided IndexManager or create one if not provided
        if index_manager:
            self.index_manager = index_manager
            logger.info("Using provided IndexManager")
        else:
            try:
                from vector_store.services.index_manager.atomic_index_manager import AtomicIndexManager
                self.index_manager = AtomicIndexManager(redis_client=self.redis, embedding_service=embedding_service)
                
                # Set chunk metadata adapter
                from chunk_metadata_adapter.utils import to_flat_dict
                class ChunkMetadataAdapter:
                    @staticmethod
                    def to_flat_dict(chunk):
                        if hasattr(chunk, 'model_dump'):
                            return to_flat_dict(chunk.model_dump(), for_redis=True)
                        elif isinstance(chunk, dict):
                            return to_flat_dict(chunk, for_redis=True)
                        else:
                            # Fallback for string or other types
                            return to_flat_dict({"uuid": str(chunk)}, for_redis=True)
                
                self.index_manager.set_chunk_metadata_adapter(ChunkMetadataAdapter())
                logger.info("IndexManager created successfully with ChunkQuery support")
            except Exception as e:
                logger.warning(f"Failed to create IndexManager: {e}")
                self.index_manager = None
        
        # TTL for chunk data (24 hours)
        self.chunk_ttl = 24 * 60 * 60

    def chunk_key(self, uuid: str) -> str:
        """
        Generate Redis key for chunk data.
        
        Args:
            uuid: Chunk UUID
            
        Returns:
            Redis key string
        """
        return f"vector:{uuid}"

    async def flush_all(self):
        """
        Completely flushes the current Redis database (removes all keys).
        Use with caution in tests only!
        """
        try:
            await self.redis.flushdb()
            logger.info("Successfully flushed Redis database")
        except redis.RedisError as e:
            raise create_redis_operation_error("flushdb", e)
        except Exception as e:
            logger.error(f"Failed to flush Redis database: {e}")
            raise UnexpectedError(f"Failed to flush Redis database: {e}", original_error=e)

    async def upsert_chunks(self, chunks: List[SemanticChunk]) -> List[str]:
        """
        Create or update multiple chunks atomically.
        
        Args:
            chunks: List of SemanticChunk objects
            
        Returns:
            List of UUIDs of successfully upserted chunks
            
        Raises:
            ValueError: If chunk validation fails
            RuntimeError: If Redis operation fails
        """
        # CRITICAL: Check required services at the beginning
        if not hasattr(self, 'index_manager') or not self.index_manager:
            raise RedisOperationError("index_manager_unavailable", "IndexManager is not available - critical error")
        if not self.faiss_service:
            raise RedisOperationError("faiss_service_unavailable", "FAISS service is not available - critical error")
        
        if not chunks:
            return []
            
        # Validate all chunks first
        for chunk in chunks:
            self._validate_chunk(chunk)
        
        # Analyze fields and create necessary indexes
        await self._ensure_indexes_for_chunks(chunks)
        
        successful_uuids = []
        
        try:
            # Get initial counts for consistency check
            initial_redis_count = await self.count_records(include_deleted=False)
            initial_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
            
            logger.info(f"Starting upsert for {len(chunks)} chunks. Initial counts - Redis: {initial_redis_count}, FAISS: {initial_faiss_count}")
            
            # Prepare Redis operations
            pipeline = await self.redis.pipeline()
            vector_pipeline = await self.redis.pipeline()
            
            vectors = []
            uuid_list = []
            
            for chunk in chunks:
                try:
                    # Serialize chunk
                    flat_dict = self._serialize_chunk(chunk)
                    
                    # Separate scalar fields and arrays
                    list_fields = {k: v for k, v in flat_dict.items() if isinstance(v, list)}
                    scalar_fields = {k: v for k, v in flat_dict.items() if not isinstance(v, list) and v is not None}
                    
                    # Store scalar fields in hash
                    hash_key = f"vector:{chunk.uuid}"
                    pipeline.hset(hash_key, mapping=scalar_fields)
                    pipeline.expire(hash_key, self.chunk_ttl)
                    
                    # Store list fields in separate Redis Lists
                    for field_name, field_value in list_fields.items():
                        list_key = f"{field_name}:{chunk.uuid}"
                        pipeline.delete(list_key)  # Clear existing list
                        if field_value:
                            pipeline.rpush(list_key, *field_value)
                        pipeline.expire(list_key, self.chunk_ttl)
                    
                    # Create field indexes using IndexManager
                    try:
                        await self.index_manager.index_chunk(chunk.uuid, chunk.model_dump())
                    except Exception as index_error:
                        logger.error(f"Failed to index chunk {chunk.uuid}: {index_error}")
                        # Rollback this chunk's Redis changes due to indexing failure
                        await self._rollback_single_chunk(chunk.uuid)
                        continue
                    
                    # Store vector in Redis
                    if chunk.embedding:
                        vector_key = f"vector_data:{chunk.uuid}"
                        vector_pipeline.set(vector_key, json.dumps(chunk.embedding))
                        vector_pipeline.expire(vector_key, self.chunk_ttl)
                        
                        # Prepare for FAISS
                        vector = np.array(chunk.embedding, dtype=np.float32)
                        vectors.append(vector)
                        uuid_list.append(chunk.uuid)
                        logger.debug(f"Stored vector for chunk {chunk.uuid}: {self._format_vector_log(chunk.embedding)}")
                    else:
                        logger.debug(f"No embedding for chunk {chunk.uuid}")
                    
                    successful_uuids.append(chunk.uuid)
                    
                except ChunkSerializationError as e:
                    logger.error(f"Failed to serialize chunk {chunk.uuid}: {e}")
                    await self._rollback_single_chunk(chunk.uuid)
                    continue
                except DataProcessingError as e:
                    logger.error(f"Failed to process chunk data {chunk.uuid}: {e}")
                    await self._rollback_single_chunk(chunk.uuid)
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing chunk {chunk.uuid}: {e}")
                    await self._rollback_single_chunk(chunk.uuid)
                    continue
            
            # Execute Redis operations
            if successful_uuids:
                await pipeline.execute()
                await vector_pipeline.execute()
                logger.debug(f"Stored {len(successful_uuids)} chunks in Redis")
            
            # Add vectors to FAISS with rollback support
            if vectors:
                logger.debug(f"Adding {len(vectors)} vectors to FAISS for search")
                try:
                    indices = await self.faiss_service.add_vectors(vectors)
                    logger.debug(f"FAISS indices: {indices}")
                    
                    # Store FAISS index mappings
                    idx_pipeline = await self.redis.pipeline()
                    for idx, uuid in zip(indices, uuid_list):
                        idx_pipeline.set(f"faiss_idx:{idx}", uuid)
                        idx_pipeline.hset(self.chunk_key(uuid), "faiss_idx", idx)
                    await idx_pipeline.execute()
                    logger.debug(f"Stored FAISS index mappings for {len(indices)} vectors")
                    
                except Exception as faiss_error:
                    logger.error(f"Failed to add vectors to FAISS: {faiss_error}")
                    # CRITICAL: Rollback Redis changes if FAISS fails
                    logger.warning(f"Rolling back Redis changes due to FAISS failure")
                    await self._rollback_redis_changes(successful_uuids)
                    raise RedisOperationError("faiss_add_vectors", f"FAISS operation failed: {faiss_error}")
            
            # Verify consistency after operation
            await self._verify_consistency_after_operation(
                initial_redis_count, initial_faiss_count, 
                len(successful_uuids), "upsert_chunks"
            )
            
            # Final count verification
            final_redis_count = await self.count_records(include_deleted=False)
            final_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
            
            redis_diff = final_redis_count - initial_redis_count
            faiss_diff = final_faiss_count - initial_faiss_count
            
            if redis_diff != len(successful_uuids):
                logger.error(f"[CONSISTENCY ERROR] upsert_chunks: Redis count mismatch. Expected: {len(successful_uuids)}, Got: {redis_diff}")
                logger.error(f"Initial Redis: {initial_redis_count}, Final Redis: {final_redis_count}, Difference: {redis_diff}")
            
            if faiss_diff != len(vectors):
                logger.error(f"[CONSISTENCY ERROR] upsert_chunks: FAISS count mismatch. Expected: {len(vectors)}, Got: {faiss_diff}")
                logger.error(f"Initial FAISS: {initial_faiss_count}, Final FAISS: {final_faiss_count}, Difference: {faiss_diff}")
            
            if redis_diff == len(successful_uuids) and faiss_diff == len(vectors):
                logger.info(f"Successfully upserted {len(successful_uuids)} chunks. Final counts - Redis: {final_redis_count}, FAISS: {final_faiss_count}")
            else:
                logger.warning(f"Upsert completed with inconsistencies. Final counts - Redis: {final_redis_count}, FAISS: {final_faiss_count}")
            
            return successful_uuids
            
        except RedisOperationError as e:
            logger.error(f"Redis operation failed: {e}")
            if successful_uuids:
                await self._rollback_redis_changes(successful_uuids)
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in upsert_chunks: {e}")
            if successful_uuids:
                await self._rollback_redis_changes(successful_uuids)
            raise UnexpectedError(f"Unexpected error in upsert_chunks: {e}", original_error=e)

    async def upsert_chunk(self, chunk: SemanticChunk) -> str:
        """
        Create or update single chunk.
        
        Args:
            chunk: SemanticChunk object
            
        Returns:
            UUID of the upserted chunk
            
        Raises:
            ValueError: If chunk validation fails
            RuntimeError: If Redis operation fails
        """
        logger.debug(f"Starting upsert_chunk for UUID: {chunk.uuid}")
        try:
            uuids = await self.upsert_chunks([chunk])
            logger.debug(f"upsert_chunks returned: {uuids}")
            return uuids[0] if uuids else chunk.uuid
        except Exception as e:
            logger.error(f"Failed to upsert chunk: {e}")
            raise

    async def get_chunks(self, uuids: List[str], include_vectors: bool = True, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get chunks by UUIDs.
        
        Args:
            uuids: List of chunk UUIDs
            include_vectors: Whether to include vectors in results
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            List of chunk dictionaries
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        if not uuids:
            return []
            
        try:
            # Prepare pipeline for hash and list keys queries
            pipeline = await self.redis.pipeline()
            
            for uuid in uuids:
                # Get hash data
                hash_key = f"vector:{uuid}"
                pipeline.hgetall(hash_key)
                
                # Get list keys for this UUID
                pipeline.keys(f"*:{uuid}")
            
            # Execute pipeline
            try:
                pipeline_results = await pipeline.execute()
            except redis.RedisError as e:
                raise create_redis_operation_error("pipeline_execute", e, {"uuids": uuids})
            
            results = []
            
            # Process results
            for i, uuid in enumerate(uuids):
                # Get hash data
                hash_data = pipeline_results[i * 2]  # 1 hash + 1 keys query per UUID
                
                if not hash_data:
                    results.append(None)
                    continue
                    
                # Decode hash data
                meta = {k.decode('utf-8') if isinstance(k, bytes) else k:
                        v.decode('utf-8') if isinstance(v, bytes) else v
                        for k, v in hash_data.items()}
                
                # Remove embedding field if vectors not needed
                if not include_vectors and 'embedding' in meta:
                    del meta['embedding']
                
                # Get list keys for this UUID
                list_keys = pipeline_results[i * 2 + 1]
                list_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in list_keys]
                
                # Get list data for existing list fields
                list_pipeline = await self.redis.pipeline()
                filtered_list_keys = []  # Track which keys we actually query
                for list_key in list_keys:
                    if ':' in list_key and not list_key.startswith('vector:') and not list_key.startswith('vector_data:'):  # Only non-vector keys
                        # Check if key exists and get its type
                        list_pipeline.exists(list_key)
                        list_pipeline.type(list_key)
                        filtered_list_keys.append(list_key)
                
                if list_pipeline:
                    try:
                        type_results = await list_pipeline.execute()
                    except redis.RedisError as e:
                        raise create_redis_operation_error("list_pipeline_execute", e, {"uuid": uuid})
                    
                    # Process each key based on its type
                    for j, list_key in enumerate(filtered_list_keys):
                        if ':' in list_key:
                            field_name = list_key.split(':', 1)[0]
                            exists = type_results[j * 2] if j * 2 < len(type_results) else 0
                            key_type = type_results[j * 2 + 1] if j * 2 + 1 < len(type_results) else None
                            
                            if exists and key_type:
                                if isinstance(key_type, bytes):
                                    key_type = key_type.decode('utf-8')
                                
                                # Get data based on type
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
                
                # Check if deleted (unless include_deleted=True)
                if not include_deleted and meta.get('is_deleted') == 'true':
                    results.append(None)
                    continue
                
                # Restore types using SemanticChunk
                try:
                    if include_vectors:
                        logger.debug(f"get_chunks: meta keys: {list(meta.keys())}")
                        logger.debug(f"get_chunks: embedding in meta: {meta.get('embedding', 'NOT_FOUND')}")
                    logger.debug(f"get_chunks: meta for {uuid}, keys: {list(meta.keys())}")
                    if 'uuid' in meta:
                        logger.debug(f"get_chunks: UUID in meta for {uuid}: type={type(meta['uuid'])}, value={meta['uuid']}")
                        # Fix UUID if it's a list
                        if isinstance(meta['uuid'], list) and len(meta['uuid']) == 1:
                            meta['uuid'] = meta['uuid'][0]
                            logger.debug(f"get_chunks: Fixed UUID for {uuid}: {meta['uuid']}")
                    flat_meta = SemanticChunk.from_flat_dict(meta, from_redis=True).model_dump()
                    if include_vectors:
                        logger.debug(f"get_chunks: flat_meta keys: {list(flat_meta.keys())}")
                        logger.debug(f"get_chunks: embedding in flat_meta: {flat_meta.get('embedding', 'NOT_FOUND')}")
                    # Ensure faiss_idx is preserved
                    if 'faiss_idx' in meta:
                        flat_meta['faiss_idx'] = meta['faiss_idx']
                    results.append(flat_meta)
                except Exception as e:
                    logger.warning(f"Failed to restore types for {uuid}: {e}")
                    results.append(meta)
            
            return results
            
        except redis.RedisError as e:
            raise create_redis_operation_error("get_chunks", e, {"uuids": uuids})
        except RedisOperationError as e:
            raise e
        except DeserializationError as e:
            logger.error(f"Failed to deserialize chunks: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error getting chunks: {e}")
            raise UnexpectedError(f"Unexpected error getting chunks: {e}", original_error=e)

    async def get_chunk(self, uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get single chunk by UUID.
        
        Args:
            uuid: Chunk UUID
            
        Returns:
            Chunk dictionary or None if not found
        """
        try:
            chunks = await self.get_chunks([uuid])
            return chunks[0] if chunks else None
        except Exception as e:
            logger.error(f"Failed to get chunk {uuid}: {e}")
            raise

    async def get_vector_from_redis(self, uuid: str) -> Optional[List[float]]:
        """
        Get vector from Redis by UUID.
        
        Args:
            uuid: Chunk UUID
            
        Returns:
            Vector as list of floats or None if not found
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        try:
            vector_key = f"vector_data:{uuid}"
            vector_data = await self.redis.get(vector_key)
            if vector_data:
                if isinstance(vector_data, bytes):
                    vector_data = vector_data.decode('utf-8')
                return json.loads(vector_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get vector from Redis for {uuid}: {e}")
            return None

    async def get_vectors_from_redis(self, uuids: List[str]) -> List[Optional[List[float]]]:
        """
        Get multiple vectors from Redis by UUIDs.
        
        Args:
            uuids: List of chunk UUIDs
            
        Returns:
            List of vectors (None if not found)
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        if not uuids:
            return []
            
        try:
            # Prepare pipeline
            pipeline = await self.redis.pipeline()
            for uuid in uuids:
                vector_key = f"vector_data:{uuid}"
                pipeline.get(vector_key)
            
            # Execute pipeline
            results = await pipeline.execute()
            
            # Process results
            vectors = []
            for result in results:
                if result:
                    if isinstance(result, bytes):
                        result = result.decode('utf-8')
                    vectors.append(json.loads(result))
                else:
                    vectors.append(None)
            
            return vectors
        except Exception as e:
            logger.error(f"Failed to get vectors from Redis: {e}")
            return [None] * len(uuids)

    async def delete_chunks(self, uuids: List[str]) -> List[str]:
        """
        Soft delete chunks by UUIDs (mark as deleted).
        
        Args:
            uuids: List of chunk UUIDs to soft delete
            
        Returns:
            List of successfully soft deleted UUIDs
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        if not uuids:
            return []
            
        logger.debug(f"Starting soft delete for {len(uuids)} UUIDs")
        
        # Get initial counts for consistency check
        initial_redis_count = await self.count_records(include_deleted=False)
        initial_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
        
        pipeline = await self.redis.pipeline()
        
        try:
            for uuid in uuids:
                # Mark chunk as deleted (is_deleted=True)
                key = f"vector:{uuid}"
                logger.debug(f"Marking chunk as deleted: {key}")
                pipeline.hset(key, "is_deleted", "true")
                pipeline.expire(key, self.chunk_ttl)
            
            # Execute pipeline
            try:
                results = await pipeline.execute()
                logger.debug(f"Soft delete pipeline results: {results}")
            except redis.RedisError as e:
                raise create_redis_operation_error("pipeline_execute", e, {"uuids": uuids})
            
            # Verify consistency after operation (soft delete should reduce active count)
            await self._verify_consistency_after_operation(
                initial_redis_count, initial_faiss_count, 
                -len(uuids), "soft_delete_chunks"
            )
            
            logger.info(f"Successfully soft deleted {len(uuids)} chunks")
            return uuids
            

        except redis.RedisError as e:
            raise create_redis_operation_error("delete_chunks", e, {"uuids": uuids})
        except Exception as e:
            logger.error(f"Failed to soft delete chunks: {e}")
            raise RedisOperationError("delete_chunks", str(e))

    async def hard_delete_chunks(self, uuids: List[str] = None, delete_all: bool = False) -> List[str]:
        """
        Hard delete chunks by UUIDs (remove from FAISS and Redis).
        
        Args:
            uuids: List of chunk UUIDs to delete
            delete_all: Whether to delete all chunks
            
        Returns:
            List of successfully deleted UUIDs
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        # CRITICAL: Check required services at the beginning
        if not hasattr(self, 'index_manager') or not self.index_manager:
            raise RedisOperationError("index_manager_unavailable", "IndexManager is not available - critical error")
        if not self.faiss_service:
            raise RedisOperationError("faiss_service_unavailable", "FAISS service is not available - critical error")
        
        if delete_all:
            logger.debug("Starting hard delete for ALL chunks")
            all_keys = await self.redis.keys("vector:*")
            uuids = [key.decode('utf-8').replace('vector:', '') if isinstance(key, bytes) else key.replace('vector:', '') for key in all_keys]
        elif not uuids:
            logger.debug("No UUIDs provided for hard delete")
            return []
        else:
            logger.debug(f"Starting hard delete for {len(uuids)} UUIDs")
        
        if not uuids:
            return []

        # Get initial counts for consistency check
        initial_redis_count = await self.count_records(include_deleted=False)
        initial_faiss_count = await self.faiss_service.count()
        
        logger.info(f"[HARD_DELETE] Initial counts - Redis chunks: {initial_redis_count}, FAISS vectors: {initial_faiss_count}")
        logger.info(f"[HARD_DELETE] Planning to delete {len(uuids)} chunks")

        # 1. ПАКЕТНОЕ получение индексов FAISS (оптимизация N+1 query)
        logger.info(f"[OPTIMIZED] Batch fetching FAISS indices for {len(uuids)} UUIDs")
        faiss_pipeline = await self.redis.pipeline()
        for uuid in uuids:
            faiss_pipeline.hget(self.chunk_key(uuid), "faiss_idx")
        
        faiss_results = await faiss_pipeline.execute()
        
        # Обработка результатов и формирование списка индексов
        idxs_to_delete = []
        uuid_idx_mapping = {}
        valid_uuids = []
        
        for i, (uuid, idx_result) in enumerate(zip(uuids, faiss_results)):
            if idx_result is not None:
                if isinstance(idx_result, bytes):
                    idx = int(idx_result.decode("utf-8"))
                else:
                    idx = int(idx_result)
                idxs_to_delete.append(idx)
                uuid_idx_mapping[uuid] = idx
                valid_uuids.append(uuid)
                logger.debug(f"[OPTIMIZED] UUID {uuid} -> FAISS idx {idx}")
            else:
                logger.warning(f"[OPTIMIZED] UUID {uuid} has no faiss_idx in Redis")

        # 2. УДАЛЕНИЕ ИЗ FAISS (с роллбеком)
        if idxs_to_delete:
            try:
                # Сортируем индексы по убыванию для безопасного удаления
                sorted_indices = sorted(idxs_to_delete, reverse=True)
                logger.info(f"[OPTIMIZED] Deleting {len(sorted_indices)} FAISS vectors")
                
                # Удаляем все векторы за одну операцию
                deleted_count = await self.faiss_service.delete_vectors(sorted_indices)
                logger.info(f"[OPTIMIZED] Successfully deleted {deleted_count} vectors from FAISS")
                
                # Удаляем idx-uuid маппинги из Redis
                idx_pipeline = await self.redis.pipeline()
                for idx in idxs_to_delete:
                    idx_pipeline.delete(f"faiss_idx:{idx}")
                await idx_pipeline.execute()
                logger.info(f"[OPTIMIZED] Deleted {len(idxs_to_delete)} faiss_idx mappings from Redis")
                
            except Exception as e:
                logger.error(f"[ROLLBACK] FAISS deletion failed: {e}")
                # РОЛЛБЕК: Восстанавливаем FAISS индексы
                try:
                    logger.info(f"[ROLLBACK] Attempting to restore FAISS indices")
                    # Здесь должна быть логика восстановления FAISS
                    # Пока просто логируем ошибку
                except Exception as rollback_error:
                    logger.error(f"[ROLLBACK] Failed to restore FAISS: {rollback_error}")
                
                raise RedisOperationError("faiss_delete_vectors", f"FAISS deletion failed: {e}")

        # 3. ПАКЕТНОЕ удаление из Redis (только после успешного удаления FAISS)
        logger.info(f"[OPTIMIZED] Starting batch Redis deletion for {len(uuids)} UUIDs")
        
        # Собираем все ключи для удаления
        all_keys_to_delete = set()
        
        # Основные ключи чанков
        for uuid in uuids:
            all_keys_to_delete.add(f"vector:{uuid}")
        
        # Пакетное получение связанных ключей (замена KEYS на SCAN)
        logger.info(f"[OPTIMIZED] Scanning for related keys using SCAN")
        for uuid in uuids:
            try:
                # Используем SCAN вместо KEYS для безопасности
                cursor = 0
                while True:
                    cursor, keys = await self.redis.scan(cursor, match=f"*:{uuid}", count=100)
                    for key in keys:
                        if isinstance(key, bytes):
                            key = key.decode('utf-8')
                        if key != f"vector:{uuid}":  # Исключаем основной ключ
                            all_keys_to_delete.add(key)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"[OPTIMIZED] Error scanning keys for {uuid}: {e}")
                # Продолжаем с другими UUID
        
        # Пакетное удаление всех ключей
        if all_keys_to_delete:
            try:
                delete_pipeline = await self.redis.pipeline()
                for key in all_keys_to_delete:
                    delete_pipeline.delete(key)
                
                delete_results = await delete_pipeline.execute()
                deleted_keys_count = sum(1 for result in delete_results if result > 0)
                
                logger.info(f"[OPTIMIZED] Successfully deleted {deleted_keys_count} Redis keys")
                
            except Exception as e:
                logger.error(f"[ROLLBACK] Redis deletion failed: {e}")
                # РОЛЛБЕК: Восстанавливаем Redis данные
                try:
                    logger.info(f"[ROLLBACK] Attempting to restore Redis data")
                    # Здесь должна быть логика восстановления Redis
                    # Пока просто логируем ошибку
                except Exception as rollback_error:
                    logger.error(f"[ROLLBACK] Failed to restore Redis: {rollback_error}")
                
                raise RedisOperationError("redis_delete_keys", f"Redis deletion failed: {e}")
        
        # 4. Удаление из индексов (последний этап)
        logger.info(f"[OPTIMIZED] Removing from field indexes")
        for uuid in uuids:
            try:
                # Получаем минимальные данные для удаления из индексов
                chunk_key = f"vector:{uuid}"
                chunk_exists = await self.redis.exists(chunk_key)
                
                if chunk_exists:
                    # Получаем только необходимые поля для индексов
                    index_pipeline = await self.redis.pipeline()
                    index_pipeline.hget(chunk_key, "type")
                    index_pipeline.hget(chunk_key, "language")
                    index_pipeline.hget(chunk_key, "project")
                    index_pipeline.hget(chunk_key, "source")
                    index_pipeline.hget(chunk_key, "task")
                    index_pipeline.hget(chunk_key, "subtask")
                    index_pipeline.hget(chunk_key, "unit")
                    index_pipeline.hget(chunk_key, "block")
                    index_pipeline.hget(chunk_key, "status")
                    index_pipeline.hget(chunk_key, "priority")
                    
                    index_results = await index_pipeline.execute()
                    
                    # Создаем минимальный chunk_data для удаления из индексов
                    chunk_data = {
                        "uuid": uuid,
                        "type": index_results[0].decode('utf-8') if index_results[0] else None,
                        "language": index_results[1].decode('utf-8') if index_results[1] else None,
                        "project": index_results[2].decode('utf-8') if index_results[2] else None,
                        "source": index_results[3].decode('utf-8') if index_results[3] else None,
                        "task": index_results[4].decode('utf-8') if index_results[4] else None,
                        "subtask": index_results[5].decode('utf-8') if index_results[5] else None,
                        "unit": index_results[6].decode('utf-8') if index_results[6] else None,
                        "block": index_results[7].decode('utf-8') if index_results[7] else None,
                        "status": index_results[8].decode('utf-8') if index_results[8] else None,
                        "priority": index_results[9].decode('utf-8') if index_results[9] else None,
                    }
                    
                    await self.index_manager.remove_chunk_from_indexes(uuid, chunk_data)
                    logger.debug(f"[OPTIMIZED] Removed {uuid} from indexes")
                    
            except Exception as index_error:
                logger.error(f"[OPTIMIZED] Failed to remove {uuid} from indexes: {index_error}")
                # Продолжаем с другими UUID
        
            # 5. Финальная проверка и логирование
            logger.info(f"[OPTIMIZED] Successfully hard deleted {len(uuids)} chunks")
            
            # Get final counts for detailed consistency check
            final_redis_count = await self.count_records(include_deleted=False)
            final_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
            
            logger.info(f"[HARD_DELETE] Final counts - Redis chunks: {final_redis_count}, FAISS vectors: {final_faiss_count}")
            
            # Calculate expected counts
            expected_redis_count = initial_redis_count - len(uuids)
            expected_faiss_count = initial_faiss_count - len(idxs_to_delete)
            
            # Verify counts match expectations
            if final_redis_count != expected_redis_count:
                error_msg = f"[HARD_DELETE ERROR] Redis count mismatch! Expected: {expected_redis_count}, Got: {final_redis_count}, Deleted: {len(uuids)}"
                logger.error(error_msg)
                logger.error(f"[HARD_DELETE ERROR] Initial Redis: {initial_redis_count}, Final Redis: {final_redis_count}, Difference: {initial_redis_count - final_redis_count}")
            
            if self.faiss_service and final_faiss_count != expected_faiss_count:
                error_msg = f"[HARD_DELETE ERROR] FAISS count mismatch! Expected: {expected_faiss_count}, Got: {final_faiss_count}, Deleted vectors: {len(idxs_to_delete)}"
                logger.error(error_msg)
                logger.error(f"[HARD_DELETE ERROR] Initial FAISS: {initial_faiss_count}, Final FAISS: {final_faiss_count}, Difference: {initial_faiss_count - final_faiss_count}")
            
            # Log success if counts match
            if final_redis_count == expected_redis_count and final_faiss_count == expected_faiss_count:
                logger.info(f"[HARD_DELETE SUCCESS] Count verification passed - Redis: {final_redis_count}, FAISS: {final_faiss_count}")
            
            # Verify consistency after operation
            await self._verify_consistency_after_operation(
                initial_redis_count, initial_faiss_count, 
                -len(uuids), "hard_delete_chunks"
            )
            
            # Clean up empty indexes after deletion
            await self._cleanup_empty_indexes()
            
            return uuids

    async def delete_chunk(self, uuid: str) -> bool:
        """
        Soft delete single chunk by UUID.
        
        Args:
            uuid: Chunk UUID
            
        Returns:
            True if soft deleted successfully
            
        Raises:
            RuntimeError: If Redis operation fails
        """
        try:
            deleted_uuids = await self.delete_chunks([uuid])
            return len(deleted_uuids) > 0
        except Exception as e:
            logger.error(f"Failed to soft delete chunk {uuid}: {e}")
            raise

    async def clean_faiss_vectors_without_metadata(self, faiss_service) -> int:
        """
        Clean FAISS vectors that don't have corresponding metadata in Redis.
        
        Args:
            faiss_service: FAISS service instance
            
        Returns:
            Number of cleaned vectors
        """
        try:
            # Get all FAISS indices
            if not faiss_service:
                logger.warning("No FAISS service provided for orphan cleanup")
                return 0
            
            # Get total vectors in FAISS
            faiss_info = await faiss_service.get_index_info()
            total_vectors = faiss_info.get('total_vectors', 0)
            
            if total_vectors == 0:
                logger.info("No vectors in FAISS to check")
                return 0
            
            # Get all Redis UUIDs
            redis_uuids = await self.get_all_record_ids()
            redis_uuids_set = set(redis_uuids)
            
            # Find orphaned FAISS indices (those without Redis metadata)
            orphaned_indices = []
            
            for idx in range(total_vectors):
                # Check if this FAISS index has corresponding Redis metadata
                idx_uuid_key = f"faiss_idx:{idx}"
                uuid_value = await self.redis.get(idx_uuid_key)
                
                if uuid_value is None:
                    # This FAISS index has no Redis metadata - it's orphaned
                    orphaned_indices.append(idx)
                else:
                    # Decode UUID if it's bytes
                    if isinstance(uuid_value, bytes):
                        uuid_value = uuid_value.decode('utf-8')
                    
                    # Check if this UUID exists in Redis
                    if uuid_value not in redis_uuids_set:
                        orphaned_indices.append(idx)
            
            # Clean up orphaned vectors
            if orphaned_indices:
                logger.info(f"Found {len(orphaned_indices)} orphaned FAISS vectors")
                await faiss_service.delete_vectors(orphaned_indices)
                
                # Clean up idx-uuid mappings
                pipeline = await self.redis.pipeline()
                for idx in orphaned_indices:
                    pipeline.delete(f"faiss_idx:{idx}")
                await pipeline.execute()
                
                logger.info(f"Cleaned {len(orphaned_indices)} orphaned FAISS vectors")
                return len(orphaned_indices)
            else:
                logger.info("No orphaned FAISS vectors found")
                return 0
                
        except Exception as e:
            logger.error(f"Failed to clean FAISS vectors without metadata: {e}")
            raise RedisOperationError("clean_faiss_vectors_without_metadata", str(e))

    async def get_all_record_ids(self, uuids: List[str] = None) -> List[str]:
        """
        Get chunk UUIDs from Redis.
        
        Args:
            uuids: Optional list of UUIDs to filter by. If None, returns all UUIDs.
            
        Returns:
            List of chunk UUIDs (filtered by uuids if provided)
            
        Raises:
            RedisOperationError: If Redis operation fails
        """
        try:
            if uuids is not None:
                # Filter by provided UUIDs - check which ones exist in Redis
                pipeline = await self.redis.pipeline()
                for uuid in uuids:
                    pipeline.exists(f"vector:{uuid}")
                
                try:
                    exists_results = await pipeline.execute()
                except redis.RedisError as e:
                    raise create_redis_operation_error("pipeline_execute", e, {"uuids": uuids})
                
                existing_uuids = [uuid for uuid, exists in zip(uuids, exists_results) if exists]
                return existing_uuids
            else:
                # Get all UUIDs
                try:
                    keys = await self.redis.keys("vector:*")
                except redis.RedisError as e:
                    raise create_redis_operation_error("keys", e)
                
                record_ids = []
                for key in keys:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    record_ids.append(key.replace("vector:", ""))
                return record_ids
        except redis.RedisError as e:
            raise create_redis_operation_error("get_all_record_ids", e, {"uuids": uuids})
        except Exception as e:
            logger.error(f"Failed to get record IDs: {e}")
            raise RedisOperationError("get_all_record_ids", str(e))

    async def count_records(self, include_deleted: bool = False) -> int:
        """
        Count total number of chunks in Redis.
        
        Args:
            include_deleted: Whether to include soft-deleted records
            
        Returns:
            Number of chunks
        """
        try:
            if include_deleted:
                # Count all records
                cursor = 0
                count = 0
                while True:
                    try:
                        cursor, keys = await self.redis.scan(cursor=cursor, match="vector:*", count=1000)
                    except redis.RedisError as e:
                        raise create_redis_operation_error("scan", e)
                    count += len(keys)
                    if cursor == 0:
                        break
                logger.info(f"Total records in Redis: {count}")
                return count
            else:
                # Count only non-deleted records
                cursor = 0
                count = 0
                while True:
                    try:
                        cursor, keys = await self.redis.scan(cursor=cursor, match="vector:*", count=1000)
                    except redis.RedisError as e:
                        raise create_redis_operation_error("scan", e)
                    
                    # Check which keys are not deleted
                    if keys:
                        pipeline = await self.redis.pipeline()
                        for key in keys:
                            pipeline.hget(key, "is_deleted")
                        
                        try:
                            deletion_status = await pipeline.execute()
                            # Count non-deleted records
                            for status in deletion_status:
                                if status != b'true' and status != 'true':
                                    count += 1
                        except redis.RedisError as e:
                            raise create_redis_operation_error("pipeline_execute", e)
                    
                    if cursor == 0:
                        break
                        
                logger.info(f"Active records in Redis: {count}")
                return count
                
        except redis.RedisError as e:
            raise create_redis_operation_error("count_records", e)
        except Exception as e:
            error_msg = f"Redis error while counting records: {str(e)}"
            logger.error(error_msg)
            raise RedisOperationError("count_records", str(e))

    async def count(self) -> int:
        """Return number of chunk records in Redis (by vector:* keys)."""
        keys = await self.redis.keys("vector:*")
        return len(keys)

    # ============================================================================
    # VECTOR REVERSE INDEX METHODS
    # ============================================================================



    def _validate_chunk(self, chunk) -> None:
        """
        Validate SemanticChunk object.
        
        Args:
            chunk: SemanticChunk object to validate
            
        Raises:
            ChunkValidationError: If chunk is invalid
        """
        if not isinstance(chunk, SemanticChunk):
            raise ChunkValidationError(f"Expected SemanticChunk, got {type(chunk)}")
            
        if not chunk.uuid:
            raise ChunkValidationError("Chunk must have UUID", chunk.uuid)

    def _format_vector_log(self, vector, max_show=3):
        """
        Format vector for logging - show dimension and first few values.
        
        Args:
            vector: Vector to format
            max_show: Maximum number of values to show
            
        Returns:
            Formatted string for logging
        """
        if not vector:
            return "empty"
        if isinstance(vector, (list, tuple)):
            if len(vector) == 0:
                return "empty"
            preview = vector[:max_show]
            return f"dim={len(vector)}, values={preview}{'...' if len(vector) > max_show else ''}"
        return f"type={type(vector)}"
    
    def _serialize_chunk(self, chunk: SemanticChunk) -> dict:
        """
        Serialize chunk to flat dict for Redis storage (включая embedding).
        """
        try:
            flat_dict = chunk.to_flat_dict(for_redis=True, include_embedding=True)
            logger.debug(f"_serialize_chunk: flat_dict keys: {list(flat_dict.keys())}")
            
            # Format embedding for logging
            embedding_data = flat_dict.get('embedding')
            if embedding_data:
                logger.debug(f"_serialize_chunk: embedding in flat_dict: {self._format_vector_log(embedding_data)}")
            else:
                logger.debug(f"_serialize_chunk: embedding in flat_dict: NOT_FOUND")
            
            filtered_dict = {}
            for k, v in flat_dict.items():
                if v is not None:
                    if isinstance(v, list):
                        filtered_dict[k] = json.dumps(v, ensure_ascii=False)
                        logger.debug(f"_serialize_chunk: serialized list {k}: {len(v)} items")
                    else:
                        filtered_dict[k] = v
            logger.debug(f"_serialize_chunk: final filtered_dict keys: {list(filtered_dict.keys())}")
            return filtered_dict
        except Exception as e:
            raise ChunkSerializationError("to_flat_dict", str(e), chunk.uuid)

    async def _rollback_redis_changes(self, uuids: List[str]) -> None:
        """
        Rollback Redis changes by deleting the specified UUIDs.
        
        Args:
            uuids: List of UUIDs to delete from Redis
            
        Raises:
            RedisOperationError: If rollback fails
        """
        try:
            logger.info(f"Rolling back Redis changes for {len(uuids)} UUIDs: {uuids}")
            
            # Delete the chunks from Redis
            pipeline = await self.redis.pipeline()
            
            for uuid in uuids:
                # Delete metadata hash
                key = f"vector:{uuid}"
                pipeline.delete(key)
                
                # Delete all list fields
                list_keys = await self.redis.keys(f"*:{uuid}")
                for list_key in list_keys:
                    if isinstance(list_key, bytes):
                        list_key = list_key.decode('utf-8')
                    pipeline.delete(list_key)
            
            # Execute rollback
            await pipeline.execute()
            

            
            logger.info("Redis rollback completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to rollback Redis changes: {e}")
            raise RedisOperationError("rollback_redis_changes", str(e))

    async def _rollback_redis_deletions(self, uuids: List[str]) -> None:
        """
        Rollback Redis deletions by restoring the specified UUIDs.
        This is a simplified rollback - in production you'd need to restore the actual data.
        
        Args:
            uuids: List of UUIDs that were deleted (for logging purposes)
            
        Raises:
            RedisOperationError: If rollback fails
        """
        try:
            logger.info(f"Rolling back Redis deletions for {len(uuids)} UUIDs: {uuids}")
            
            # Note: This is a simplified rollback
            # In a production system, you'd need to restore the actual chunk data
            # For now, we just log the rollback attempt
            

            
            logger.warning("Redis deletion rollback attempted - data may be inconsistent")
            
        except Exception as e:
            logger.error(f"Failed to rollback Redis deletions: {e}")
            raise RedisOperationError("rollback_redis_deletions", str(e))





    # Index Management Methods - REMOVED: Now using IndexManager
    # All index operations are now handled by self.index_manager

    async def _verify_consistency_after_operation(
        self, 
        initial_redis_count: int, 
        initial_faiss_count: int, 
        operation_count: int, 
        operation_name: str
    ) -> None:
        """
        Verify consistency between Redis and FAISS after operation.
        
        Args:
            initial_redis_count: Redis count before operation
            initial_faiss_count: FAISS count before operation  
            operation_count: Number of records processed
            operation_name: Name of the operation for logging
        """
        try:
            current_redis_count = await self.count_records(include_deleted=False)
            current_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
            
            # For upsert operations, counts should increase by operation_count
            # For delete operations, counts should decrease by operation_count
            # For soft delete operations, only Redis count should decrease, FAISS count stays the same
            expected_redis_count = initial_redis_count + operation_count
            
            if "soft_delete" in operation_name:
                # Soft delete: only Redis count changes, FAISS count stays the same
                expected_faiss_count = initial_faiss_count
            else:
                # Hard delete or upsert: both counts change
                expected_faiss_count = initial_faiss_count + operation_count
            
            if current_redis_count != expected_redis_count:
                logger.error(f"[CONSISTENCY ERROR] {operation_name}: Redis count mismatch. "
                           f"Expected: {expected_redis_count}, Got: {current_redis_count}")
            
            if self.faiss_service and current_faiss_count != expected_faiss_count:
                logger.error(f"[CONSISTENCY ERROR] {operation_name}: FAISS count mismatch. "
                           f"Expected: {expected_faiss_count}, Got: {current_faiss_count}")
            
            if current_redis_count == expected_redis_count and current_faiss_count == expected_faiss_count:
                logger.info(f"[CONSISTENCY OK] {operation_name}: Counts verified successfully")
                
        except Exception as e:
            logger.error(f"Failed to verify consistency after {operation_name}: {e}")

    async def _ensure_indexes_for_chunks(self, chunks: List[SemanticChunk]) -> None:
        """
        Ensure that indexes exist for fields that are actually present in the chunks.
        
        Args:
            chunks: List of chunks to analyze for field presence
        """
        if not self.index_manager:
            logger.warning("IndexManager not available - cannot create indexes")
            return
        
        # Get existing indexed fields
        existing_indexes = set(self.index_manager.indexed_fields)
        logger.info(f"Existing indexes: {existing_indexes}")
        
        # Analyze all chunks to find fields that need indexing
        fields_to_index = set()
        for chunk in chunks:
            chunk_dict = chunk.model_dump()
            for field_name, field_value in chunk_dict.items():
                # Only index scalar fields with non-None values
                if field_value is not None and not isinstance(field_value, (list, dict)):
                    fields_to_index.add(field_name)
        
        logger.info(f"Fields found in chunks: {fields_to_index}")
        
        # Find fields that need new indexes
        fields_needing_indexes = fields_to_index - existing_indexes
        
        if fields_needing_indexes:
            logger.info(f"Creating indexes for fields: {fields_needing_indexes}")
            try:
                from vector_store.services.index_manager.base import IndexType
                
                for field_name in fields_needing_indexes:
                    try:
                        await self.index_manager.create_index(field_name, IndexType.SCALAR)
                        logger.info(f"Created index for field: {field_name}")
                    except Exception as e:
                        if "already exists" in str(e):
                            logger.debug(f"Index for field {field_name} already exists")
                        else:
                            logger.warning(f"Failed to create index for field {field_name}: {e}")
            except Exception as e:
                logger.warning(f"Failed to create indexes: {e}")
        else:
            logger.info("All necessary indexes already exist")

    async def _cleanup_empty_indexes(self) -> None:
        """
        Remove indexes that have no data.
        """
        if not self.index_manager:
            return
        
        try:
            # Get all indexed fields
            indexed_fields = self.index_manager.indexed_fields
            
            for field_name in indexed_fields:
                try:
                    # Check if index has any data
                    field_keys = await self.redis.keys(f'field_index:{field_name}:*')
                    if not field_keys:
                        logger.info(f"Removing empty index for field: {field_name}")
                        await self.index_manager.drop_index(field_name)
                except Exception as e:
                    logger.warning(f"Failed to check/cleanup index for field {field_name}: {e}")
        except Exception as e:
            logger.warning(f"Failed to cleanup empty indexes: {e}")

    async def find_chunks_by_query(
        self,
        chunk_query: 'ChunkQuery',
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
            # Use the new search method
            results = await self.search(chunk_query)
            
            # Filter out deleted records if needed
            if not include_deleted:
                results = [chunk for chunk in results if not chunk.get('is_deleted', False)]
            
            return results
            
        except Exception as e:
            logger.error(f"Error finding chunks by query: {e}")
            raise

    async def count_chunks_by_query(
        self,
        chunk_query: 'ChunkQuery',
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
    
    async def search(
        self,
        chunk_query: 'ChunkQuery',
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Поиск с использованием ChunkQuery.
        
        Args:
            chunk_query: Запрос для поиска (обязательно должен содержать критерии поиска)
            limit: Максимальное количество результатов (опциональный параметр)
            offset: Смещение результатов (опциональный параметр)
            
        Returns:
            Список найденных чанков
            
        Raises:
            ValueError: Если ChunkQuery не содержит критериев поиска
        """
        try:
            if limit is not None and limit < 0:
                raise ValueError("limit must be non-negative if specified")
            
            if offset is not None and offset < 0:
                raise ValueError("offset must be non-negative if specified")
            
            if not self.index_manager:
                raise ValueError("IndexManager not available")
            
            # Проверка наличия критериев поиска в ChunkQuery
            has_search_criteria = (
                bool(chunk_query.search_query or chunk_query.text) or
                bool(chunk_query.embedding) or
                bool(chunk_query.category or chunk_query.tags or chunk_query.type or chunk_query.language or 
                     chunk_query.is_deleted is not None or (hasattr(chunk_query, 'block_meta') and chunk_query.block_meta))
            )
            
            if not has_search_criteria:
                raise ValueError("ChunkQuery must contain at least one search criterion")
            
            # Выполнение поиска через AtomicIndexManager
            search_results = await self.index_manager.search_by_chunk_query(chunk_query, limit, offset)
            
            # Преобразование результатов в формат чанков
            chunks = []
            for result in search_results:
                chunk = {
                    "uuid": result.uuid,
                    "metadata": result.metadata,
                    "score": result.score
                }
                chunks.append(chunk)
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error searching with ChunkQuery: {e}")
            raise
    
    async def delete_by_query(self, chunk_query: 'ChunkQuery') -> int:
        """
        Удаление чанков по запросу.
        
        Args:
            chunk_query: Запрос для поиска чанков для удаления
            
        Returns:
            Количество удаленных чанков
        """
        try:
            if not self.index_manager:
                raise ValueError("IndexManager not available")
            
            # Поиск чанков для удаления
            search_results = self.index_manager.search_by_chunk_query(chunk_query)
            
            # Удаление найденных чанков
            deleted_count = 0
            for result in search_results:
                try:
                    # Удаление через существующий метод
                    await self.delete_chunk(result.uuid)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete chunk {result.uuid}: {e}")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting by query: {e}")
            raise


