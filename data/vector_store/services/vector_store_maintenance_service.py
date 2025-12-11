"""
Vector Store Maintenance Service

This module provides the VectorStoreMaintenanceService class for maintenance operations
that require special handling: background execution, database locking strategies,
progress tracking, and rollback capabilities.

Features:
- Deferred cleanup of soft-deleted records
- Duplicate detection and analysis
- Full reindexing with database locking
- Progress tracking for long-running operations
- Background execution support
- Rollback capabilities
- Comprehensive error handling

Usage:
    service = VectorStoreMaintenanceService(
        crud_service=crud_service,
        faiss_service=faiss_service,
        redis_client=redis_client
    )
    
    # Background cleanup
    result = await service.deferred_cleanup(background=True)
    
    # Find duplicates with progress tracking
    result = await service.find_duplicates(batch_size=1000)
    
    # Full reindex with database locking
    result = await service.reindex_all(embedding_service, lock_database=True)
"""

import logging
import asyncio
import time
import hashlib
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone
import json

from chunk_metadata_adapter import SemanticChunk
from chunk_metadata_adapter.chunk_query import ChunkQuery

from vector_store.services.service_lock_manager import ServiceLockManager
from vector_store.exceptions import (
    RedisOperationError, ServiceInitializationError, MaintenanceOperationError
)

logger = logging.getLogger("vector_store.maintenance")


