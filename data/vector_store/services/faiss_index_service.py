"""
FAISS Index Service

This module provides the FaissIndexService class, which is a high-performance vector indexing
service built on top of Facebook AI Similarity Search (FAISS). It handles vector storage,
similarity search, and index management for large-scale vector operations.

Core Features:
- Vector addition, deletion, and similarity search operations
- Automatic index persistence and backup management
- Concurrent operation support with async locks
- Vector validation and normalization
- Performance metrics tracking
- Index reconstruction and recovery capabilities

Storage Architecture:
- FAISS IndexFlatL2 with IndexIDMap for deletion support
- In-memory vector storage for reconstruction
- Disk-based index persistence with auto-save
- Backup creation with atomic operations

Performance Optimizations:
- Async locks for write operations (add/delete)
- Separate locks for backup and index access
- Batch operations with configurable auto-save
- Non-blocking search during backup operations

Error Handling:
- Comprehensive exception classification
- Vector validation with detailed error messages
- Graceful handling of FAISS-specific errors
- Recovery mechanisms for corrupted indices

Integration:
- Works with numpy arrays for vector operations
- Supports distributed architecture patterns
- Integrates with Redis metadata storage via UUID mapping
- Provides metrics for monitoring and optimization

Usage:
    service = FaissIndexService(index_path="/path/to/index", vector_size=384)
    indices = await service.add_vectors([vector1, vector2])
    results = await service.search_vectors([query_vector], limit=10)
    await service.delete_vectors([index1, index2])
"""

import os
import logging
import tempfile
import faiss
import numpy as np
from typing import List, Optional, Tuple, Union
import time
import asyncio
import copy
from vector_store.exceptions import (
    FaissError, FaissVectorError, FaissIndexError, FaissSearchError, FaissStorageError,
    FaissBatchOperationError, ServiceInitializationError, create_vector_size_error, 
    create_search_limit_error, create_faiss_batch_operation_error
)
from .faiss_wal_service import FaissWALService

logger = logging.getLogger("vector_store.faiss")

