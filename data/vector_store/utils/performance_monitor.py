"""
Performance monitor for query performance and complexity analysis.

This module provides comprehensive performance monitoring for queries,
including complexity analysis, performance metrics, and optimization recommendations.

Features:
- Query complexity analysis
- Performance metrics tracking
- Slow query detection
- Optimization recommendations
- Performance monitoring and alerting

Architecture:
- Performance monitoring pipeline
- Complexity analysis integration
- Metrics collection and storage
- Recommendation generation

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from chunk_metadata_adapter import ChunkQuery
from chunk_metadata_adapter.complexity_analyzer import ComplexityAnalyzer

logger = logging.getLogger("vector_store.utils.performance_monitor")


@dataclass
class ComplexityResult:
    """
    Result of complexity analysis.
    
    Contains complexity metrics and analysis results for a query.
    """
    
    max_depth: int
    """Maximum nested depth of query."""
    
    total_conditions: int
    """Total number of conditions in query."""
    
    complexity_score: float
    """Complexity score from 0.0 to 1.0."""
    
    estimated_execution_time: float
    """Estimated execution time in seconds."""
    
    recommendations: List[str]
    """Optimization recommendations."""
    
    analysis_time: float = 0.0
    """Time taken for analysis."""


@dataclass
class PerformanceMetrics:
    """
    Performance metrics for a query.
    
    Contains performance data and analysis results.
    """
    
    query_id: str
    """Unique identifier for the query."""
    
    filter_hash: str
    """Hash of the metadata filter."""
    
    execution_time: float
    """Actual execution time in seconds."""
    
    complexity_score: float
    """Complexity score from analysis."""
    
    max_depth: int
    """Maximum nested depth."""
    
    total_conditions: int
    """Total number of conditions."""
    
    timestamp: float
    """Timestamp when metrics were collected."""
    
    user_id: Optional[str] = None
    """User ID if available."""
    
    command_name: Optional[str] = None
    """Name of the command that executed the query."""
    
    cache_hit: bool = False
    """Whether the query result was from cache."""
    
    optimization_applied: bool = False
    """Whether query optimization was applied."""


@dataclass
class PerformanceThresholds:
    """
    Performance thresholds configuration.
    
    Defines thresholds for performance monitoring and alerting.
    """
    
    slow_query_threshold: float = 1.0
    """Threshold for slow query detection in seconds."""
    
    very_slow_query_threshold: float = 5.0
    """Threshold for very slow query detection in seconds."""
    
    critical_query_threshold: float = 10.0
    """Threshold for critical slow query detection in seconds."""
    
    max_complexity_score: float = 0.8
    """Maximum acceptable complexity score."""
    
    max_depth_threshold: int = 5
    """Maximum acceptable nested depth."""
    
    max_conditions_threshold: int = 20
    """Maximum acceptable number of conditions."""


class PerformanceMonitor:
    """
    Monitor for query performance and complexity analysis.
    
    Tracks performance metrics, analyzes complexity, and generates recommendations.
    
    Features:
    - Real-time performance monitoring
    - Complexity analysis integration
    - Slow query detection and alerting
    - Performance trend analysis
    - Optimization recommendations
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize performance monitor.
        
        Args:
            config: Performance monitoring configuration
        """
        self.config = config or {}
        
        # Initialize components
        self.complexity_analyzer = ComplexityAnalyzer()
        
        # Performance thresholds
        self.thresholds = PerformanceThresholds(
            slow_query_threshold=self.config.get("slow_query_threshold", 1.0),
            very_slow_query_threshold=self.config.get("very_slow_query_threshold", 5.0),
            critical_query_threshold=self.config.get("critical_query_threshold", 10.0),
            max_complexity_score=self.config.get("max_complexity_score", 0.8),
            max_depth_threshold=self.config.get("max_depth_threshold", 5),
            max_conditions_threshold=self.config.get("max_conditions_threshold", 20)
        )
        
        # Monitoring settings
        self.enable_monitoring = self.config.get("enable_monitoring", True)
        self.enable_logging = self.config.get("enable_logging", True)
        self.enable_recommendations = self.config.get("enable_recommendations", True)
        self.enable_trend_analysis = self.config.get("enable_trend_analysis", True)
        
        # Metrics storage
        self.performance_metrics: List[PerformanceMetrics] = []
        self.complexity_cache: Dict[str, ComplexityResult] = {}
        
        # Cache settings
        self.cache_size = self.config.get("complexity_cache_size", 1000)
        self.cache_ttl = self.config.get("complexity_cache_ttl", 3600)
        
        # Performance trends
        self.performance_trends: Dict[str, List[float]] = {}
        
        self.logger = logger
    
    def analyze_complexity(
        self,
        metadata_filter: Dict[str, Any]
    ) -> ComplexityResult:
        """Analyze complexity of query and return analysis result."""
        start_time = time.time()
        filter_hash = self._hash_filter(metadata_filter)

        # Check cache
        if self.config.get("enable_complexity_cache", True):
            cached_complexity = self.complexity_cache.get(filter_hash)
            if cached_complexity and (time.time() - cached_complexity.analysis_time < self.cache_ttl):
                cached_complexity.analysis_time = time.time() - start_time # Update analysis time for cache hit
                return cached_complexity

        # Use visit + get_complexity_metrics
        self.complexity_analyzer.visit(metadata_filter)
        metrics = self.complexity_analyzer.get_complexity_metrics()

        complexity_score = metrics.get("complexity_score", 0.0)
        estimated_execution_time = metrics.get("estimated_execution_time", 0.0)

        recommendations = self._generate_recommendations(metrics)

        result = ComplexityResult(
            max_depth=metrics.get("max_depth", 0),
            total_conditions=metrics.get("total_conditions", 0),
            complexity_score=complexity_score,
            estimated_execution_time=estimated_execution_time,
            recommendations=recommendations,
            analysis_time=time.time() - start_time
        )

        # Cache result
        if self.config.get("enable_complexity_cache", True):
            self.complexity_cache[filter_hash] = result
            # Simple LRU eviction
            if len(self.complexity_cache) > self.cache_size:
                oldest_key = next(iter(self.complexity_cache))
                del self.complexity_cache[oldest_key]

        self._log_complexity_metrics(result, metadata_filter)

        return result
    
    def monitor_performance(
        self,
        metadata_filter: Dict[str, Any],
        execution_time: float,
        complexity_result: Optional[ComplexityResult] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> PerformanceMetrics:
        """
        Monitor query performance.
        
        Args:
            metadata_filter: Metadata filter
            execution_time: Actual execution time in seconds
            complexity_result: Complexity analysis result
            context: Additional context
            
        Returns:
            PerformanceMetrics with performance data
        """
        context = context or {}
        
        # Analyze complexity if not provided
        if complexity_result is None:
            complexity_result = self.analyze_complexity(metadata_filter)
        
        # Create performance metrics
        filter_hash = self._hash_filter(metadata_filter)
        query_id = self._generate_query_id()
        
        # Handle both dict and ComplexityResult
        if isinstance(complexity_result, dict):
            complexity_score = complexity_result.get("complexity_score", 0.0)
            max_depth = complexity_result.get("max_depth", 0)
            total_conditions = complexity_result.get("total_conditions", 0)
        else:
            complexity_score = complexity_result.complexity_score
            max_depth = complexity_result.max_depth
            total_conditions = complexity_result.total_conditions
        
        metrics = PerformanceMetrics(
            query_id=query_id,
            filter_hash=filter_hash,
            execution_time=execution_time,
            complexity_score=complexity_score,
            max_depth=max_depth,
            total_conditions=total_conditions,
            timestamp=time.time(),
            user_id=context.get("user_id"),
            command_name=context.get("command_name"),
            cache_hit=context.get("cache_hit", False),
            optimization_applied=context.get("optimization_applied", False)
        )
        
        # Store metrics
        self.performance_metrics.append(metrics)
        
        # Keep only last 10000 metrics
        if len(self.performance_metrics) > 10000:
            self.performance_metrics = self.performance_metrics[-10000:]
        
        # Update trends
        if self.enable_trend_analysis:
            self._update_performance_trends(metrics)
        
        # Check for performance issues
        if self.enable_logging:
            self._check_performance_issues(metrics, complexity_result)
        
        return metrics
    
    def _generate_recommendations(self, complexity_result: Any) -> List[str]:
        """
        Generate optimization recommendations based on complexity analysis.
        
        Args:
            complexity_result: Complexity analysis result (dict or ComplexityResult)
            
        Returns:
            List of optimization recommendations
        """
        recommendations = []
        
        # Handle both dict and ComplexityResult
        if isinstance(complexity_result, dict):
            max_depth = complexity_result.get("max_depth", 0)
            total_conditions = complexity_result.get("total_conditions", 0)
            complexity_score = complexity_result.get("complexity_score", 0.0)
            estimated_execution_time = complexity_result.get("estimated_execution_time", 0.0)
            has_redundant_conditions = complexity_result.get("has_redundant_conditions", False)
            has_inefficient_operators = complexity_result.get("has_inefficient_operators", False)
        else:
            max_depth = complexity_result.max_depth
            total_conditions = complexity_result.total_conditions
            complexity_score = complexity_result.complexity_score
            estimated_execution_time = complexity_result.estimated_execution_time
            has_redundant_conditions = getattr(complexity_result, 'has_redundant_conditions', False)
            has_inefficient_operators = getattr(complexity_result, 'has_inefficient_operators', False)
        
        if max_depth > self.thresholds.max_depth_threshold:
            recommendations.append(
                f"Consider flattening nested conditions (current depth: {max_depth})"
            )
        
        if total_conditions > self.thresholds.max_conditions_threshold:
            recommendations.append(
                f"Consider splitting query into multiple smaller queries "
                f"(current conditions: {total_conditions})"
            )
        
        if complexity_score > self.thresholds.max_complexity_score:
            recommendations.append(
                f"Query is very complex (score: {complexity_score:.2f}), "
                "consider using indexes or simplifying structure"
            )
        
        if estimated_execution_time > self.thresholds.slow_query_threshold:
            recommendations.append(
                f"Query may be slow (estimated: {estimated_execution_time:.2f}s), "
                "consider optimization"
            )
        
        # Check for specific patterns
        if has_redundant_conditions:
            recommendations.append("Remove redundant conditions to improve performance")
        
        if has_inefficient_operators:
            recommendations.append("Consider using more efficient operators")
        
        return recommendations
    
    def _check_performance_issues(
        self,
        metrics: PerformanceMetrics,
        complexity_result: Any
    ) -> None:
        """
        Check for performance issues and log warnings.
        
        Args:
            metrics: Performance metrics
            complexity_result: Complexity analysis result (dict or ComplexityResult)
        """
        # Check execution time
        if metrics.execution_time > self.thresholds.critical_query_threshold:
            self.logger.error(
                f"Critical slow query detected: {metrics.execution_time}s",
                extra=self._create_log_context(metrics, complexity_result)
            )
        elif metrics.execution_time > self.thresholds.very_slow_query_threshold:
            self.logger.warning(
                f"Very slow query detected: {metrics.execution_time}s",
                extra=self._create_log_context(metrics, complexity_result)
            )
        elif metrics.execution_time > self.thresholds.slow_query_threshold:
            self.logger.info(
                f"Slow query detected: {metrics.execution_time}s",
                extra=self._create_log_context(metrics, complexity_result)
            )
        
        # Handle both dict and ComplexityResult
        if isinstance(complexity_result, dict):
            complexity_score = complexity_result.get("complexity_score", 0.0)
            max_depth = complexity_result.get("max_depth", 0)
        else:
            complexity_score = complexity_result.complexity_score
            max_depth = complexity_result.max_depth
        
        # Check complexity
        if complexity_score > self.thresholds.max_complexity_score:
            self.logger.warning(
                f"Complex query detected: score {complexity_score:.2f}",
                extra=self._create_log_context(metrics, complexity_result)
            )
        
        # Check depth
        if max_depth > self.thresholds.max_depth_threshold:
            self.logger.warning(
                f"Deeply nested query detected: depth {max_depth}",
                extra=self._create_log_context(metrics, complexity_result)
            )
    
    def _create_log_context(
        self,
        metrics: PerformanceMetrics,
        complexity_result: ComplexityResult
    ) -> Dict[str, Any]:
        """
        Create logging context for performance issues.
        
        Args:
            metrics: Performance metrics
            complexity_result: Complexity analysis result
            
        Returns:
            Logging context dictionary
        """
        return {
            "query_id": metrics.query_id,
            "execution_time": metrics.execution_time,
            "complexity_score": metrics.complexity_score,
            "max_depth": metrics.max_depth,
            "total_conditions": metrics.total_conditions,
            "user_id": metrics.user_id,
            "command_name": metrics.command_name,
            "cache_hit": metrics.cache_hit,
            "optimization_applied": metrics.optimization_applied,
            "recommendations": complexity_result.recommendations,
            "timestamp": datetime.fromtimestamp(metrics.timestamp).isoformat()
        }
    
    def _log_complexity_metrics(
        self,
        complexity_result: ComplexityResult,
        metadata_filter: Dict[str, Any]
    ) -> None:
        """
        Log complexity metrics.
        
        Args:
            complexity_result: Complexity analysis result
            metadata_filter: Metadata filter
        """
        self.logger.debug(
            "Complexity analysis completed",
            extra={
                "max_depth": complexity_result.max_depth,
                "total_conditions": complexity_result.total_conditions,
                "complexity_score": complexity_result.complexity_score,
                "estimated_execution_time": complexity_result.estimated_execution_time,
                "analysis_time": complexity_result.analysis_time,
                "filter_size": len(str(metadata_filter))
            }
        )
    
    def _update_performance_trends(self, metrics: PerformanceMetrics) -> None:
        """
        Update performance trends.
        
        Args:
            metrics: Performance metrics
        """
        trend_key = f"{metrics.command_name}_{metrics.user_id}"
        
        if trend_key not in self.performance_trends:
            self.performance_trends[trend_key] = []
        
        self.performance_trends[trend_key].append(metrics.execution_time)
        
        # Keep only last 100 trend points
        if len(self.performance_trends[trend_key]) > 100:
            self.performance_trends[trend_key] = self.performance_trends[trend_key][-100:]
    
    def _hash_filter(self, metadata_filter: Dict[str, Any]) -> str:
        """
        Generate hash for metadata filter.
        
        Args:
            metadata_filter: Metadata filter
            
        Returns:
            Hash string
        """
        return str(hash(str(metadata_filter)))
    
    def _generate_query_id(self) -> str:
        """
        Generate unique query ID.
        
        Returns:
            Unique query ID
        """
        return f"query_{int(time.time() * 1000000)}"
    
    def get_performance_metrics(
        self,
        user_id: Optional[str] = None,
        command_name: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[PerformanceMetrics]:
        """
        Get performance metrics with optional filtering.
        
        Args:
            user_id: Filter by user ID
            command_name: Filter by command name
            limit: Maximum number of metrics to return
            
        Returns:
            List of performance metrics
        """
        metrics = self.performance_metrics
        
        if user_id:
            metrics = [m for m in metrics if m.user_id == user_id]
        
        if command_name:
            metrics = [m for m in metrics if m.command_name == command_name]
        
        if limit:
            metrics = metrics[-limit:]
        
        return metrics
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get performance summary statistics.
        
        Returns:
            Performance summary dictionary
        """
        if not self.performance_metrics:
            return {
                "total_queries": 0,
                "average_execution_time": 0.0,
                "slow_queries_count": 0,
                "complex_queries_count": 0,
                "cache_hit_rate": 0.0,
                "optimization_rate": 0.0
            }
        
        execution_times = [m.execution_time for m in self.performance_metrics]
        complexity_scores = [m.complexity_score for m in self.performance_metrics]
        
        slow_queries = [m for m in self.performance_metrics 
                       if m.execution_time > self.thresholds.slow_query_threshold]
        complex_queries = [m for m in self.performance_metrics 
                          if m.complexity_score > self.thresholds.max_complexity_score]
        
        return {
            "total_queries": len(self.performance_metrics),
            "average_execution_time": sum(execution_times) / len(execution_times),
            "max_execution_time": max(execution_times),
            "min_execution_time": min(execution_times),
            "average_complexity_score": sum(complexity_scores) / len(complexity_scores),
            "slow_queries_count": len(slow_queries),
            "complex_queries_count": len(complex_queries),
            "cache_hit_rate": len([m for m in self.performance_metrics if m.cache_hit]) / len(self.performance_metrics),
            "optimization_rate": len([m for m in self.performance_metrics if m.optimization_applied]) / len(self.performance_metrics)
        }
    
    def get_performance_trends(self) -> Dict[str, List[float]]:
        """
        Get performance trends.
        
        Returns:
            Dictionary of performance trends
        """
        return self.performance_trends.copy()
    
    def clear_metrics(self) -> None:
        """Clear all performance metrics."""
        self.performance_metrics.clear()
        self.performance_trends.clear()
    
    def clear_complexity_cache(self) -> None:
        """Clear complexity analysis cache."""
        self.complexity_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics dictionary
        """
        return {
            "complexity_cache_size": len(self.complexity_cache),
            "performance_metrics_count": len(self.performance_metrics),
            "trends_count": len(self.performance_trends)
        } 