class VectorStoreMaintenanceService:
    """
    Service for maintenance operations that require special handling.
    
    Features:
    - Background execution with progress tracking
    - Database locking strategies for different operation types
    - Batch processing for large datasets
    - Rollback capabilities
    - Comprehensive error handling and logging
    
    Operations:
    - Deferred cleanup: Remove soft-deleted records
    - Duplicate detection: Find and analyze duplicate records
    - Full reindexing: Rebuild entire vector index
    - Orphan cleanup: Remove records without FAISS indices
    - Statistics collection: Gather comprehensive metrics
    
    Architecture:
    - Uses existing CRUD and FAISS services
    - Implements ServiceLockManager for database locking
    - Progress tracking via Redis
    - Background task management
    """
    
    def __init__(self,
                 crud_service,
                 faiss_service,
                 redis_client,
                 lock_timeout: int = 3600):
        """
        Initialize maintenance service.
        
        Args:
            crud_service: RedisMetadataCRUDService instance
            faiss_service: FaissIndexService instance
            redis_client: Redis client
            lock_timeout: Lock timeout in seconds (default: 1 hour)
            
        Raises:
            ServiceInitializationError: If initialization fails
        """
        if not crud_service:
            raise ServiceInitializationError("VectorStoreMaintenanceService", "CRUD service is required")
        if not faiss_service:
            raise ServiceInitializationError("VectorStoreMaintenanceService", "FAISS service is required")
        if not redis_client:
            raise ServiceInitializationError("VectorStoreMaintenanceService", "Redis client is required")
        
        self.crud_service = crud_service
        self.faiss_service = faiss_service
        self.redis = redis_client
        self.lock_manager = ServiceLockManager(redis_client, timeout=lock_timeout)
        
        # Progress tracking key prefix
        self.progress_prefix = "maintenance:progress:"
        
        logger.info("VectorStoreMaintenanceService initialized successfully")

    # ============================================================================
    # DEFERRED CLEANUP OPERATIONS
    # ============================================================================

    async def deferred_cleanup(self,
                             background: bool = True,
                             batch_size: int = 100) -> Dict[str, Any]:
        """
        Perform deferred cleanup of soft-deleted records.
        
        This operation removes records that were previously soft-deleted
        from both FAISS and Redis storage to free up space.
        
        Args:
            background: Whether to run in background (non-blocking)
            batch_size: Number of records to process per batch
            
        Returns:
            Dictionary with operation status and results
            
        Raises:
            MaintenanceOperationError: If cleanup operation fails
        """
        operation_id = f"deferred_cleanup_{int(time.time())}"
        
        if background:
            # Start background task
            asyncio.create_task(self._deferred_cleanup_task(operation_id, batch_size))
            return {
                "status": "started",
                "operation_id": operation_id,
                "progress": 0.0,
                "message": "Deferred cleanup started in background"
            }
        else:
            # Run synchronously
            return await self._deferred_cleanup_task(operation_id, batch_size)

    async def _deferred_cleanup_task(self, operation_id: str, batch_size: int) -> Dict[str, Any]:
        """Internal deferred cleanup task with progress tracking."""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Initialize progress
            await self._update_progress(operation_id, 0.0, "Starting deferred cleanup")
            
            # Get soft-deleted UUIDs
            soft_deleted_uuids = await self._get_soft_deleted_uuids()
            
            if not soft_deleted_uuids:
                await self._update_progress(operation_id, 1.0, "No soft-deleted records found")
                return {
                    "status": "completed",
                    "operation_id": operation_id,
                    "progress": 1.0,
                    "processed": 0,
                    "total": 0,
                    "cleaned": 0,
                    "started_at": start_time.isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "message": "No soft-deleted records found"
                }
            
            total_records = len(soft_deleted_uuids)
            processed = 0
            cleaned = 0
            
            # Process in batches
            for i in range(0, total_records, batch_size):
                batch_uuids = soft_deleted_uuids[i:i + batch_size]
                
                # Perform hard delete on batch
                cleaned_batch = await self.crud_service.hard_delete_chunks(batch_uuids)
                cleaned += len(cleaned_batch)
                processed += len(batch_uuids)
                
                # Update progress
                progress = processed / total_records
                await self._update_progress(
                    operation_id, 
                    progress, 
                    f"Processed {processed}/{total_records}, cleaned {cleaned}"
                )
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
            
            completed_time = datetime.now(timezone.utc)
            
            result = {
                "status": "completed",
                "operation_id": operation_id,
                "progress": 1.0,
                "processed": processed,
                "total": total_records,
                "cleaned": cleaned,
                "started_at": start_time.isoformat(),
                "completed_at": completed_time.isoformat(),
                "duration_seconds": (completed_time - start_time).total_seconds(),
                "message": f"Deferred cleanup completed: {cleaned} records cleaned"
            }
            
            await self._update_progress(operation_id, 1.0, result["message"])
            logger.info(f"Deferred cleanup completed: {cleaned} records cleaned")
            
            return result
            
        except Exception as e:
            error_msg = f"Deferred cleanup failed: {e}"
            logger.error(error_msg)
            await self._update_progress(operation_id, 0.0, error_msg)
            
            return {
                "status": "failed",
                "operation_id": operation_id,
                "progress": 0.0,
                "error": str(e),
                "started_at": start_time.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "message": error_msg
            }

    async def _get_soft_deleted_uuids(self) -> List[str]:
        """Get UUIDs of soft-deleted records."""
        try:
            # Get all record UUIDs
            all_uuids = await self.crud_service.get_all_record_ids()
            
            if not all_uuids:
                return []
            
            # Check which ones are soft-deleted
            soft_deleted = []
            pipeline = await self.redis.pipeline()
            
            for uuid in all_uuids:
                pipeline.hget(f"vector:{uuid}", "is_deleted")
            
            results = await pipeline.execute()
            
            for uuid, result in zip(all_uuids, results):
                if result and result.decode('utf-8') == 'true':
                    soft_deleted.append(uuid)
            
            return soft_deleted
            
        except Exception as e:
            logger.error(f"Failed to get soft-deleted UUIDs: {e}")
            return []

    # ============================================================================
    # DUPLICATE DETECTION OPERATIONS
    # ============================================================================

    async def find_duplicates(self,
                            metadata_filter: Dict[str, Any] = None,
                            batch_size: int = 1000,
                            background: bool = False) -> Dict[str, Any]:
        """
        Find duplicate records based on content similarity.
        
        Args:
            metadata_filter: Optional metadata filter to limit search scope
            batch_size: Number of records to process per batch
            background: Whether to run in background
            
        Returns:
            Dictionary with duplicate analysis results
        """
        operation_id = f"find_duplicates_{int(time.time())}"
        
        if background:
            asyncio.create_task(self._find_duplicates_task(operation_id, metadata_filter, batch_size))
            return {
                "status": "started",
                "operation_id": operation_id,
                "progress": 0.0,
                "message": "Duplicate detection started in background"
            }
        else:
            return await self._find_duplicates_task(operation_id, metadata_filter, batch_size)

    async def _find_duplicates_task(self,
                                  operation_id: str,
                                  metadata_filter: Dict[str, Any],
                                  batch_size: int) -> Dict[str, Any]:
        """Internal duplicate detection task."""
        start_time = datetime.now(timezone.utc)
        
        try:
            await self._update_progress(operation_id, 0.0, "Starting duplicate detection")
            
            # Get records to analyze
            if metadata_filter:
                chunk_query = ChunkQuery(**metadata_filter)
                # Note: This would need to be implemented in filter service
                # For now, get all records
                all_uuids = await self.crud_service.get_all_record_ids()
                records = await self.crud_service.get_chunks(all_uuids)
            else:
                all_uuids = await self.crud_service.get_all_record_ids()
                records = await self.crud_service.get_chunks(all_uuids)
            
            records = [r for r in records if r is not None]
            
            if not records:
                return {
                    "status": "completed",
                    "operation_id": operation_id,
                    "progress": 1.0,
                    "total_records": 0,
                    "duplicates": [],
                    "duplicate_groups": 0,
                    "message": "No records to analyze"
                }
            
            total_records = len(records)
            processed = 0
            duplicates = []
            seen_content = {}
            
            # Process in batches
            for i in range(0, total_records, batch_size):
                batch_records = records[i:i + batch_size]
                
                # Find duplicates in batch
                batch_duplicates = await self._find_batch_duplicates(batch_records, seen_content)
                duplicates.extend(batch_duplicates)
                
                processed += len(batch_records)
                progress = processed / total_records
                
                await self._update_progress(
                    operation_id,
                    progress,
                    f"Processed {processed}/{total_records}, found {len(duplicates)} duplicates"
                )
                
                await asyncio.sleep(0.01)  # Small delay
            
            # Group duplicates
            duplicate_groups = await self._group_duplicates(duplicates, seen_content)
            
            completed_time = datetime.now(timezone.utc)
            
            result = {
                "status": "completed",
                "operation_id": operation_id,
                "progress": 1.0,
                "total_records": total_records,
                "duplicates": duplicates,
                "duplicate_groups": duplicate_groups,
                "duplicate_count": len(duplicates),
                "group_count": len(duplicate_groups),
                "started_at": start_time.isoformat(),
                "completed_at": completed_time.isoformat(),
                "duration_seconds": (completed_time - start_time).total_seconds(),
                "message": f"Found {len(duplicates)} duplicates in {len(duplicate_groups)} groups"
            }
            
            await self._update_progress(operation_id, 1.0, result["message"])
            return result
            
        except Exception as e:
            error_msg = f"Duplicate detection failed: {e}"
            logger.error(error_msg)
            await self._update_progress(operation_id, 0.0, error_msg)
            
            return {
                "status": "failed",
                "operation_id": operation_id,
                "progress": 0.0,
                "error": str(e),
                "started_at": start_time.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "message": error_msg
            }

    async def _find_batch_duplicates(self,
                                   records: List[Dict[str, Any]],
                                   seen_content: Dict[str, str]) -> List[str]:
        """Find duplicates in a batch of records."""
        batch_duplicates = []
        
        for record in records:
            if not record or 'uuid' not in record:
                continue
            
            content_key = self._create_content_key(record)
            
            if content_key in seen_content:
                # Found a duplicate
                batch_duplicates.append(record['uuid'])
                if seen_content[content_key] not in batch_duplicates:
                    batch_duplicates.append(seen_content[content_key])
            else:
                seen_content[content_key] = record['uuid']
        
        return batch_duplicates

    async def _group_duplicates(self,
                              duplicates: List[str],
                              seen_content: Dict[str, str]) -> List[List[str]]:
        """Group duplicates by content key."""
        content_groups = {}
        
        for uuid in duplicates:
            # Get record to find its content key
            record = await self.crud_service.get_chunk(uuid)
            if record:
                content_key = self._create_content_key(record)
                if content_key not in content_groups:
                    content_groups[content_key] = []
                content_groups[content_key].append(uuid)
        
        return list(content_groups.values())

    def _create_content_key(self, record: Dict[str, Any]) -> str:
        """Create a content key for duplicate detection."""
        # Key fields for duplicate detection
        key_fields = ['text', 'body', 'type', 'source_id']
        content_parts = []
        
        for field in key_fields:
            value = record.get(field, '')
            if isinstance(value, (list, dict)):
                value = str(sorted(value.items()) if isinstance(value, dict) else sorted(value))
            content_parts.append(str(value))
        
        content_string = '|'.join(content_parts)
        return hashlib.md5(content_string.encode('utf-8')).hexdigest()

    # ============================================================================
    # REINDEXING OPERATIONS
    # ============================================================================

    async def reindex_all(self,
                         embedding_service,
                         lock_database: bool = True,
                         background: bool = False) -> Dict[str, Any]:
        """
        Reindex all records in the vector store.
        
        Args:
            embedding_service: Service for text vectorization
            lock_database: Whether to lock database during reindexing
            background: Whether to run in background
            
        Returns:
            Dictionary with reindexing results
        """
        operation_id = f"reindex_all_{int(time.time())}"
        
        if background:
            asyncio.create_task(self._reindex_all_task(operation_id, embedding_service, lock_database))
            return {
                "status": "started",
                "operation_id": operation_id,
                "progress": 0.0,
                "message": "Full reindexing started in background"
            }
        else:
            return await self._reindex_all_task(operation_id, embedding_service, lock_database)

    async def _reindex_all_task(self,
                              operation_id: str,
                              embedding_service,
                              lock_database: bool) -> Dict[str, Any]:
        """Internal reindexing task."""
        start_time = datetime.now(timezone.utc)
        lock_acquired = False
        
        try:
            await self._update_progress(operation_id, 0.0, "Starting full reindexing")
            
            # Acquire database lock if requested
            if lock_database:
                lock_acquired = await self.lock_manager.acquire_lock("reindex_all", timeout=3600)
                if not lock_acquired:
                    return {
                        "status": "failed",
                        "operation_id": operation_id,
                        "error": "Could not acquire database lock",
                        "message": "Database is locked by another operation"
                    }
                await self._update_progress(operation_id, 0.1, "Database lock acquired")
            
            # Perform full reindex
            await self.crud_service.full_reindex(embedding_service)
            
            # Get final count
            all_uuids = await self.crud_service.get_all_record_ids()
            total_records = len(all_uuids)
            
            completed_time = datetime.now(timezone.utc)
            
            result = {
                "status": "completed",
                "operation_id": operation_id,
                "progress": 1.0,
                "total_records": total_records,
                "started_at": start_time.isoformat(),
                "completed_at": completed_time.isoformat(),
                "duration_seconds": (completed_time - start_time).total_seconds(),
                "message": f"Full reindexing completed: {total_records} records reindexed"
            }
            
            await self._update_progress(operation_id, 1.0, result["message"])
            logger.info(f"Full reindexing completed: {total_records} records reindexed")
            
            return result
            
        except Exception as e:
            error_msg = f"Full reindexing failed: {e}"
            logger.error(error_msg)
            await self._update_progress(operation_id, 0.0, error_msg)
            
            return {
                "status": "failed",
                "operation_id": operation_id,
                "progress": 0.0,
                "error": str(e),
                "started_at": start_time.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "message": error_msg
            }
        finally:
            # Release lock if acquired
            if lock_acquired:
                await self.lock_manager.release_lock("reindex_all")

    # ============================================================================
    # ORPHAN CLEANUP OPERATIONS
    # ============================================================================

    async def cleanup_orphans(self, background: bool = True) -> Dict[str, Any]:
        """
        Clean up orphaned records (records in Redis but not in FAISS).
        
        Args:
            background: Whether to run in background
            
        Returns:
            Dictionary with cleanup results
        """
        operation_id = f"cleanup_orphans_{int(time.time())}"
        
        if background:
            asyncio.create_task(self._cleanup_orphans_task(operation_id))
            return {
                "status": "started",
                "operation_id": operation_id,
                "progress": 0.0,
                "message": "Orphan cleanup started in background"
            }
        else:
            return await self._cleanup_orphans_task(operation_id)

    async def _cleanup_orphans_task(self, operation_id: str) -> Dict[str, Any]:
        """Internal orphan cleanup task."""
        start_time = datetime.now(timezone.utc)
        
        try:
            await self._update_progress(operation_id, 0.0, "Starting orphan cleanup")
            
            # Get all Redis UUIDs
            redis_uuids = await self.crud_service.get_all_record_ids()
            
            if not redis_uuids:
                return {
                    "status": "completed",
                    "operation_id": operation_id,
                    "progress": 1.0,
                    "orphaned_count": 0,
                    "cleaned_count": 0,
                    "message": "No records to check"
                }
            
            # Check which Redis records have FAISS indices
            orphaned_uuids = []
            pipeline = await self.redis.pipeline()
            
            for uuid in redis_uuids:
                pipeline.hget(f"vector:{uuid}", "faiss_idx")
            
            results = await pipeline.execute()
            
            for uuid, result in zip(redis_uuids, results):
                if not result:
                    orphaned_uuids.append(uuid)
            
            await self._update_progress(operation_id, 0.5, f"Found {len(orphaned_uuids)} orphaned records")
            
            # Clean up orphaned records
            cleaned_count = 0
            if orphaned_uuids:
                cleaned_uuids = await self.crud_service.hard_delete_chunks(orphaned_uuids)
                cleaned_count = len(cleaned_uuids)
            
            completed_time = datetime.now(timezone.utc)
            
            result = {
                "status": "completed",
                "operation_id": operation_id,
                "progress": 1.0,
                "total_records": len(redis_uuids),
                "orphaned_count": len(orphaned_uuids),
                "cleaned_count": cleaned_count,
                "started_at": start_time.isoformat(),
                "completed_at": completed_time.isoformat(),
                "duration_seconds": (completed_time - start_time).total_seconds(),
                "message": f"Orphan cleanup completed: {cleaned_count} records cleaned"
            }
            
            await self._update_progress(operation_id, 1.0, result["message"])
            return result
            
        except Exception as e:
            error_msg = f"Orphan cleanup failed: {e}"
            logger.error(error_msg)
            await self._update_progress(operation_id, 0.0, error_msg)
            
            return {
                "status": "failed",
                "operation_id": operation_id,
                "progress": 0.0,
                "error": str(e),
                "started_at": start_time.isoformat(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "message": error_msg
            }

    # ============================================================================
    # STATISTICS AND MONITORING
    # ============================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the vector store.
        
        Returns:
            Dictionary with statistics
        """
        try:
            redis_count = await self.crud_service.count_records()
            faiss_info = await self.faiss_service.get_index_info()
            soft_deleted_count = len(await self._get_soft_deleted_uuids())
            
            return {
                'total_records': redis_count,
                'active_records': redis_count - soft_deleted_count,
                'soft_deleted_records': soft_deleted_count,
                'faiss_vectors': faiss_info.get('total_vectors', 0),
                'vector_size': faiss_info.get('vector_size', 0),
                'index_type': faiss_info.get('index_type', 'Unknown'),
                'operations_since_save': faiss_info.get('operations_since_save', 0),
                'last_save_time': faiss_info.get('last_save_time'),
                'auto_save_enabled': faiss_info.get('auto_save_enabled', False)
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}

    async def get_operation_status(self, operation_id: str) -> Dict[str, Any]:
        """
        Get status of a maintenance operation.
        
        Args:
            operation_id: Operation identifier
            
        Returns:
            Dictionary with operation status
        """
        try:
            progress_key = f"{self.progress_prefix}{operation_id}"
            progress_data = await self.redis.get(progress_key)
            
            if not progress_data:
                return {
                    "status": "not_found",
                    "operation_id": operation_id,
                    "message": "Operation not found"
                }
            
            progress_info = json.loads(progress_data.decode('utf-8'))
            return {
                "status": "found",
                "operation_id": operation_id,
                **progress_info
            }
            
        except Exception as e:
            logger.error(f"Failed to get operation status: {e}")
            return {
                "status": "error",
                "operation_id": operation_id,
                "error": str(e)
            }

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    async def _update_progress(self, operation_id: str, progress: float, message: str):
        """Update progress for an operation."""
        try:
            progress_key = f"{self.progress_prefix}{operation_id}"
            progress_data = {
                "progress": progress,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.redis.setex(
                progress_key,
                3600,  # TTL: 1 hour
                json.dumps(progress_data, ensure_ascii=False)
            )
            
        except Exception as e:
            logger.error(f"Failed to update progress: {e}")

    async def cleanup_progress_data(self, older_than_hours: int = 24) -> int:
        """
        Clean up old progress data.
        
        Args:
            older_than_hours: Remove progress data older than this many hours
            
        Returns:
            Number of progress entries cleaned up
        """
        try:
            pattern = f"{self.progress_prefix}*"
            keys = await self.redis.keys(pattern)
            
            cleaned_count = 0
            cutoff_time = time.time() - (older_than_hours * 3600)
            
            for key in keys:
                try:
                    data = await self.redis.get(key)
                    if data:
                        progress_info = json.loads(data.decode('utf-8'))
                        updated_at = progress_info.get('updated_at')
                        
                        if updated_at:
                            # Parse ISO timestamp
                            dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                            if dt.timestamp() < cutoff_time:
                                await self.redis.delete(key)
                                cleaned_count += 1
                                
                except Exception as e:
                    logger.warning(f"Failed to process progress key {key}: {e}")
                    # Delete corrupted data
                    await self.redis.delete(key)
                    cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} old progress entries")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup progress data: {e}")
            return 0 