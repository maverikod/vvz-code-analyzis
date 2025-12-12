"""
Service lock manager for distributed locking.

This module provides functionality for managing service-wide locks using Redis.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import time
import redis.asyncio as redis
from typing import Optional, Set
from contextlib import asynccontextmanager

logger = logging.getLogger("vector_store.service_lock_manager")

class ServiceLockManager:
    """
    Manages service-wide locks using Redis for distributed locking.
    Supports timeout-based locks for maintenance operations.
    """

    def __init__(self, redis_client: redis.Redis, timeout: int = 3600):
        """
        Initialize lock manager.
        
        Args:
            redis_client: Redis client for distributed locking
            timeout: Default lock timeout in seconds
        """
        self.redis = redis_client
        self.default_timeout = timeout
        self._lock = asyncio.Lock()
        self._active_connections: Set[str] = set()
        self._is_locked = False
        self._lock_reason: Optional[str] = None

    @property
    def is_locked(self) -> bool:
        """Check if service is currently locked."""
        return self._is_locked

    @property
    def lock_reason(self) -> Optional[str]:
        """Get reason for current lock."""
        return self._lock_reason

    def register_connection(self, connection_id: str) -> None:
        """Register an active connection."""
        self._active_connections.add(connection_id)
        logger.debug(f"Registered connection: {connection_id}")

    def unregister_connection(self, connection_id: str) -> None:
        """Unregister an active connection."""
        self._active_connections.discard(connection_id)
        logger.debug(f"Unregistered connection: {connection_id}")

    def get_active_connections(self) -> Set[str]:
        """Get all active connection IDs."""
        return self._active_connections.copy()

    async def acquire_lock(self, lock_name: str, timeout: int = None, reason: str = None) -> bool:
        """
        Acquire a distributed lock using Redis.
        
        Args:
            lock_name: Name of the lock
            timeout: Lock timeout in seconds (uses default if None)
            reason: Reason for locking (optional)
            
        Returns:
            True if lock acquired, False if already locked
            
        Raises:
            RuntimeError: If Redis operation fails
        """
        lock_timeout = timeout or self.default_timeout
        lock_key = f"lock:{lock_name}"
        lock_value = f"{int(time.time())}:{reason or 'maintenance'}"
        
        try:
            # Try to acquire lock using SET with NX and EX
            result = await self.redis.set(
                lock_key, 
                lock_value, 
                ex=lock_timeout, 
                nx=True
            )
            
            if result:
                self._is_locked = True
                self._lock_reason = reason
                logger.warning(f"Distributed lock acquired: {lock_name} ({reason})")
                return True
            else:
                # Check if lock exists and get its value
                existing_value = await self.redis.get(lock_key)
                if existing_value:
                    logger.warning(f"Lock already exists: {lock_name} = {existing_value.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to acquire lock {lock_name}: {e}")
            raise RuntimeError(f"Lock acquisition failed: {e}")

    async def release_lock(self, lock_name: str) -> bool:
        """
        Release a distributed lock.
        
        Args:
            lock_name: Name of the lock to release
            
        Returns:
            True if lock released, False if not found
            
        Raises:
            RuntimeError: If Redis operation fails
        """
        lock_key = f"lock:{lock_name}"
        
        try:
            # Delete the lock
            result = await self.redis.delete(lock_key)
            
            if result:
                self._is_locked = False
                self._lock_reason = None
                logger.info(f"Distributed lock released: {lock_name}")
                return True
            else:
                logger.warning(f"Lock not found for release: {lock_name}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to release lock {lock_name}: {e}")
            raise RuntimeError(f"Lock release failed: {e}")

    async def check_lock(self, lock_name: str) -> bool:
        """
        Check if a specific lock exists.
        
        Args:
            lock_name: Name of the lock to check
            
        Returns:
            True if lock exists, False otherwise
        """
        lock_key = f"lock:{lock_name}"
        
        try:
            exists = await self.redis.exists(lock_key)
            return bool(exists)
        except Exception as e:
            logger.error(f"Failed to check lock {lock_name}: {e}")
            return False

    async def get_lock_info(self, lock_name: str) -> Optional[dict]:
        """
        Get information about a lock.
        
        Args:
            lock_name: Name of the lock
            
        Returns:
            Dictionary with lock information or None if not found
        """
        lock_key = f"lock:{lock_name}"
        
        try:
            value = await self.redis.get(lock_key)
            if value:
                value_str = value.decode('utf-8')
                parts = value_str.split(':', 1)
                timestamp = int(parts[0])
                reason = parts[1] if len(parts) > 1 else 'unknown'
                
                ttl = await self.redis.ttl(lock_key)
                
                return {
                    "lock_name": lock_name,
                    "acquired_at": timestamp,
                    "reason": reason,
                    "ttl_seconds": ttl,
                    "expires_at": timestamp + ttl if ttl > 0 else None
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get lock info {lock_name}: {e}")
            return None

    async def wait_for_lock_release(self, lock_name: str, timeout: float = 30.0) -> bool:
        """
        Wait for a specific lock to be released.
        
        Args:
            lock_name: Name of the lock to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if lock was released, False if timeout
            
        Raises:
            TimeoutError: If lock is not released within timeout
        """
        start_time = time.time()
        
        while await self.check_lock(lock_name):
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Lock {lock_name} not released within {timeout} seconds")
            await asyncio.sleep(0.1)
        
        return True

    @asynccontextmanager
    async def acquire_lock_context(self, lock_name: str, timeout: int = None, reason: str = None):
        """
        Context manager for acquiring and automatically releasing a lock.
        
        Args:
            lock_name: Name of the lock
            timeout: Lock timeout in seconds
            reason: Reason for locking
            
        Raises:
            RuntimeError: If lock cannot be acquired
        """
        acquired = await self.acquire_lock(lock_name, timeout, reason)
        if not acquired:
            raise RuntimeError(f"Could not acquire lock: {lock_name}")
        
        try:
            yield
        finally:
            await self.release_lock(lock_name)

    async def cleanup_expired_locks(self) -> int:
        """
        Clean up expired locks (Redis handles this automatically with EX).
        This method can be used to manually clean up if needed.
        
        Returns:
            Number of locks cleaned up
        """
        try:
            # Get all lock keys
            lock_keys = await self.redis.keys("lock:*")
            cleaned_count = 0
            
            for key in lock_keys:
                # Check TTL
                ttl = await self.redis.ttl(key)
                if ttl <= 0:
                    await self.redis.delete(key)
                    cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired locks")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired locks: {e}")
            return 0
