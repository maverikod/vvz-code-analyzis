"""
Improved Redis Metadata CRUD Service

This module provides an improved version of RedisMetadataCRUDService with better upsert algorithm:
1. Get existing FAISS indices from Redis
2. Delete old indices from FAISS
3. Add new vectors to FAISS
4. Write data to Redis with new indices
5. Full rollback on any error

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import json
import numpy as np
import redis.asyncio as redis
from typing import Dict, List, Any, Optional, Tuple
from chunk_metadata_adapter import SemanticChunk
from datetime import datetime

from vector_store.exceptions import (
    RedisOperationError, ChunkValidationError, ChunkSerializationError,
    create_redis_operation_error, DataProcessingError, SerializationError,
    DeserializationError, UnexpectedError
)

from vector_store.services.faiss_index_service import (
    FaissIndexService, FaissIndexError, FaissSearchError, FaissVectorError, FaissStorageError
)

logger = logging.getLogger("vector_store.redis.improved")

class ImprovedRedisMetadataCRUDService:
    """
    Improved service for CRUD operations on chunk metadata and vectors in Redis.
    
    Features improved upsert algorithm with proper FAISS index management:
    - Delete old FAISS indices before adding new ones
    - Full rollback support for both FAISS and Redis
    - Better consistency guarantees
    """
    
    def __init__(self, redis_client=None, redis_url=None, faiss_service=None, index_manager=None):
        """
        Initialize improved Redis CRUD service.
        
        Args:
            redis_client: Redis client instance
            redis_url: Redis connection URL
            faiss_service: FAISS service for vector operations
            index_manager: Pre-initialized IndexManager instance
        """
        if redis_client:
            self.redis = redis_client
        elif redis_url:
            self.redis = redis.from_url(redis_url)
        else:
            raise ValueError("Either redis_client or redis_url must be provided")
        
        # FAISS service for vector operations
        self.faiss_service = faiss_service
        
        # Use provided IndexManager or create one if not provided
        if index_manager:
            self.index_manager = index_manager
            logger.info("Using provided IndexManager")
        else:
            try:
                from vector_store.services.index_manager.atomic_operations import AtomicIndexManager
                self.index_manager = AtomicIndexManager(redis_client=self.redis)
                logger.info("IndexManager created successfully")
            except Exception as e:
                logger.warning(f"Failed to create IndexManager: {e}")
                self.index_manager = None
        
        # TTL for chunk data
        self.chunk_ttl = 86400  # 24 hours
        
        logger.info("ImprovedRedisMetadataCRUDService initialized")

    async def upsert_chunks(self, chunks: List[SemanticChunk]) -> List[str]:
        """
        Create or update multiple chunks atomically using improved algorithm:
        1. Get existing FAISS indices from Redis
        2. Delete old indices from FAISS
        3. Add new vectors to FAISS
        4. Write data to Redis with new indices
        5. Full rollback on any error
        
        Args:
            chunks: List of SemanticChunk objects
            
        Returns:
            List of UUIDs of successfully upserted chunks
            
        Raises:
            ValueError: If chunk validation fails
            RedisOperationError: If Redis operation fails
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
        
        # Get initial counts for consistency check
        initial_redis_count = await self.count_records(include_deleted=False)
        initial_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
        
        logger.info(f"Starting improved upsert for {len(chunks)} chunks. Initial counts - Redis: {initial_redis_count}, FAISS: {initial_faiss_count}")
        
        # STEP 1: BACKUP existing data for rollback
        logger.info("Step 1: Backing up existing chunk data for rollback")
        backup_data = await self._backup_existing_chunks(chunks)
        
        # STEP 2: Get existing FAISS indices and prepare for deletion
        logger.info("Step 2: Getting existing FAISS indices")
        existing_faiss_data = await self._get_existing_faiss_data(chunks)
        old_faiss_indices = list(existing_faiss_data.keys())
        
        if old_faiss_indices:
            logger.info(f"Found {len(old_faiss_indices)} existing FAISS indices to delete: {old_faiss_indices}")
        
        # STEP 3: Delete old FAISS indices
        if old_faiss_indices:
            logger.info("Step 3: Deleting old FAISS indices")
            try:
                # Sort indices in reverse order for safe deletion
                sorted_indices = sorted(old_faiss_indices, reverse=True)
                deleted_count = await self.faiss_service.delete_vectors(sorted_indices)
                logger.info(f"Successfully deleted {deleted_count} old FAISS vectors")
                
                # Remove old FAISS mappings from Redis
                idx_pipeline = await self.redis.pipeline()
                for idx in old_faiss_indices:
                    idx_pipeline.delete(f"faiss_idx:{idx}")
                await idx_pipeline.execute()
                logger.info(f"Removed {len(old_faiss_indices)} old FAISS mappings from Redis")
                
            except Exception as e:
                logger.error(f"Failed to delete old FAISS indices: {e}")
                # Rollback: restore old FAISS indices
                await self._restore_faiss_indices(existing_faiss_data)
                raise RedisOperationError("faiss_delete_old_vectors", f"FAISS deletion failed: {e}")
        
        # STEP 4: Prepare new vectors for FAISS
        logger.info("Step 4: Preparing new vectors for FAISS")
        new_vectors = []
        uuid_list = []
        
        for chunk in chunks:
            if chunk.embedding:
                vector = np.array(chunk.embedding, dtype=np.float32)
                new_vectors.append(vector)
                uuid_list.append(chunk.uuid)
                logger.debug(f"Prepared vector for chunk {chunk.uuid}")
            else:
                logger.debug(f"No embedding for chunk {chunk.uuid}")
        
        # STEP 5: Add new vectors to FAISS
        new_faiss_indices = []
        if new_vectors:
            logger.info(f"Step 5: Adding {len(new_vectors)} new vectors to FAISS")
            try:
                new_faiss_indices = await self.faiss_service.add_vectors(new_vectors)
                logger.info(f"Successfully added vectors to FAISS, got indices: {new_faiss_indices}")
            except Exception as e:
                logger.error(f"Failed to add new vectors to FAISS: {e}")
                # Rollback: restore old FAISS indices
                await self._restore_faiss_indices(existing_faiss_data)
                raise RedisOperationError("faiss_add_new_vectors", f"FAISS addition failed: {e}")
        
        # STEP 6: Write data to Redis with new indices
        logger.info("Step 6: Writing data to Redis with new indices")
        try:
            successful_uuids = await self._write_chunks_to_redis_with_indices(chunks, new_faiss_indices, uuid_list)
            logger.info(f"Successfully wrote {len(successful_uuids)} chunks to Redis")
        except Exception as e:
            logger.error(f"Failed to write chunks to Redis: {e}")
            # Rollback: restore old FAISS indices and Redis data
            await self._restore_faiss_indices(existing_faiss_data)
            await self._restore_redis_data(backup_data)
            raise RedisOperationError("redis_write_chunks", f"Redis write failed: {e}")
        
        # STEP 7: Verify consistency
        logger.info("Step 7: Verifying consistency")
        await self._verify_consistency_after_operation(
            initial_redis_count, initial_faiss_count, 
            len(successful_uuids), "improved_upsert_chunks"
        )
        
        # Final count verification
        final_redis_count = await self.count_records(include_deleted=False)
        final_faiss_count = await self.faiss_service.count() if self.faiss_service else 0
        
        logger.info(f"Improved upsert completed successfully. Final counts - Redis: {final_redis_count}, FAISS: {final_faiss_count}")
        logger.info(f"Successfully upserted {len(successful_uuids)} chunks")
        
        return successful_uuids

    async def _backup_existing_chunks(self, chunks: List[SemanticChunk]) -> Dict[str, Any]:
        """
        Backup existing chunk data for rollback purposes.
        
        Args:
            chunks: List of chunks to backup
            
        Returns:
            Dictionary with backup data
        """
        backup_data = {}
        
        for chunk in chunks:
            uuid = chunk.uuid
            backup_data[uuid] = {
                'redis_data': {},
                'faiss_index': None,
                'list_fields': {}
            }
            
            # Backup Redis hash data
            hash_key = f"vector:{uuid}"
            redis_data = await self.redis.hgetall(hash_key)
            if redis_data:
                backup_data[uuid]['redis_data'] = {
                    k.decode('utf-8') if isinstance(k, bytes) else k: 
                    v.decode('utf-8') if isinstance(v, bytes) else v
                    for k, v in redis_data.items()
                }
            
            # Backup FAISS index
            faiss_idx = await self.redis.hget(hash_key, "faiss_idx")
            if faiss_idx:
                if isinstance(faiss_idx, bytes):
                    faiss_idx = faiss_idx.decode('utf-8')
                backup_data[uuid]['faiss_index'] = int(faiss_idx)
            
            # Backup list fields
            for field_name in ['tags', 'categories', 'entities']:
                list_key = f"{field_name}:{uuid}"
                list_data = await self.redis.lrange(list_key, 0, -1)
                if list_data:
                    backup_data[uuid]['list_fields'][field_name] = [
                        item.decode('utf-8') if isinstance(item, bytes) else item
                        for item in list_data
                    ]
        
        logger.debug(f"Backed up data for {len(backup_data)} chunks")
        return backup_data

    async def _get_existing_faiss_data(self, chunks: List[SemanticChunk]) -> Dict[int, str]:
        """
        Get existing FAISS indices for chunks.
        
        Args:
            chunks: List of chunks to check
            
        Returns:
            Dictionary mapping FAISS index to UUID
        """
        existing_faiss_data = {}
        
        # Batch get FAISS indices
        pipeline = await self.redis.pipeline()
        for chunk in chunks:
            pipeline.hget(f"vector:{chunk.uuid}", "faiss_idx")
        
        results = await pipeline.execute()
        
        for chunk, result in zip(chunks, results):
            if result is not None:
                if isinstance(result, bytes):
                    faiss_idx = int(result.decode('utf-8'))
                else:
                    faiss_idx = int(result)
                existing_faiss_data[faiss_idx] = chunk.uuid
                logger.debug(f"Found existing FAISS index {faiss_idx} for chunk {chunk.uuid}")
        
        logger.info(f"Found {len(existing_faiss_data)} existing FAISS indices")
        return existing_faiss_data

    async def _restore_faiss_indices(self, existing_faiss_data: Dict[int, str]) -> None:
        """
        Restore FAISS indices from backup data.
        
        Args:
            existing_faiss_data: Dictionary mapping FAISS index to UUID
        """
        if not existing_faiss_data:
            return
        
        logger.info(f"Restoring {len(existing_faiss_data)} FAISS indices")
        
        try:
            # Get vectors from Redis and restore to FAISS
            for faiss_idx, uuid in existing_faiss_data.items():
                vector_key = f"vector_data:{uuid}"
                vector_data = await self.redis.get(vector_key)
                
                if vector_data:
                    if isinstance(vector_data, bytes):
                        vector_data = vector_data.decode('utf-8')
                    
                    embedding = json.loads(vector_data)
                    vector = np.array(embedding, dtype=np.float32)
                    
                    # Add vector back to FAISS
                    new_idx = await self.faiss_service.add_vector(vector)
                    
                    # Update mapping
                    await self.redis.set(f"faiss_idx:{new_idx}", uuid)
                    await self.redis.hset(f"vector:{uuid}", "faiss_idx", new_idx)
                    
                    logger.debug(f"Restored FAISS index {faiss_idx} -> {new_idx} for chunk {uuid}")
            
            logger.info("Successfully restored FAISS indices")
            
        except Exception as e:
            logger.error(f"Failed to restore FAISS indices: {e}")
            raise RedisOperationError("restore_faiss_indices", f"FAISS restoration failed: {e}")

    async def _restore_redis_data(self, backup_data: Dict[str, Any]) -> None:
        """
        Restore Redis data from backup.
        
        Args:
            backup_data: Backup data dictionary
        """
        if not backup_data:
            return
        
        logger.info(f"Restoring Redis data for {len(backup_data)} chunks")
        
        try:
            pipeline = await self.redis.pipeline()
            
            for uuid, data in backup_data.items():
                # Restore hash data
                if data['redis_data']:
                    hash_key = f"vector:{uuid}"
                    pipeline.hset(hash_key, mapping=data['redis_data'])
                    pipeline.expire(hash_key, self.chunk_ttl)
                
                # Restore list fields
                for field_name, field_data in data['list_fields'].items():
                    if field_data:
                        list_key = f"{field_name}:{uuid}"
                        pipeline.delete(list_key)
                        pipeline.rpush(list_key, *field_data)
                        pipeline.expire(list_key, self.chunk_ttl)
            
            await pipeline.execute()
            logger.info("Successfully restored Redis data")
            
        except Exception as e:
            logger.error(f"Failed to restore Redis data: {e}")
            raise RedisOperationError("restore_redis_data", f"Redis restoration failed: {e}")

    async def _write_chunks_to_redis_with_indices(self, chunks: List[SemanticChunk], 
                                                faiss_indices: List[int], 
                                                uuid_list: List[str]) -> List[str]:
        """
        Write chunks to Redis with FAISS indices.
        
        Args:
            chunks: List of chunks to write
            faiss_indices: List of FAISS indices
            uuid_list: List of UUIDs corresponding to vectors
            
        Returns:
            List of successfully written UUIDs
        """
        successful_uuids = []
        
        # Prepare Redis operations
        pipeline = await self.redis.pipeline()
        vector_pipeline = await self.redis.pipeline()
        idx_pipeline = await self.redis.pipeline()
        
        # Create mapping from UUID to FAISS index
        uuid_to_faiss_idx = dict(zip(uuid_list, faiss_indices))
        
        for chunk in chunks:
            try:
                # Serialize chunk
                flat_dict = self._serialize_chunk(chunk)
                
                # Separate scalar fields and arrays
                list_fields = {k: v for k, v in flat_dict.items() if isinstance(v, list)}
                scalar_fields = {k: v for k, v in flat_dict.items() if not isinstance(v, list) and v is not None}
                
                # Add FAISS index to scalar fields if available
                if chunk.uuid in uuid_to_faiss_idx:
                    scalar_fields['faiss_idx'] = uuid_to_faiss_idx[chunk.uuid]
                
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
                    continue
                
                # Store vector in Redis
                if chunk.embedding:
                    vector_key = f"vector_data:{chunk.uuid}"
                    vector_pipeline.set(vector_key, json.dumps(chunk.embedding))
                    vector_pipeline.expire(vector_key, self.chunk_ttl)
                
                successful_uuids.append(chunk.uuid)
                
            except Exception as e:
                logger.error(f"Failed to process chunk {chunk.uuid}: {e}")
                continue
        
        # Execute Redis operations
        if successful_uuids:
            await pipeline.execute()
            await vector_pipeline.execute()
            
            # Store FAISS index mappings
            for uuid, faiss_idx in uuid_to_faiss_idx.items():
                if uuid in successful_uuids:
                    idx_pipeline.set(f"faiss_idx:{faiss_idx}", uuid)
            
            await idx_pipeline.execute()
        
        return successful_uuids

    async def delete_chunks(self, uuids: List[str]) -> List[str]:
        """
        Soft delete chunks by marking them as deleted.
        
        Args:
            uuids: List of chunk UUIDs to delete
            
        Returns:
            List of successfully deleted UUIDs
        """
        logger.info(f"Soft deleting {len(uuids)} chunks")
        
        successful_deletes = []
        
        try:
            # Mark chunks as deleted in Redis
            pipeline = await self.redis.pipeline()
            
            for uuid in uuids:
                hash_key = f"vector:{uuid}"
                pipeline.hset(hash_key, "is_deleted", "true")
                successful_deletes.append(uuid)
            
            await pipeline.execute()
            logger.info(f"Successfully soft deleted {len(successful_deletes)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to soft delete chunks: {e}")
            raise RedisOperationError("soft_delete_chunks", f"Soft delete failed: {e}")
        
        return successful_deletes

    async def hard_delete_chunks(self, uuids: List[str] = None, delete_all: bool = False) -> List[str]:
        """
        Hard delete chunks by removing them from both Redis and FAISS.
        
        Args:
            uuids: List of chunk UUIDs to delete (if None and delete_all=False, no action)
            delete_all: If True, delete all chunks
            
        Returns:
            List of successfully deleted UUIDs
        """
        if delete_all:
            logger.info("Hard deleting all chunks")
            # Get all chunk UUIDs
            redis_keys = await self.redis.keys("vector:*")
            uuids = [key.decode('utf-8').replace('vector:', '') for key in redis_keys]
        elif not uuids:
            logger.info("No UUIDs provided for hard delete")
            return []
        else:
            logger.info(f"Hard deleting {len(uuids)} chunks")
        
        successful_deletes = []
        
        try:
            # Get FAISS indices for the chunks
            faiss_indices = []
            pipeline = await self.redis.pipeline()
            
            for uuid in uuids:
                pipeline.hget(f"vector:{uuid}", "faiss_idx")
            
            results = await pipeline.execute()
            
            for uuid, result in zip(uuids, results):
                if result is not None:
                    if isinstance(result, bytes):
                        faiss_idx = int(result.decode('utf-8'))
                    else:
                        faiss_idx = int(result)
                    faiss_indices.append(faiss_idx)
            
            # Delete vectors from FAISS
            if faiss_indices:
                # Sort indices in reverse order for safe deletion
                sorted_indices = sorted(faiss_indices, reverse=True)
                deleted_count = await self.faiss_service.delete_vectors(sorted_indices)
                logger.info(f"Deleted {deleted_count} vectors from FAISS")
            
            # Delete all Redis data for the chunks
            pipeline = await self.redis.pipeline()
            
            for uuid in uuids:
                # Delete main hash
                pipeline.delete(f"vector:{uuid}")
                
                # Delete vector data
                pipeline.delete(f"vector_data:{uuid}")
                
                # Delete list fields
                for field_name in ['tags', 'categories', 'entities', 'tokens', 'links']:
                    pipeline.delete(f"{field_name}:{uuid}")
                
                # Delete metrics fields
                for field_name in ['metrics.bm25_tokens', 'metrics.tokens', 'metrics.links']:
                    pipeline.delete(f"{field_name}:{uuid}")
                
                # Add to successful deletes
                successful_deletes.append(uuid)
            
            await pipeline.execute()
            
            # Delete FAISS mappings separately
            if faiss_indices:
                faiss_pipeline = await self.redis.pipeline()
                for idx in faiss_indices:
                    faiss_pipeline.delete(f"faiss_idx:{idx}")
                await faiss_pipeline.execute()
            
            await pipeline.execute()
            logger.info(f"Successfully hard deleted {len(successful_deletes)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to hard delete chunks: {e}")
            raise RedisOperationError("hard_delete_chunks", f"Hard delete failed: {e}")
        
        return successful_deletes

    def _validate_chunk(self, chunk: SemanticChunk) -> None:
        """
        Validate chunk data.
        
        Args:
            chunk: Chunk to validate
            
        Raises:
            ChunkValidationError: If chunk is invalid
        """
        if not chunk.uuid:
            raise ChunkValidationError("Chunk UUID is required")
        
        if not chunk.body:
            raise ChunkValidationError("Chunk body is required")

    def _serialize_chunk(self, chunk: SemanticChunk) -> Dict[str, Any]:
        """
        Serialize chunk to flat dictionary.
        
        Args:
            chunk: Chunk to serialize
            
        Returns:
            Flat dictionary representation
        """
        # Use the chunk's built-in serialization method
        flat_dict = chunk.to_flat_dict(for_redis=True, include_embedding=False)
        
        # Ensure required fields are present
        if 'uuid' not in flat_dict:
            flat_dict['uuid'] = chunk.uuid
        if 'body' not in flat_dict:
            flat_dict['body'] = chunk.body
        if 'type' not in flat_dict:
            flat_dict['type'] = chunk.type
        
        return flat_dict

    async def _ensure_indexes_for_chunks(self, chunks: List[SemanticChunk]) -> None:
        """
        Ensure necessary indexes exist for chunks.
        
        Args:
            chunks: List of chunks to process
        """
        # This is a placeholder - implement index creation logic
        pass

    async def count_records(self, include_deleted: bool = False) -> int:
        """
        Count records in Redis.
        
        Args:
            include_deleted: Whether to include deleted records
            
        Returns:
            Number of records
        """
        # This is a placeholder - implement counting logic
        return 0

    async def _verify_consistency_after_operation(self, initial_redis_count: int, 
                                                initial_faiss_count: int, 
                                                expected_change: int, 
                                                operation: str) -> None:
        """
        Verify consistency after operation.
        
        Args:
            initial_redis_count: Initial Redis count
            initial_faiss_count: Initial FAISS count
            expected_change: Expected change in count
            operation: Operation name
        """
        # This is a placeholder - implement consistency verification
        pass