class FaissIndexService:
    """
    Simple FAISS driver for distributed architecture.

    Core responsibilities:
    - Basic vector operations (add/delete/search)
    - Index persistence to disk
    - Vector validation
    - Minimal metrics tracking

    All complex logic (replication, backup, size management) handled by upper layers.
    """

    def __init__(self, index_path: str = None, vector_size: int = 384,
                 auto_save: bool = True, save_batch_size: int = 100):
        """
        Initialize FAISS index service as simple driver.

        Args:
            index_path: Path to FAISS index file
            vector_size: Vector dimension
            auto_save: Enable automatic saving
            save_batch_size: Operations before auto-save
            
        Raises:
            FaissIndexError: If index initialization fails
            FaissStorageError: If index loading fails
        """
        logger.info(f"FaissIndexService.__init__ called with index_path={index_path}, vector_size={vector_size}, auto_save={auto_save}, save_batch_size={save_batch_size}")
        
        try:
            self.index_path = index_path
            self.vector_size = vector_size
            self.auto_save = auto_save
            self.save_batch_size = save_batch_size

            # Async locks for operations
            logger.info("FaissIndexService.__init__: creating async locks...")
            self.write_lock = asyncio.Lock()  # For write operations (add/delete)
            self.backup_lock = asyncio.Lock()  # For backup operations
            self.index_lock = asyncio.Lock()   # For direct index access
            logger.info("FaissIndexService.__init__: async locks created")

            # Simple operation tracking
            self.operations_since_save = 0

            # Store vectors separately for reconstruct support
            self.vectors = []

            # Basic metrics
            self.metrics = {
                'add_operations': 0,
                'search_operations': 0,
                'delete_operations': 0,
                'total_vectors': 0,
                'last_save_time': None,
                'backup_operations': 0,
                'backup_duration_avg': 0.0,
                'last_backup_time': None
            }
            logger.info("FaissIndexService.__init__: metrics initialized")

            # Initialize WAL service
            log_dir = os.path.join(os.path.dirname(index_path) if index_path else "data1", "logs")
            self.wal_service = FaissWALService(log_dir=log_dir)
            logger.info("FaissIndexService.__init__: WAL service initialized")

            logger.info("FaissIndexService.__init__: calling _init_index...")
            self._init_index()
            
            logger.info(f"FAISS driver initialized. Vector size: {vector_size}, Path: {index_path}")
        except Exception as e:
            logger.error(f"Failed to initialize FAISS service: {e}")
            raise FaissIndexError(f"Service initialization failed: {e}", "init")

    async def initialize_with_wal(self) -> int:
        """
        Initialize FAISS service with WAL replay.
        
        Returns:
            Number of operations replayed from WAL
        """
        try:
            logger.info("FaissIndexService: replaying WAL logs...")
            operations_replayed = await self.wal_service.replay_logs(self)
            logger.info(f"FaissIndexService: replayed {operations_replayed} operations from WAL")
            return operations_replayed
        except Exception as e:
            logger.error(f"Failed to replay WAL logs: {e}")
            raise FaissIndexError(f"WAL replay failed: {e}", "initialize_with_wal")

    def _init_index(self):
        """Initialize FAISS index with IndexIDMap for deletion support"""
        logger.info("_init_index: starting index initialization")
        try:
            if self.index_path and os.path.exists(self.index_path):
                logger.info(f"_init_index: index file exists at {self.index_path}, attempting to load...")
                try:
                    logger.info("_init_index: calling faiss.read_index...")
                    loaded_index = faiss.read_index(self.index_path)
                    logger.info("_init_index: faiss.read_index completed successfully")

                    # Ensure IndexIDMap for deletion support
                    if hasattr(loaded_index, 'remove_ids'):
                        logger.info("_init_index: loaded index already has remove_ids, using as-is")
                        self.index = loaded_index
                    else:
                        logger.info("_init_index: loaded index doesn't have remove_ids, wrapping in IndexIDMap")
                        self.index = faiss.IndexIDMap(loaded_index)

                    self.metrics['total_vectors'] = self.index.ntotal
                    # Note: vectors array will be empty on load, reconstruct won't work for loaded indices
                    logger.info(f"Loaded FAISS index: {self.index_path}, vectors: {self.index.ntotal}")

                except Exception as e:
                    logger.warning(f"Failed to load index: {e}, creating new")
                    self._create_new_index()
            else:
                logger.info(f"_init_index: no existing index file, creating new index")
                self._create_new_index()
        except Exception as e:
            logger.error(f"Failed to initialize index: {e}")
            raise FaissIndexError(f"Index initialization failed: {e}", "_init_index")

    def _create_new_index(self):
        """Create new FAISS index"""
        try:
            # Create base index and wrap it with IndexIDMap for deletion support
            base_index = faiss.IndexFlatL2(self.vector_size)
            self.index = faiss.IndexIDMap(base_index)
            self.vectors = []  # Reset vectors array
            logger.info("Created new FAISS index")
        except Exception as e:
            logger.error(f"Failed to create new index: {e}")
            raise FaissIndexError(f"Failed to create new index: {e}", "_create_new_index")

    def _validate_vectors(self, vectors: List[np.ndarray], operation: str = "operation") -> np.ndarray:
        """
        Validate and normalize vectors.

        Args:
            vectors: List of input vectors
            operation: Operation name for error messages

        Returns:
            Normalized numpy array

        Raises:
            FaissVectorError: If any vector is invalid
        """
        if not vectors:
            return np.array([], dtype=np.float32).reshape(0, self.vector_size)

        validated_vectors = []
        for i, vector in enumerate(vectors):
            if not isinstance(vector, np.ndarray):
                vector = np.array(vector, dtype=np.float32)

            if vector.shape[-1] != self.vector_size:
                raise create_vector_size_error(
                    operation=operation,
                    vector_index=i,
                    expected_size=self.vector_size,
                    actual_size=vector.shape[-1]
                )

            validated_vectors.append(vector.astype(np.float32))

        return np.array(validated_vectors, dtype=np.float32)

    # ============================================================================
    # CORE OPERATIONS - ALL WORK WITH LISTS
    # ============================================================================

    async def add_vectors(self, vectors: List[np.ndarray]) -> List[int]:
        """
        Add multiple vectors to index.

        Args:
            vectors: List of vectors to add

        Returns:
            List of internal indices of added vectors

        Raises:
            FaissVectorError: If any vector is invalid
            FaissIndexError: If index operation fails
            FaissBatchOperationError: If batch operation fails partially
        """
        logger.info(f"add_vectors called with {len(vectors)} vectors")
        
        if not vectors:
            logger.info("add_vectors: empty vectors list, returning empty result")
            return []

        successful_indices = []
        failed_indices = []
        
        try:
            logger.info("add_vectors: acquiring write_lock...")
            # Use write lock to prevent concurrent modifications during backup
            async with self.write_lock:
                logger.info("add_vectors: write_lock acquired, starting vector processing...")
                try:
                    logger.info("add_vectors: validating vectors...")
                    vectors_array = self._validate_vectors(vectors, "add_vectors")
                    batch_size = len(vectors)
                    logger.info(f"add_vectors: validated {batch_size} vectors")

                    # Generate sequential IDs
                    start_idx = self.index.ntotal
                    ids = np.arange(start_idx, start_idx + batch_size)
                    logger.info(f"add_vectors: generated IDs from {start_idx} to {start_idx + batch_size - 1}")

                    # Add vectors
                    try:
                        logger.info("add_vectors: calling FAISS add_with_ids...")
                        # Check if index supports add_with_ids operation
                        if hasattr(self.index, 'add_with_ids') and callable(getattr(self.index, 'add_with_ids')):
                            self.index.add_with_ids(vectors_array, ids)
                            logger.info("add_vectors: FAISS add_with_ids completed successfully")
                        else:
                            # Fallback: use regular add operation
                            logger.warning("add_vectors: Index does not support add_with_ids, using regular add")
                            self.index.add(vectors_array)
                            logger.info("add_vectors: FAISS add completed successfully")
                    except Exception as e:
                        logger.error(f"add_vectors: FAISS add_with_ids failed: {e}")
                        raise FaissIndexError(f"FAISS add_with_ids failed: {e}", "add_vectors")

                    # Store vectors for reconstruct support
                    logger.info("add_vectors: storing vectors for reconstruct support...")
                    for i, vector in enumerate(vectors_array):
                        if len(self.vectors) <= ids[i]:
                            self.vectors.extend([None] * (ids[i] - len(self.vectors) + 1))
                        self.vectors[ids[i]] = vector.copy()

                    # Update metrics
                    self.metrics['add_operations'] += batch_size
                    self.metrics['total_vectors'] = self.index.ntotal
                    self.operations_since_save += batch_size
                    logger.info(f"add_vectors: updated metrics - total_vectors: {self.index.ntotal}, operations_since_save: {self.operations_since_save}")

                    logger.info(f"Added {batch_size} vectors, total: {self.index.ntotal}")

                    # Auto-save if needed (async, doesn't block writes)
                    if self.auto_save and self.operations_since_save >= self.save_batch_size:
                        logger.info(f"add_vectors: triggering auto-save (operations_since_save: {self.operations_since_save}, save_batch_size: {self.save_batch_size})")
                        asyncio.create_task(self._save_index())

                    successful_indices = ids.tolist()
                    logger.info(f"add_vectors: returning {len(successful_indices)} successful indices")
                    
                    # Log operation to WAL
                    try:
                        await self.wal_service.log_add_vectors(vectors, successful_indices)
                        logger.debug(f"add_vectors: logged {len(successful_indices)} vectors to WAL")
                    except Exception as e:
                        logger.error(f"add_vectors: failed to log to WAL: {e}")
                        # Don't fail the operation if WAL logging fails
                    
                    return successful_indices

                except FaissVectorError:
                    logger.error("add_vectors: FaissVectorError occurred")
                    # Re-raise validation errors
                    raise
                except FaissIndexError:
                    logger.error("add_vectors: FaissIndexError occurred")
                    # Re-raise index errors
                    raise
                except Exception as e:
                    # Handle unexpected errors
                    logger.error(f"Unexpected error in add_vectors: {e}")
                    raise FaissIndexError(f"Vector addition failed: {e}", "add_vectors")

        except FaissVectorError:
            logger.error("add_vectors: FaissVectorError in outer catch")
            # Re-raise validation errors
            raise
        except FaissIndexError:
            logger.error("add_vectors: FaissIndexError in outer catch")
            # Re-raise index errors
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in add_vectors outer catch: {e}")
            if successful_indices or failed_indices:
                raise create_faiss_batch_operation_error("add_vectors", successful_indices, failed_indices, e)
            else:
                raise FaissIndexError(f"Vector addition failed: {e}", "add_vectors")

    async def search_vectors(self, vectors: List[np.ndarray], limit: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Search for nearest vectors using multiple query vectors.

        Args:
            vectors: List of query vectors
            limit: Maximum number of results per query

        Returns:
            List of (distances, indices) for each query

        Raises:
            FaissVectorError: If any vector is invalid
            FaissSearchError: If search operation fails
        """
        if not vectors:
            return []

        if limit <= 0:
            raise create_search_limit_error("search_vectors", limit)

        try:
            vectors_array = self._validate_vectors(vectors, "search_vectors")
            batch_size = len(vectors)

            # Check if backup is in progress (non-blocking check)
            if self.backup_lock.locked():
                logger.info("Search operation during backup - proceeding with current index state")

            # Search (no lock needed for read operations, but we ensure index consistency)
            async with self.index_lock:
                try:
                    distances, indices = self.index.search(vectors_array, limit)
                except Exception as e:
                    logger.error(f"FAISS search error: {e}")
                    raise FaissSearchError(f"Search operation failed: {e}", "search_vectors")

            # Update metrics
            self.metrics['search_operations'] += batch_size

            # Convert to list of tuples
            results = [(distances[i], indices[i]) for i in range(batch_size)]
            return results

        except FaissVectorError:
            # Re-raise validation errors
            raise
        except FaissSearchError:
            # Re-raise search errors
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in search_vectors: {e}")
            raise FaissSearchError(f"Search operation failed: {e}", "search_vectors")

    async def delete_vectors(self, indices: List[int]) -> int:
        """
        Remove multiple vectors from index.

        Args:
            indices: List of indices to remove

        Returns:
            Number of successfully deleted vectors

        Raises:
            FaissIndexError: If index operation fails
        """
        if not indices:
            return 0

        try:
            # Use write lock to prevent concurrent modifications during backup
            async with self.write_lock:
                try:
                    # Filter valid indices
                    valid_indices = [idx for idx in indices if 0 <= idx < self.index.ntotal]
                    invalid_indices = [idx for idx in indices if idx < 0 or idx >= self.index.ntotal]
                    invalid_count = len(indices) - len(valid_indices)

                    if invalid_count > 0:
                        logger.warning(f"{invalid_count} invalid indices ignored: {invalid_indices}")
                        logger.warning(f"FAISS index size: {self.index.ntotal}, valid range: 0-{self.index.ntotal-1}")

                    if not valid_indices:
                        logger.warning("No valid indices to delete")
                        return 0

                    # Delete vectors
                    try:
                        self.index.remove_ids(np.array(valid_indices))
                    except Exception as e:
                        raise FaissIndexError(f"FAISS remove_ids failed: {e}", "delete_vectors")

                    deleted_count = len(valid_indices)
                    self.metrics['delete_operations'] += deleted_count
                    self.metrics['total_vectors'] = self.index.ntotal
                    self.operations_since_save += deleted_count

                    logger.info(f"Deleted {deleted_count} vectors, total: {self.index.ntotal}")

                    # Log operation to WAL
                    try:
                        await self.wal_service.log_delete_vectors(valid_indices)
                        logger.debug(f"delete_vectors: logged {deleted_count} deletions to WAL")
                    except Exception as e:
                        logger.error(f"delete_vectors: failed to log to WAL: {e}")
                        # Don't fail the operation if WAL logging fails

                    # Auto-save if needed (async, doesn't block writes)
                    if self.auto_save and self.operations_since_save >= self.save_batch_size:
                        asyncio.create_task(self._save_index())

                    return deleted_count

                except FaissIndexError:
                    # Re-raise index errors
                    raise
                except Exception as e:
                    # Handle unexpected errors
                    logger.error(f"Unexpected error in delete_vectors: {e}")
                    raise FaissIndexError(f"Vector deletion failed: {e}", "delete_vectors")

        except FaissIndexError:
            # Re-raise index errors
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in delete_vectors: {e}")
            raise FaissIndexError(f"Vector deletion failed: {e}", "delete_vectors")

    # ============================================================================
    # CONVENIENCE WRAPPERS FOR SINGLE VECTOR OPERATIONS
    # ============================================================================

    async def add_vector(self, vector: np.ndarray) -> int:
        """
        Add single vector (wrapper around add_vectors).

        Args:
            vector: Vector to add

        Returns:
            Internal index of added vector, or -1 if failed

        Raises:
            FaissVectorError: If vector is invalid
            FaissIndexError: If index operation fails
        """
        try:
            indices = await self.add_vectors([vector])
            return indices[0] if indices else -1
        except (FaissVectorError, FaissIndexError):
            # Re-raise specific exceptions
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in add_vector: {e}")
            raise FaissIndexError(f"Single vector addition failed: {e}", "add_vector")

    async def search_vector(self, vector: np.ndarray, limit: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search with single vector (wrapper around search_vectors).

        Args:
            vector: Query vector
            limit: Maximum number of results

        Returns:
            Tuple of (distances, indices)

        Raises:
            FaissVectorError: If vector is invalid
            FaissSearchError: If search operation fails
        """
        try:
            results = await self.search_vectors([vector], limit)
            return results[0] if results else (np.array([]), np.array([]))
        except (FaissVectorError, FaissSearchError):
            # Re-raise specific exceptions
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in search_vector: {e}")
            raise FaissSearchError(f"Single vector search failed: {e}", "search_vector")

    async def search(self, vector: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Search with single vector (returns distances and indices).

        Args:
            vector: Query vector
            k: Maximum number of results

        Returns:
            Tuple of (distances, indices) for the query

        Raises:
            FaissVectorError: If vector is invalid
            FaissSearchError: If search operation fails
        """
        try:
            distances, indices = await self.search_vector(vector, k)
            return distances, indices
        except (FaissVectorError, FaissSearchError):
            # Re-raise specific exceptions
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in search: {e}")
            raise FaissSearchError(f"Search operation failed: {e}", "search")

    async def delete_vector(self, idx: int) -> bool:
        """
        Delete single vector (wrapper around delete_vectors).

        Args:
            idx: Index of vector to delete

        Returns:
            True if successfully deleted, False otherwise

        Raises:
            FaissIndexError: If index operation fails
        """
        try:
            deleted_count = await self.delete_vectors([idx])
            return deleted_count > 0
        except FaissIndexError:
            # Re-raise specific exceptions
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in delete_vector: {e}")
            raise FaissIndexError(f"Single vector deletion failed: {e}", "delete_vector")

    # ============================================================================
    # ASYNC BACKUP STRATEGY WITH IN-MEMORY COPYING
    # ============================================================================

    async def create_backup_async(self, backup_path: str) -> None:
        """
        Create backup using async strategy:
        1. Block write operations
        2. Create in-memory copy
        3. Unblock write operations
        4. Save copy to disk asynchronously

        Args:
            backup_path: Path for backup file
            
        Raises:
            FaissStorageError: If backup operation fails
        """
        start_time = time.time()

        try:
            # Step 1: Block write operations AND backup operations
            async with self.write_lock, self.backup_lock:
                logger.info("Creating in-memory copy of index for backup")

                # Step 2: Create in-memory copy (with proper locking)
                index_copy = await self._create_index_copy()

                # Step 3: Unblock write operations (locks released here)
                logger.info("In-memory copy created, write operations unblocked")

            # Step 4: Save copy to disk asynchronously (outside of locks)
            await self._save_index_copy_to_disk(index_copy, backup_path)

            # Update metrics
            duration = time.time() - start_time
            self.metrics['backup_operations'] += 1
            self.metrics['backup_duration_avg'] = (
                (self.metrics['backup_duration_avg'] * (self.metrics['backup_operations'] - 1) + duration) /
                self.metrics['backup_operations']
            )
            self.metrics['last_backup_time'] = time.time()

            logger.info(f"Backup completed: {backup_path}, duration: {duration:.3f}s, vectors: {index_copy.ntotal}")

        except FaissStorageError:
            # Re-raise storage errors
            raise
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            raise FaissStorageError(f"Backup failed: {e}", "create_backup_async", backup_path)

    async def _create_index_copy(self):
        """
        Create a deep copy of the current index in memory.
        This method is called within write_lock context to ensure index consistency.

        Returns:
            Copy of the FAISS index
            
        Raises:
            FaissStorageError: If index copy creation fails
        """
        try:
            # Create a temporary file for the copy
            with tempfile.NamedTemporaryFile(suffix='.faiss', delete=False) as tmp_file:
                temp_path = tmp_file.name

            # Save current index to temp file (index is locked by caller)
            faiss.write_index(self.index, temp_path)

            # Load copy from temp file
            index_copy = faiss.read_index(temp_path)

            # Clean up temp file
            os.unlink(temp_path)

            return index_copy

        except Exception as e:
            logger.error(f"Failed to create index copy: {e}")
            raise FaissStorageError(f"Index copy creation failed: {e}", "_create_index_copy")

    async def _save_index_copy_to_disk(self, index_copy, backup_path: str) -> None:
        """
        Save index copy to disk asynchronously.

        Args:
            index_copy: FAISS index copy to save
            backup_path: Path where to save the backup
            
        Raises:
            FaissStorageError: If backup save fails
        """
        try:
            # Use asyncio to run the blocking operation in a thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, faiss.write_index, index_copy, backup_path)

        except Exception as e:
            logger.error(f"Failed to save index copy to disk: {e}")
            raise FaissStorageError(f"Backup save failed: {e}", "_save_index_copy_to_disk", backup_path)

    # ============================================================================
    # PERSISTENCE OPERATIONS
    # ============================================================================

    async def save_index(self, path: str = None) -> None:
        """
        Save index to file.

        Args:
            path: Optional custom path, uses self.index_path if None
            
        Raises:
            FaissStorageError: If index save fails
        """
        save_path = path or self.index_path
        if not save_path:
            logger.warning("No index path specified for saving")
            return

        try:
            # Use index lock instead of write lock to avoid deadlock
            async with self.index_lock:
                faiss.write_index(self.index, save_path)
                self.metrics['last_save_time'] = time.time()
                self.operations_since_save = 0

            logger.info(f"Saved index to: {save_path}, vectors: {self.index.ntotal}")

        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            raise FaissStorageError(f"Index save failed: {e}", "save_index", save_path)

    async def load_index(self, path: str = None) -> None:
        """
        Load index from file.

        Args:
            path: Optional custom path, uses self.index_path if None
            
        Raises:
            FaissStorageError: If index load fails
        """
        load_path = path or self.index_path
        if not load_path or not os.path.exists(load_path):
            logger.warning(f"Index file not found: {load_path}")
            return

        try:
            loaded_index = faiss.read_index(load_path)

            # Ensure IndexIDMap
            if hasattr(loaded_index, 'remove_ids'):
                self.index = loaded_index
            else:
                self.index = faiss.IndexIDMap(loaded_index)

            self.metrics['total_vectors'] = self.index.ntotal
            self.operations_since_save = 0

            logger.info(f"Loaded index from: {load_path}, vectors: {self.index.ntotal}")

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            raise FaissStorageError(f"Index load failed: {e}", "load_index", load_path)

    async def _save_index(self) -> None:
        """Internal save method for auto-save"""
        await self.save_index()

    # ============================================================================
    # UTILITY OPERATIONS
    # ============================================================================

    def get_vector_by_index(self, idx: int) -> Optional[np.ndarray]:
        """
        Get vector by index.
        
        Args:
            idx: Vector index
            
        Returns:
            Vector as numpy array or None if not found
            
        Raises:
            FaissIndexError: If index is invalid
        """
        try:
            if idx < 0 or idx >= self.index.ntotal:
                return None
                
            # Check if index supports reconstruct operation
            if hasattr(self.index, 'reconstruct') and callable(getattr(self.index, 'reconstruct')):
                # Get vector from FAISS index using reconstruct
                vector = self.index.reconstruct(idx)
                return vector.astype(np.float32)
            else:
                # Fallback: try to get vector from in-memory storage if available
                if hasattr(self, 'vectors') and self.vectors and idx < len(self.vectors):
                    return self.vectors[idx].astype(np.float32)
                else:
                    logger.warning(f"Index does not support reconstruct operation and no in-memory vectors available for index {idx}")
                    return None
                
        except Exception as e:
            logger.error(f"Failed to get vector by index {idx}: {e}")
            # Don't raise exception, just return None for unsupported operations
            return None


    async def count(self) -> int:
        """Return number of vectors in FAISS index."""
        return self.index.ntotal

    async def clear_index(self) -> None:
        """
        Clear all vectors (for testing)
        
        Raises:
            FaissIndexError: If index clearing fails
            FaissStorageError: If auto-save after clearing fails
        """
        logger.info(f"Clearing index, previous size: {self.index.ntotal}")

        try:
            async with self.write_lock:
                self._create_new_index()
                self.operations_since_save = 0
                self.metrics['total_vectors'] = 0

            # Log operation to WAL
            try:
                await self.wal_service.log_clear_index()
                logger.debug("clear_index: logged clear operation to WAL")
            except Exception as e:
                logger.error(f"clear_index: failed to log to WAL: {e}")
                # Don't fail the operation if WAL logging fails

            # Save without write lock to avoid deadlock
            if self.index_path:
                await self._save_index()

            logger.info("Index cleared")
        except (FaissIndexError, FaissStorageError):
            # Re-raise specific errors
            raise
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            raise FaissIndexError(f"Index clearing failed: {e}", "clear_index")

    async def force_save(self) -> None:
        """
        Force save regardless of batch settings
        
        Raises:
            FaissStorageError: If save operation fails
        """
        if self.operations_since_save > 0:
            await self._save_index()

    def get_metrics(self) -> dict:
        """Get current metrics"""
        return self.metrics.copy()

    def reset_metrics(self) -> None:
        """Reset metrics"""
        self.metrics = {
            'add_operations': 0,
            'search_operations': 0,
            'delete_operations': 0,
            'total_vectors': self.index.ntotal,
            'last_save_time': self.metrics.get('last_save_time'),
            'backup_operations': 0,
            'backup_duration_avg': 0.0,
            'last_backup_time': self.metrics.get('last_backup_time')
        }
        logger.info("Metrics reset")

    # ============================================================================
    # BACKUP/REPLICATION SUPPORT METHODS
    # ============================================================================

    async def create_backup(self, backup_path: str) -> None:
        """
        Create backup of current index (legacy method, use create_backup_async for better performance).

        Args:
            backup_path: Path for backup file
            
        Raises:
            FaissStorageError: If backup operation fails
        """
        await self.create_backup_async(backup_path)

    async def restore_from_backup(self, backup_path: str) -> None:
        """
        Restore index from backup.

        Args:
            backup_path: Path to backup file
            
        Raises:
            FaissStorageError: If backup file not found or restore fails
        """
        if not os.path.exists(backup_path):
            raise FaissStorageError(f"Backup file not found: {backup_path}", "restore_from_backup", backup_path)

        try:
            loaded_index = faiss.read_index(backup_path)

            # Ensure IndexIDMap
            if hasattr(loaded_index, 'remove_ids'):
                self.index = loaded_index
            else:
                self.index = faiss.IndexIDMap(loaded_index)

            self.metrics['total_vectors'] = self.index.ntotal
            self.operations_since_save = 0

            # Note: vectors array cannot be restored from backup file
            # It will be empty and reconstruct won't work for restored indices
            self.vectors = []

            logger.info(f"Restored from backup: {backup_path}, vectors: {self.index.ntotal}")

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            raise FaissStorageError(f"Restore failed: {e}", "restore_from_backup", backup_path)

    async def get_index_info(self) -> dict:
        """
        Get basic index information for monitoring.

        Returns:
            Dictionary with index information
        """
        return {
            'total_vectors': self.index.ntotal,
            'vector_size': self.vector_size,
            'index_type': type(self.index).__name__,
            'operations_since_save': self.operations_since_save,
            'auto_save_enabled': self.auto_save,
            'save_batch_size': self.save_batch_size,
            'backup_operations': self.metrics.get('backup_operations', 0),
            'backup_duration_avg': self.metrics.get('backup_duration_avg', 0.0),
            'last_backup_time': self.metrics.get('last_backup_time')
        }

    def is_backup_in_progress(self) -> bool:
        """
        Check if backup operation is currently in progress.

        Returns:
            True if backup is in progress, False otherwise
        """
        return self.backup_lock.locked()

    # ============================================================================
    # ADDITIONAL ASYNC UTILITY METHODS FOR ENHANCED COVERAGE
    # ============================================================================

    async def get_vector(self, uuid: int) -> np.ndarray:
        """
        Get vector by UUID (alias for get_vector_by_index).

        Args:
            uuid: Vector UUID/index

        Returns:
            Vector as numpy array

        Raises:
            ValueError: If UUID is invalid
            FaissSearchError: If vector retrieval fails
        """
        if uuid < 0:
            raise ValueError("Invalid UUID: must be non-negative")
        
        try:
            result = self.get_vector_by_index(uuid)
            if result is None:
                raise FaissSearchError("Vector retrieval failed: vector not found", "get_vector")
            return result
        except Exception as e:
            if isinstance(e, FaissSearchError):
                raise
            raise FaissSearchError(f"Vector retrieval failed: {e}", "get_vector")

    async def get_vectors(self, uuids: List[int]) -> np.ndarray:
        """
        Get multiple vectors by UUIDs.

        Args:
            uuids: List of vector UUIDs

        Returns:
            Array of vectors as numpy array

        Raises:
            ValueError: If any UUID is invalid
            FaissSearchError: If vector retrieval fails
        """
        if not uuids:
            return np.array([], dtype=np.float32).reshape(0, self.vector_size)

        # Validate UUIDs
        for uuid in uuids:
            if uuid < 0:
                raise ValueError(f"Invalid UUID: {uuid} must be non-negative")

        try:
            # Use FAISS reconstruct_n for batch retrieval
            vectors = self.index.reconstruct_n(np.array(uuids))
            return vectors.astype(np.float32)
        except Exception as e:
            raise FaissSearchError(f"Batch vector retrieval failed: {e}", "get_vectors")

    async def get_total_vectors(self) -> int:
        """
        Get total number of vectors in index.

        Returns:
            Total vector count
        """
        return self.index.ntotal

    async def get_vector_size(self) -> int:
        """
        Get vector dimension size.

        Returns:
            Vector dimension
        """
        return self.vector_size

    async def get_index_stats(self) -> dict:
        """
        Get index statistics.

        Returns:
            Dictionary with index statistics
        """
        return {
            'total_vectors': self.index.ntotal,
            'vector_size': self.vector_size,
            'index_type': type(self.index).__name__,
            'operations_since_save': self.operations_since_save,
            'auto_save_enabled': self.auto_save,
            'save_batch_size': self.save_batch_size
        }

    async def is_empty(self) -> bool:
        """
        Check if index is empty.

        Returns:
            True if index is empty, False otherwise
        """
        return self.index.ntotal == 0

    async def get_index_type(self) -> str:
        """
        Get index type name.

        Returns:
            Index type as string
        """
        return type(self.index).__name__

    async def optimize_index(self) -> bool:
        """
        Optimize index for better performance.

        Returns:
            True if successful

        Raises:
            FaissSearchError: If optimization fails
        """
        try:
            # Make direct map for faster access
            self.index.make_direct_map()
            return True
        except Exception as e:
            raise FaissSearchError(f"Index optimization failed: {e}", "optimize_index")

    async def get_memory_usage(self) -> int:
        """
        Get estimated memory usage in bytes.

        Returns:
            Memory usage in bytes
        """
        # Rough estimation: vectors * vector_size * 4 bytes (float32)
        return self.index.ntotal * self.vector_size * 4

    async def search_vectors_batch(self, query_vectors: np.ndarray, k: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Search for nearest vectors using batch query vectors.

        Args:
            query_vectors: Array of query vectors
            k: Maximum number of results per query

        Returns:
            List of (distances, indices) for each query

        Raises:
            ValueError: If vectors have invalid shape
            FaissSearchError: If search operation fails
        """
        if query_vectors.shape[-1] != self.vector_size:
            raise ValueError(f"Invalid vector shape: expected {self.vector_size}, got {query_vectors.shape[-1]}")

        try:
            distances, indices = self.index.search(query_vectors, k)
            # FAISS returns (n_queries, k) arrays, so we need to transpose the results
            # Each query gets its own (distances, indices) tuple
            return [(distances[i], indices[i]) for i in range(distances.shape[0])]
        except Exception as e:
            raise FaissSearchError(f"Batch search failed: {e}", "search_vectors_batch")

    async def add_vectors_with_ids(self, vectors: np.ndarray, ids: List[int]) -> bool:
        """
        Add vectors with specific IDs.

        Args:
            vectors: Array of vectors to add
            ids: List of IDs for vectors

        Returns:
            True if successful

        Raises:
            ValueError: If vectors and IDs have different lengths
            FaissSearchError: If addition fails
        """
        if len(vectors) != len(ids):
            raise ValueError(f"Vectors and IDs must have same length: {len(vectors)} vs {len(ids)}")

        try:
            self.index.add_with_ids(vectors, np.array(ids))
            return True
        except Exception as e:
            raise FaissSearchError(f"Vector addition with IDs failed: {e}", "add_vectors_with_ids")

    async def search_vector_with_ids(self, query_vector: np.ndarray, k: int) -> Tuple[List[int], List[float]]:
        """
        Search for nearest vectors and return IDs and scores.

        Args:
            query_vector: Query vector
            k: Maximum number of results

        Returns:
            Tuple of (ids, scores)

        Raises:
            ValueError: If vector has invalid shape
            FaissSearchError: If search operation fails
        """
        if query_vector.shape[-1] != self.vector_size:
            raise ValueError(f"Invalid vector shape: expected {self.vector_size}, got {query_vector.shape[-1]}")

        try:
            distances, indices = self.index.search(query_vector.reshape(1, -1), k)
            return indices[0].tolist(), distances[0].tolist()
        except Exception as e:
            raise FaissSearchError(f"Vector search with IDs failed: {e}", "search_vector_with_ids")

    async def get_vector_by_id(self, vector_id: int) -> np.ndarray:
        """
        Get vector by ID.

        Args:
            vector_id: Vector ID

        Returns:
            Vector as numpy array

        Raises:
            ValueError: If ID is invalid
            FaissSearchError: If vector retrieval fails
        """
        if vector_id < 0:
            raise ValueError("Invalid vector ID: must be non-negative")

        try:
            vector = self.index.reconstruct(vector_id)
            return vector.astype(np.float32)
        except Exception as e:
            raise FaissSearchError(f"Vector retrieval by ID failed: {e}", "get_vector_by_id")

    async def remove_vector_by_id(self, vector_id: int) -> bool:
        """
        Remove vector by ID.

        Args:
            vector_id: Vector ID to remove

        Returns:
            True if successful

        Raises:
            ValueError: If ID is invalid
            FaissSearchError: If removal fails
        """
        if vector_id < 0:
            raise ValueError("Invalid vector ID: must be non-negative")

        try:
            self.index.remove_ids(np.array([vector_id]))
            return True
        except Exception as e:
            raise FaissSearchError(f"Vector removal by ID failed: {e}", "remove_vector_by_id")

    async def update_vector(self, vector_id: int, new_vector: np.ndarray) -> bool:
        """
        Update vector by ID (remove old, add new).

        Args:
            vector_id: Vector ID to update
            new_vector: New vector data

        Returns:
            True if successful

        Raises:
            ValueError: If ID is invalid or vector has wrong shape
            FaissSearchError: If update fails
        """
        if vector_id < 0:
            raise ValueError("Invalid vector ID: must be non-negative")

        if new_vector.shape[-1] != self.vector_size:
            raise ValueError(f"Invalid vector shape: expected {self.vector_size}, got {new_vector.shape[-1]}")

        try:
            # Remove old vector
            self.index.remove_ids(np.array([vector_id]))
            # Add new vector with same ID
            self.index.add_with_ids(new_vector.reshape(1, -1), np.array([vector_id]))
            return True
        except Exception as e:
            raise FaissSearchError(f"Vector update failed: {e}", "update_vector")

    async def get_nearest_neighbors(self, query_vector: np.ndarray, k: int) -> List[Tuple[int, float]]:
        """
        Get nearest neighbors with distances.

        Args:
            query_vector: Query vector
            k: Number of neighbors to return

        Returns:
            List of (id, distance) tuples

        Raises:
            ValueError: If k is invalid
            FaissSearchError: If search fails
        """
        if k <= 0:
            raise ValueError("k must be positive")

        try:
            distances, indices = self.index.search(query_vector.reshape(1, -1), k)
            return list(zip(indices[0], distances[0]))
        except Exception as e:
            raise FaissSearchError(f"Nearest neighbors search failed: {e}", "get_nearest_neighbors")

    async def compute_distance(self, vector1: np.ndarray, vector2: np.ndarray) -> float:
        """
        Compute Euclidean distance between two vectors.

        Args:
            vector1: First vector
            vector2: Second vector

        Returns:
            Euclidean distance

        Raises:
            ValueError: If vectors have different shapes
        """
        if vector1.shape != vector2.shape:
            raise ValueError(f"Vectors must have same shape: {vector1.shape} vs {vector2.shape}")

        return float(np.linalg.norm(vector1 - vector2))

    async def normalize_vector(self, vector: np.ndarray) -> np.ndarray:
        """
        Normalize vector to unit length.

        Args:
            vector: Vector to normalize

        Returns:
            Normalized vector
        """
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    async def compute_similarity(self, vector1: np.ndarray, vector2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vector1: First vector
            vector2: Second vector

        Returns:
            Cosine similarity (-1 to 1)

        Raises:
            ValueError: If vectors have different shapes
        """
        if vector1.shape != vector2.shape:
            raise ValueError(f"Vectors must have same shape: {vector1.shape} vs {vector2.shape}")

        # Normalize vectors
        norm1 = np.linalg.norm(vector1)
        norm2 = np.linalg.norm(vector2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(vector1, vector2) / (norm1 * norm2))
