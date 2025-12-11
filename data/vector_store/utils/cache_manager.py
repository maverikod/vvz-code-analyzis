"""
Cache manager for query processing results.

This module provides efficient caching for query processing results,
including validation results, optimizations, and processing results.

Features:
- Multi-level caching (validation, optimization, results)
- LRU eviction policy
- TTL-based expiration
- Cache statistics and monitoring
- Memory usage optimization

Architecture:
- Cache management with multiple cache types
- LRU eviction for memory management
- TTL-based expiration for data freshness
- Statistics collection and monitoring

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from collections import OrderedDict

logger = logging.getLogger("vector_store.utils.cache_manager")


@dataclass
class CacheEntry:
    """
    Cache entry with metadata.
    
    Contains cached data with timestamp and access information.
    """
    
    data: Any
    """Cached data."""
    
    timestamp: float
    """Timestamp when entry was created."""
    
    last_access: float
    """Timestamp of last access."""
    
    access_count: int = 0
    """Number of times entry was accessed."""
    
    size: int = 0
    """Estimated size of entry in bytes."""


@dataclass
class CacheStats:
    """
    Cache statistics.
    
    Contains performance and usage statistics for cache.
    """
    
    total_entries: int
    """Total number of entries in cache."""
    
    total_size: int
    """Total size of cache in bytes."""
    
    hit_count: int
    """Number of cache hits."""
    
    miss_count: int
    """Number of cache misses."""
    
    hit_rate: float
    """Cache hit rate (0.0 to 1.0)."""
    
    eviction_count: int
    """Number of entries evicted."""
    
    memory_usage: float
    """Memory usage percentage."""


class CacheManager:
    """
    Manager for caching query processing results.
    
    Handles caching of validation results, optimizations, and processing results
    with efficient memory management and performance monitoring.
    
    Features:
    - Multi-level caching with different TTLs
    - LRU eviction policy for memory management
    - Cache statistics and performance monitoring
    - Memory usage optimization
    - Automatic cleanup and maintenance
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize cache manager.
        
        Args:
            config: Cache configuration
        """
        self.config = config or {}
        
        # Cache configuration
        self.validation_cache_size = self.config.get("validation_cache_size", 1000)
        self.optimization_cache_size = self.config.get("optimization_cache_size", 500)
        self.result_cache_size = self.config.get("result_cache_size", 200)
        
        self.validation_cache_ttl = self.config.get("validation_cache_ttl", 3600)  # 1 hour
        self.optimization_cache_ttl = self.config.get("optimization_cache_ttl", 1800)  # 30 minutes
        self.result_cache_ttl = self.config.get("result_cache_ttl", 300)  # 5 minutes
        
        # Initialize caches with OrderedDict for LRU functionality
        self.validation_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.optimization_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.result_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Statistics
        self.stats = {
            "validation": {"hits": 0, "misses": 0, "evictions": 0},
            "optimization": {"hits": 0, "misses": 0, "evictions": 0},
            "result": {"hits": 0, "misses": 0, "evictions": 0}
        }
        
        # Monitoring
        self.enable_monitoring = self.config.get("enable_monitoring", True)
        self.enable_cleanup = self.config.get("enable_cleanup", True)
        
        # Cleanup interval
        self.last_cleanup = time.time()
        self.cleanup_interval = self.config.get("cleanup_interval", 300)  # 5 minutes
        
        self.logger = logger
    
    def get_validation_cache(self, key: str) -> Optional[Any]:
        """
        Get validation result from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached validation result or None
        """
        return self._get_from_cache("validation", key, self.validation_cache, self.validation_cache_ttl)
    
    def set_validation_cache(self, key: str, data: Any) -> None:
        """
        Set validation result in cache.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        self._set_in_cache("validation", key, data, self.validation_cache, self.validation_cache_size)
    
    def get_optimization_cache(self, key: str) -> Optional[Any]:
        """
        Get optimization result from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached optimization result or None
        """
        return self._get_from_cache("optimization", key, self.optimization_cache, self.optimization_cache_ttl)
    
    def set_optimization_cache(self, key: str, data: Any) -> None:
        """
        Set optimization result in cache.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        self._set_in_cache("optimization", key, data, self.optimization_cache, self.optimization_cache_size)
    
    def get_result_cache(self, key: str) -> Optional[Any]:
        """
        Get processing result from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached processing result or None
        """
        return self._get_from_cache("result", key, self.result_cache, self.result_cache_ttl)
    
    def set_result_cache(self, key: str, data: Any) -> None:
        """
        Set processing result in cache.
        
        Args:
            key: Cache key
            data: Data to cache
        """
        self._set_in_cache("result", key, data, self.result_cache, self.result_cache_size)
    
    def _get_from_cache(
        self,
        cache_type: str,
        key: str,
        cache: OrderedDict[str, CacheEntry],
        ttl: float
    ) -> Optional[Any]:
        """
        Get data from cache with TTL check.
        
        Args:
            cache_type: Type of cache (validation, optimization, result)
            key: Cache key
            cache: Cache dictionary
            ttl: Time to live in seconds
            
        Returns:
            Cached data or None
        """
        current_time = time.time()
        
        if key in cache:
            entry = cache[key]
            
            # Check TTL
            if current_time - entry.timestamp > ttl:
                # Entry expired, remove it
                del cache[key]
                self.stats[cache_type]["misses"] += 1
                return None
            
            # Update access information
            entry.last_access = current_time
            entry.access_count += 1
            
            # Move to end for LRU
            cache.move_to_end(key)
            
            self.stats[cache_type]["hits"] += 1
            return entry.data
        else:
            self.stats[cache_type]["misses"] += 1
            return None
    
    def _set_in_cache(
        self,
        cache_type: str,
        key: str,
        data: Any,
        cache: OrderedDict[str, CacheEntry],
        max_size: int
    ) -> None:
        """
        Set data in cache with LRU eviction.
        
        Args:
            cache_type: Type of cache (validation, optimization, result)
            key: Cache key
            data: Data to cache
            cache: Cache dictionary
            max_size: Maximum cache size
        """
        current_time = time.time()
        
        # Estimate size (rough approximation)
        size = self._estimate_size(data)
        
        # Create cache entry
        entry = CacheEntry(
            data=data,
            timestamp=current_time,
            last_access=current_time,
            access_count=1,
            size=size
        )
        
        # Check if key already exists
        if key in cache:
            # Update existing entry
            cache[key] = entry
            cache.move_to_end(key)
        else:
            # Check if cache is full
            if len(cache) >= max_size:
                # Evict least recently used entry
                self._evict_lru_entry(cache_type, cache)
            
            # Add new entry
            cache[key] = entry
    
    def _evict_lru_entry(self, cache_type: str, cache: OrderedDict[str, CacheEntry]) -> None:
        """
        Evict least recently used entry from cache.
        
        Args:
            cache_type: Type of cache
            cache: Cache dictionary
        """
        if cache:
            # Remove oldest entry (first in OrderedDict)
            oldest_key = next(iter(cache))
            del cache[oldest_key]
            self.stats[cache_type]["evictions"] += 1
    
    def _estimate_size(self, data: Any) -> int:
        """
        Estimate size of data in bytes.
        
        Args:
            data: Data to estimate size for
            
        Returns:
            Estimated size in bytes
        """
        try:
            # Convert to string and get length as rough estimate
            return len(str(data))
        except:
            return 0
    
    def cleanup_expired_entries(self) -> None:
        """Clean up expired entries from all caches."""
        current_time = time.time()
        
        # Clean validation cache
        self._cleanup_cache("validation", self.validation_cache, self.validation_cache_ttl, current_time)
        
        # Clean optimization cache
        self._cleanup_cache("optimization", self.optimization_cache, self.optimization_cache_ttl, current_time)
        
        # Clean result cache
        self._cleanup_cache("result", self.result_cache, self.result_cache_ttl, current_time)
        
        self.last_cleanup = current_time
    
    def _cleanup_cache(
        self,
        cache_type: str,
        cache: OrderedDict[str, CacheEntry],
        ttl: float,
        current_time: float
    ) -> None:
        """
        Clean up expired entries from specific cache.
        
        Args:
            cache_type: Type of cache
            cache: Cache dictionary
            ttl: Time to live in seconds
            current_time: Current timestamp
        """
        expired_keys = []
        
        for key, entry in cache.items():
            if current_time - entry.timestamp > ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del cache[key]
        
        if expired_keys and self.enable_monitoring:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired entries from {cache_type} cache")
    
    def get_cache_stats(self, cache_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Args:
            cache_type: Specific cache type or None for all
            
        Returns:
            Cache statistics
        """
        if cache_type:
            return self._get_single_cache_stats(cache_type)
        else:
            return {
                "validation": self._get_single_cache_stats("validation"),
                "optimization": self._get_single_cache_stats("optimization"),
                "result": self._get_single_cache_stats("result"),
                "total": self._get_total_stats()
            }
    
    def _get_single_cache_stats(self, cache_type: str) -> CacheStats:
        """
        Get statistics for single cache.
        
        Args:
            cache_type: Type of cache
            
        Returns:
            Cache statistics
        """
        if cache_type == "validation":
            cache = self.validation_cache
        elif cache_type == "optimization":
            cache = self.optimization_cache
        elif cache_type == "result":
            cache = self.result_cache
        else:
            raise ValueError(f"Unknown cache type: {cache_type}")
        
        stats = self.stats[cache_type]
        total_entries = len(cache)
        total_size = sum(entry.size for entry in cache.values())
        
        total_requests = stats["hits"] + stats["misses"]
        hit_rate = stats["hits"] / total_requests if total_requests > 0 else 0.0
        
        return CacheStats(
            total_entries=total_entries,
            total_size=total_size,
            hit_count=stats["hits"],
            miss_count=stats["misses"],
            hit_rate=hit_rate,
            eviction_count=stats["evictions"],
            memory_usage=0.0  # Could be calculated based on system memory
        )
    
    def _get_total_stats(self) -> Dict[str, Any]:
        """
        Get total statistics across all caches.
        
        Returns:
            Total statistics
        """
        total_hits = sum(stats["hits"] for stats in self.stats.values())
        total_misses = sum(stats["misses"] for stats in self.stats.values())
        total_evictions = sum(stats["evictions"] for stats in self.stats.values())
        
        total_requests = total_hits + total_misses
        overall_hit_rate = total_hits / total_requests if total_requests > 0 else 0.0
        
        return {
            "total_entries": len(self.validation_cache) + len(self.optimization_cache) + len(self.result_cache),
            "total_hits": total_hits,
            "total_misses": total_misses,
            "overall_hit_rate": overall_hit_rate,
            "total_evictions": total_evictions
        }
    
    def clear_cache(self, cache_type: Optional[str] = None) -> None:
        """
        Clear cache or all caches.
        
        Args:
            cache_type: Specific cache type or None for all
        """
        if cache_type == "validation" or cache_type is None:
            self.validation_cache.clear()
        if cache_type == "optimization" or cache_type is None:
            self.optimization_cache.clear()
        if cache_type == "result" or cache_type is None:
            self.result_cache.clear()
        
        if cache_type is None:
            # Reset statistics
            for cache_stats in self.stats.values():
                cache_stats["hits"] = 0
                cache_stats["misses"] = 0
                cache_stats["evictions"] = 0
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get detailed cache information.
        
        Returns:
            Detailed cache information
        """
        return {
            "configuration": {
                "validation_cache_size": self.validation_cache_size,
                "optimization_cache_size": self.optimization_cache_size,
                "result_cache_size": self.result_cache_size,
                "validation_cache_ttl": self.validation_cache_ttl,
                "optimization_cache_ttl": self.optimization_cache_ttl,
                "result_cache_ttl": self.result_cache_ttl,
                "enable_monitoring": self.enable_monitoring,
                "enable_cleanup": self.enable_cleanup,
                "cleanup_interval": self.cleanup_interval
            },
            "current_usage": {
                "validation_entries": len(self.validation_cache),
                "optimization_entries": len(self.optimization_cache),
                "result_entries": len(self.result_cache),
                "total_entries": len(self.validation_cache) + len(self.optimization_cache) + len(self.result_cache)
            },
            "statistics": self.get_cache_stats()
        }
    
    def maintenance(self) -> None:
        """Perform cache maintenance tasks."""
        current_time = time.time()
        
        # Cleanup expired entries if needed
        if self.enable_cleanup and current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_expired_entries()
        
        # Log cache statistics periodically
        if self.enable_monitoring:
            stats = self.get_cache_stats()
            total_entries = stats["total"]["total_entries"]
            hit_rate = stats["total"]["overall_hit_rate"]
            
            self.logger.debug(
                f"Cache status: {total_entries} entries, "
                f"hit rate: {hit_rate:.2%}"
            ) 