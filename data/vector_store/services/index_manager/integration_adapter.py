"""
Integration adapter for IndexManager with existing services.

This file implements the integration layer that connects IndexManager
with existing vector store services while maintaining backward compatibility.

Features:
- Safe integration with existing services
- Graceful degradation and fallback
- Feature flags for controlling index usage
- Monitoring and validation of results
- A/B testing capabilities

Architecture:
- Adapter pattern for service integration
- Feature flag system for gradual rollout
- Monitoring and alerting capabilities
- Fallback mechanisms for reliability

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Created: 2024-01-15
Updated: 2024-01-15
"""

import logging
import time
from typing import Dict, List, Any, Optional, Union, Set, Callable, Awaitable
from datetime import datetime
import redis.asyncio as redis

from .base import (
    BaseIndexManager,
    IndexType,
    IndexManagerError,
    IndexOperationError,
    ValidationError
)
from .atomic_operations import AtomicIndexManager

logger = logging.getLogger(__name__)


class IndexManagerAdapter:
    """
    Adapter for integrating IndexManager with existing services.
    
    Provides safe integration with existing vector store services
    while maintaining backward compatibility and providing fallback mechanisms.
    
    Features:
    - Safe integration with existing services
    - Graceful degradation and fallback
    - Feature flags for controlling index usage
    - Monitoring and validation of results
    - A/B testing capabilities
    
    Architecture:
    - Adapter pattern for service integration
    - Feature flag system for gradual rollout
    - Monitoring and alerting capabilities
    - Fallback mechanisms for reliability
    """
    
    def __init__(self, redis_client: redis.Redis, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize index manager adapter.
        
        Args:
            redis_client: Redis client for index operations
            config: Configuration for the adapter
        """
        self.redis_client: redis.Redis = redis_client
        """Redis client for index operations."""
        
        # Configuration with defaults
        self.config: Dict[str, Any] = config or {}
        self.config.setdefault("enable_indexing", True)
        self.config.setdefault("enable_index_search", False)
        self.config.setdefault("enable_monitoring", True)
        self.config.setdefault("enable_ab_testing", False)
        self.config.setdefault("fallback_threshold", 0.95)  # 95% consistency required
        self.config.setdefault("performance_threshold", 2.0)  # 2x slower than legacy
        
        # Initialize index manager
        self.index_manager: Optional[BaseIndexManager] = None
        if self.config["enable_indexing"]:
            try:
                self.index_manager = AtomicIndexManager(redis_client)
                logger.info("IndexManager initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize IndexManager: {e}")
                self.index_manager = None
        
        # Feature flags
        self.indexing_enabled: bool = self.config["enable_indexing"] and self.index_manager is not None
        """Whether indexing is enabled."""
        
        self.index_search_enabled: bool = self.config["enable_index_search"] and self.indexing_enabled
        """Whether index-based search is enabled."""
        
        # Monitoring
        self.metrics: Dict[str, Any] = {
            "index_operations": 0,
            "search_operations": 0,
            "fallback_operations": 0,
            "error_count": 0,
            "performance_comparison": [],
            "consistency_checks": []
        }
        """Metrics for monitoring and alerting."""
    
    # Configuration methods
    
    def enable_indexing(self) -> bool:
        """
        Enable indexing operations.
        
        Returns:
            True if successfully enabled, False otherwise
        """
        if self.index_manager is None:
            logger.error("IndexManager not available, cannot enable indexing")
            return False
        
        self.indexing_enabled = True
        logger.info("Indexing enabled")
        return True
    
    def disable_indexing(self) -> bool:
        """
        Disable indexing operations.
        
        Returns:
            True if successfully disabled
        """
        self.indexing_enabled = False
        logger.info("Indexing disabled")
        return True
    
    def enable_index_search(self) -> bool:
        """
        Enable index-based search.
        
        Returns:
            True if successfully enabled, False otherwise
        """
        if not self.indexing_enabled:
            logger.error("Indexing not enabled, cannot enable index search")
            return False
        
        self.index_search_enabled = True
        logger.info("Index-based search enabled")
        return True
    
    def disable_index_search(self) -> bool:
        """
        Disable index-based search.
        
        Returns:
            True if successfully disabled
        """
        self.index_search_enabled = False
        logger.info("Index-based search disabled")
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the adapter.
        
        Returns:
            Dictionary with current status information
        """
        return {
            "index_manager_available": self.index_manager is not None,
            "indexing_enabled": self.indexing_enabled,
            "index_search_enabled": self.index_search_enabled,
            "metrics": self.metrics.copy(),
            "config": self.config.copy()
        }
    
    # Integration methods for existing services
    
    async def index_chunk_safe(self, uuid: str, chunk_data: Dict[str, Any]) -> bool:
        """
        Safely index a chunk with error handling and fallback.
        
        Args:
            uuid: Unique identifier of the chunk
            chunk_data: Chunk data to index
            
        Returns:
            True if indexing was successful, False otherwise
        """
        if not self.indexing_enabled:
            return True  # Not an error if indexing is disabled
        
        try:
            self.metrics["index_operations"] += 1
            await self.index_manager.index_chunk(uuid, chunk_data)
            logger.debug(f"Successfully indexed chunk {uuid}")
            return True
            
        except Exception as e:
            self.metrics["error_count"] += 1
            logger.error(f"Failed to index chunk {uuid}: {e}")
            return False
    
    async def remove_chunk_safe(self, uuid: str, chunk_data: Dict[str, Any]) -> bool:
        """
        Safely remove a chunk from indexes with error handling.
        
        Args:
            uuid: Unique identifier of the chunk
            chunk_data: Chunk data to remove
            
        Returns:
            True if removal was successful, False otherwise
        """
        if not self.indexing_enabled:
            return True  # Not an error if indexing is disabled
        
        try:
            await self.index_manager.remove_chunk_from_indexes(uuid, chunk_data)
            logger.debug(f"Successfully removed chunk {uuid} from indexes")
            return True
            
        except Exception as e:
            self.metrics["error_count"] += 1
            logger.error(f"Failed to remove chunk {uuid} from indexes: {e}")
            return False
    
    async def search_with_fallback(self, search_criteria: Dict[str, Any], 
                                 legacy_search_func: Callable[..., Awaitable[List[str]]], 
                                 *args, **kwargs) -> List[str]:
        """
        Perform search with fallback to legacy method.
        
        Args:
            search_criteria: Search criteria for index-based search
            legacy_search_func: Function to call for legacy search
            *args: Additional arguments for legacy search
            **kwargs: Additional keyword arguments for legacy search
            
        Returns:
            List of UUIDs matching the search criteria
        """
        if not self.index_search_enabled:
            # Use legacy search only
            return await legacy_search_func(*args, **kwargs)
        
        try:
            self.metrics["search_operations"] += 1
            start_time = time.time()
            
            # Perform index-based search
            index_results = await self.index_manager.search_combined(search_criteria)
            index_time = time.time() - start_time
            
            # Perform legacy search for comparison
            start_time = time.time()
            legacy_results = await legacy_search_func(*args, **kwargs)
            legacy_time = time.time() - start_time
            
            # Compare results
            consistency = self._calculate_consistency(index_results, legacy_results)
            performance_ratio = index_time / legacy_time if legacy_time > 0 else float('inf')
            
            # Record metrics
            self.metrics["performance_comparison"].append({
                "index_time": index_time,
                "legacy_time": legacy_time,
                "performance_ratio": performance_ratio,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            self.metrics["consistency_checks"].append({
                "consistency": consistency,
                "index_count": len(index_results),
                "legacy_count": len(legacy_results),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Check if we should use index results or fallback
            if self._should_use_index_results(consistency, performance_ratio):
                logger.debug(f"Using index-based search results (consistency: {consistency:.2f}, performance_ratio: {performance_ratio:.2f})")
                return index_results
            else:
                self.metrics["fallback_operations"] += 1
                logger.warning(f"Falling back to legacy search (consistency: {consistency:.2f}, performance_ratio: {performance_ratio:.2f})")
                return legacy_results
                
        except Exception as e:
            self.metrics["error_count"] += 1
            self.metrics["fallback_operations"] += 1
            logger.error(f"Index search failed, falling back to legacy: {e}")
            return await legacy_search_func(*args, **kwargs)
    
    async def initialize_indexes_safe(self, fields: Optional[Dict[str, IndexType]] = None) -> Dict[str, bool]:
        """
        Safely initialize indexes with error handling.
        
        Args:
            fields: Dictionary of field names and their index types
            
        Returns:
            Dictionary with results of index creation
        """
        if not self.indexing_enabled:
            return {"error": "Indexing not enabled"}
        
        try:
            # Default fields for indexing
            default_fields = {
                'uuid': IndexType.SCALAR,
                'source_id': IndexType.SCALAR,
                'source_path': IndexType.SCALAR,
                'category': IndexType.SCALAR,
                'type': IndexType.SCALAR,
                'language': IndexType.SCALAR,
                'status': IndexType.SCALAR,
                'tags': IndexType.ARRAY,
                'links': IndexType.ARRAY,
                'quality_score': IndexType.RANGE,
                'year': IndexType.RANGE
            }
            
            fields_to_index = fields or default_fields
            results = {}
            
            for field_name, index_type in fields_to_index.items():
                try:
                    await self.index_manager.create_index(field_name, index_type)
                    results[field_name] = True
                    logger.info(f"Created index for field: {field_name} ({index_type.value})")
                except Exception as e:
                    results[field_name] = False
                    logger.error(f"Failed to create index for field {field_name}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to initialize indexes: {e}")
            return {"error": str(e)}
    
    async def get_index_stats_safe(self) -> Dict[str, Any]:
        """
        Safely get index statistics.
        
        Returns:
            Dictionary with index statistics or error information
        """
        if not self.indexing_enabled:
            return {"error": "Indexing not enabled"}
        
        try:
            stats = await self.index_manager.get_index_stats()
            stats["adapter_metrics"] = self.metrics.copy()
            return stats
        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {"error": str(e)}
    
    # Monitoring and validation methods
    
    def _calculate_consistency(self, index_results: List[str], legacy_results: List[str]) -> float:
        """
        Calculate consistency between index and legacy results.
        
        Args:
            index_results: Results from index-based search
            legacy_results: Results from legacy search
            
        Returns:
            Consistency ratio between 0 and 1
        """
        if not legacy_results:
            return 1.0 if not index_results else 0.0
        
        index_set = set(index_results)
        legacy_set = set(legacy_results)
        
        intersection = len(index_set & legacy_set)
        union = len(index_set | legacy_set)
        
        return intersection / union if union > 0 else 0.0
    
    def _should_use_index_results(self, consistency: float, performance_ratio: float) -> bool:
        """
        Determine whether to use index results or fallback to legacy.
        
        Args:
            consistency: Consistency ratio between index and legacy results
            performance_ratio: Performance ratio (index_time / legacy_time)
            
        Returns:
            True if index results should be used, False for fallback
        """
        # Check consistency threshold
        if consistency < self.config["fallback_threshold"]:
            return False
        
        # Check performance threshold
        if performance_ratio > self.config["performance_threshold"]:
            return False
        
        return True
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics for monitoring.
        
        Returns:
            Dictionary with performance metrics
        """
        if not self.metrics["performance_comparison"]:
            return {"error": "No performance data available"}
        
        recent_comparisons = self.metrics["performance_comparison"][-100:]  # Last 100 comparisons
        
        avg_index_time = sum(c["index_time"] for c in recent_comparisons) / len(recent_comparisons)
        avg_legacy_time = sum(c["legacy_time"] for c in recent_comparisons) / len(recent_comparisons)
        avg_performance_ratio = sum(c["performance_ratio"] for c in recent_comparisons) / len(recent_comparisons)
        
        return {
            "average_index_time": avg_index_time,
            "average_legacy_time": avg_legacy_time,
            "average_performance_ratio": avg_performance_ratio,
            "total_operations": self.metrics["search_operations"],
            "fallback_operations": self.metrics["fallback_operations"],
            "error_count": self.metrics["error_count"],
            "fallback_rate": self.metrics["fallback_operations"] / max(self.metrics["search_operations"], 1)
        }
    
    def get_consistency_metrics(self) -> Dict[str, Any]:
        """
        Get consistency metrics for monitoring.
        
        Returns:
            Dictionary with consistency metrics
        """
        if not self.metrics["consistency_checks"]:
            return {"error": "No consistency data available"}
        
        recent_checks = self.metrics["consistency_checks"][-100:]  # Last 100 checks
        
        avg_consistency = sum(c["consistency"] for c in recent_checks) / len(recent_checks)
        min_consistency = min(c["consistency"] for c in recent_checks)
        max_consistency = max(c["consistency"] for c in recent_checks)
        
        return {
            "average_consistency": avg_consistency,
            "minimum_consistency": min_consistency,
            "maximum_consistency": max_consistency,
            "total_checks": len(recent_checks),
            "checks_below_threshold": len([c for c in recent_checks if c["consistency"] < self.config["fallback_threshold"]])
        }
    
    # A/B testing methods
    
    def enable_ab_testing(self) -> None:
        """Enable A/B testing mode."""
        self.config["enable_ab_testing"] = True
        logger.info("A/B testing enabled")
    
    def disable_ab_testing(self) -> None:
        """Disable A/B testing mode."""
        self.config["enable_ab_testing"] = False
        logger.info("A/B testing disabled")
    
    async def ab_test_search(self, search_criteria: Dict[str, Any], 
                           legacy_search_func: Callable[..., Awaitable[List[str]]], 
                           *args, **kwargs) -> Dict[str, Any]:
        """
        Perform A/B test between index and legacy search.
        
        Args:
            search_criteria: Search criteria for index-based search
            legacy_search_func: Function to call for legacy search
            *args: Additional arguments for legacy search
            **kwargs: Additional keyword arguments for legacy search
            
        Returns:
            Dictionary with A/B test results
        """
        if not self.config["enable_ab_testing"]:
            return {"error": "A/B testing not enabled"}
        
        try:
            # Perform both searches
            start_time = time.time()
            index_results = await self.index_manager.search_combined(search_criteria)
            index_time = time.time() - start_time
            
            start_time = time.time()
            legacy_results = await legacy_search_func(*args, **kwargs)
            legacy_time = time.time() - start_time
            
            # Calculate metrics
            consistency = self._calculate_consistency(index_results, legacy_results)
            performance_ratio = index_time / legacy_time if legacy_time > 0 else float('inf')
            
            return {
                "index_results": index_results,
                "legacy_results": legacy_results,
                "index_time": index_time,
                "legacy_time": legacy_time,
                "performance_ratio": performance_ratio,
                "consistency": consistency,
                "index_count": len(index_results),
                "legacy_count": len(legacy_results),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"A/B test failed: {e}")
            return {"error": str(e)}
    
    # Utility methods
    
    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = {
            "index_operations": 0,
            "search_operations": 0,
            "fallback_operations": 0,
            "error_count": 0,
            "performance_comparison": [],
            "consistency_checks": []
        }
        logger.info("Metrics reset")
    
    def cleanup_old_metrics(self, max_entries: int = 1000) -> None:
        """
        Clean up old metrics to prevent memory bloat.
        
        Args:
            max_entries: Maximum number of entries to keep
        """
        if len(self.metrics["performance_comparison"]) > max_entries:
            self.metrics["performance_comparison"] = self.metrics["performance_comparison"][-max_entries:]
        
        if len(self.metrics["consistency_checks"]) > max_entries:
            self.metrics["consistency_checks"] = self.metrics["consistency_checks"][-max_entries:]
        
        logger.debug(f"Cleaned up metrics, keeping max {max_entries} entries")


# Factory function for creating adapter
def create_index_manager_adapter(redis_client: redis.Redis, 
                               config: Optional[Dict[str, Any]] = None) -> IndexManagerAdapter:
    """
    Factory function to create index manager adapter.
    
    Args:
        redis_client: Redis client for index operations
        config: Optional configuration for the adapter
        
    Returns:
        Configured index manager adapter instance
    """
    return IndexManagerAdapter(redis_client, config)
