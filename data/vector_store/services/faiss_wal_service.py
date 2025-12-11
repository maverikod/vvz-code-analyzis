"""
Write-Ahead Log (WAL) service for FAISS operations.

This module provides a WAL system for FAISS operations to ensure
data durability and enable fast recovery on startup.

Features:
- Logs all FAISS operations (add, delete) to disk
- Enables fast recovery by replaying logs
- Supports log rotation and cleanup
- Thread-safe async operations

Author: Vector Store Team
Created: 2025-01-27
"""

import json
import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

# Operation types
OP_ADD_VECTORS = "add_vectors"
OP_DELETE_VECTORS = "delete_vectors"
OP_CLEAR_INDEX = "clear_index"


class FaissWALService:
    """
    Write-Ahead Log service for FAISS operations.
    
    Provides durable logging of all FAISS operations to enable
    fast recovery and data consistency.
    """
    
    def __init__(self, log_dir: str = "data1/logs", max_log_size: int = 100 * 1024 * 1024):
        """
        Initialize WAL service.
        
        Args:
            log_dir: Directory for log files
            max_log_size: Maximum log file size in bytes before rotation
        """
        self.log_dir = log_dir
        self.max_log_size = max_log_size
        self.current_log_file = None
        self.log_lock = asyncio.Lock()
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        # Initialize current log file
        self._init_current_log_file()
        
        logger.info(f"FAISS WAL service initialized: {log_dir}")
    
    def _init_current_log_file(self) -> None:
        """Initialize current log file path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_log_file = os.path.join(self.log_dir, f"faiss_wal_{timestamp}.log")
        logger.info(f"Current WAL file: {self.current_log_file}")
    
    async def log_operation(
        self,
        operation: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None
    ) -> None:
        """
        Log an operation to WAL.
        
        Args:
            operation: Operation type (add_vectors, delete_vectors, etc.)
            data: Operation data
            timestamp: Optional timestamp, uses current time if None
        """
        if timestamp is None:
            timestamp = time.time()
        
        log_entry = {
            "timestamp": timestamp,
            "operation": operation,
            "data": data
        }
        
        async with self.log_lock:
            try:
                # Check if we need to rotate log file
                if os.path.exists(self.current_log_file):
                    file_size = os.path.getsize(self.current_log_file)
                    if file_size > self.max_log_size:
                        self._init_current_log_file()
                
                # Write log entry
                with open(self.current_log_file, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')
                
                logger.debug(f"Logged operation: {operation}")
                
            except Exception as e:
                logger.error(f"Failed to log operation {operation}: {e}")
                raise
    
    async def log_add_vectors(
        self,
        vectors: List[np.ndarray],
        indices: List[int]
    ) -> None:
        """
        Log vector addition operation.
        
        Args:
            vectors: List of vectors added
            indices: FAISS indices assigned to vectors
        """
        # Convert numpy arrays to lists for JSON serialization
        vectors_data = [vector.tolist() for vector in vectors]
        
        await self.log_operation(OP_ADD_VECTORS, {
            "vectors": vectors_data,
            "indices": indices,
            "count": len(vectors)
        })
    
    async def log_delete_vectors(self, indices: List[int]) -> None:
        """
        Log vector deletion operation.
        
        Args:
            indices: FAISS indices to delete
        """
        await self.log_operation(OP_DELETE_VECTORS, {
            "indices": indices,
            "count": len(indices)
        })
    
    async def log_clear_index(self) -> None:
        """Log index clearing operation."""
        await self.log_operation(OP_CLEAR_INDEX, {
            "timestamp": time.time()
        })
    
    def get_log_files(self) -> List[str]:
        """
        Get list of all log files sorted by creation time.
        
        Returns:
            List of log file paths
        """
        if not os.path.exists(self.log_dir):
            return []
        
        log_files = []
        for filename in os.listdir(self.log_dir):
            if filename.startswith("faiss_wal_") and filename.endswith(".log"):
                filepath = os.path.join(self.log_dir, filename)
                log_files.append(filepath)
        
        # Sort by creation time (oldest first)
        log_files.sort(key=lambda x: os.path.getctime(x))
        return log_files
    
    async def replay_logs(self, faiss_service) -> int:
        """
        Replay all log files to restore FAISS index state.
        
        Args:
            faiss_service: FAISS service instance to restore
            
        Returns:
            Number of operations replayed
        """
        log_files = self.get_log_files()
        if not log_files:
            logger.info("No WAL files found for replay")
            return 0
        
        logger.info(f"Starting WAL replay from {len(log_files)} files")
        
        operations_replayed = 0
        
        for log_file in log_files:
            try:
                file_operations = await self._replay_log_file(log_file, faiss_service)
                operations_replayed += file_operations
                logger.info(f"Replayed {file_operations} operations from {log_file}")
                
            except Exception as e:
                logger.error(f"Failed to replay log file {log_file}: {e}")
                # Continue with next file
                continue
        
        logger.info(f"WAL replay completed: {operations_replayed} operations replayed")
        return operations_replayed
    
    async def _replay_log_file(self, log_file: str, faiss_service) -> int:
        """
        Replay operations from a single log file.
        
        Args:
            log_file: Path to log file
            faiss_service: FAISS service instance
            
        Returns:
            Number of operations replayed
        """
        operations_replayed = 0
        
        try:
            with open(log_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        log_entry = json.loads(line.strip())
                        operation = log_entry.get("operation")
                        data = log_entry.get("data", {})
                        
                        if operation == OP_ADD_VECTORS:
                            vectors_data = data.get("vectors", [])
                            indices = data.get("indices", [])
                            
                            # Convert back to numpy arrays
                            vectors = [np.array(vector, dtype=np.float32) for vector in vectors_data]
                            
                            # Replay add operation
                            await faiss_service.add_vectors(vectors)
                            operations_replayed += 1
                            
                        elif operation == OP_DELETE_VECTORS:
                            indices = data.get("indices", [])
                            
                            # Replay delete operation
                            await faiss_service.delete_vectors(indices)
                            operations_replayed += 1
                            
                        elif operation == OP_CLEAR_INDEX:
                            # Replay clear operation
                            await faiss_service.clear_index()
                            operations_replayed += 1
                            
                        else:
                            logger.warning(f"Unknown operation in log: {operation}")
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in log file {log_file}, line {line_num}: {e}")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to replay operation in {log_file}, line {line_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read log file {log_file}: {e}")
            raise
        
        return operations_replayed
    
    async def cleanup_old_logs(self, keep_days: int = 7) -> int:
        """
        Clean up old log files.
        
        Args:
            keep_days: Number of days to keep logs
            
        Returns:
            Number of files deleted
        """
        cutoff_time = time.time() - (keep_days * 24 * 60 * 60)
        deleted_count = 0
        
        for log_file in self.get_log_files():
            try:
                file_time = os.path.getctime(log_file)
                if file_time < cutoff_time:
                    os.remove(log_file)
                    deleted_count += 1
                    logger.info(f"Deleted old log file: {log_file}")
                    
            except Exception as e:
                logger.error(f"Failed to delete old log file {log_file}: {e}")
        
        logger.info(f"Cleanup completed: {deleted_count} old log files deleted")
        return deleted_count
    
    def get_log_stats(self) -> Dict[str, Any]:
        """
        Get statistics about log files.
        
        Returns:
            Dictionary with log statistics
        """
        log_files = self.get_log_files()
        
        total_size = 0
        total_operations = 0
        
        for log_file in log_files:
            try:
                file_size = os.path.getsize(log_file)
                total_size += file_size
                
                # Count operations in file
                with open(log_file, 'r') as f:
                    operations_in_file = sum(1 for line in f if line.strip())
                total_operations += operations_in_file
                
            except Exception as e:
                logger.error(f"Failed to get stats for {log_file}: {e}")
        
        return {
            "log_files_count": len(log_files),
            "total_size_bytes": total_size,
            "total_operations": total_operations,
            "current_log_file": self.current_log_file
        } 