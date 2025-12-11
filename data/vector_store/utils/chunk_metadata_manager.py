"""
Central manager for chunk_metadata_adapter integration.

This module provides a unified interface for all chunk_metadata_adapter components
including validation, security, optimization, and monitoring.

Features:
- Centralized management of all components
- Unified configuration and initialization
- Consistent interface for all operations
- Performance monitoring and caching

Architecture:
- Manager pattern for component coordination
- Factory pattern for component creation
- Strategy pattern for different processing modes
- Observer pattern for monitoring and logging

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from chunk_metadata_adapter import ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator
from chunk_metadata_adapter.security_validator import SecurityValidator
from chunk_metadata_adapter.ast_optimizer import ASTOptimizer
from chunk_metadata_adapter.complexity_analyzer import ComplexityAnalyzer
from chunk_metadata_adapter.filter_executor import FilterExecutor

from vector_store.exceptions import ValidationError, CommandError

logger = logging.getLogger("vector_store.utils.chunk_metadata_manager")


@dataclass
class QueryProcessingResult:
    """
    Result of query processing pipeline.
    
    Contains validation results, security checks, optimizations,
    and complexity analysis for a processed query.
    """
    
    is_valid: bool
    """Whether the query is valid."""
    
    errors: Optional[List[str]] = None
    """List of validation errors if query is invalid."""
    
    optimized_filter: Optional[Dict[str, Any]] = None
    """Optimized version of the original filter."""
    
    complexity_analysis: Optional[Dict[str, Any]] = None
    """Complexity analysis results."""
    
    security_result: Optional[Dict[str, Any]] = None
    """Security validation results."""
    
    processing_time: float = 0.0
    """Time taken to process the query."""
    
    cache_hit: bool = False
    """Whether the result was retrieved from cache."""


@dataclass
class SecurityResult:
    """
    Result of security validation.
    
    Contains security check results and warnings for a query.
    """
    
    is_safe: bool
    """Whether the query is considered safe."""
    
    warnings: List[str]
    """List of security warnings."""
    
    risk_score: float = 0.0
    """Risk score from 0.0 (safe) to 1.0 (high risk)."""
    
    blocked_reason: Optional[str] = None
    """Reason why query was blocked if not safe."""


class ChunkMetadataAdapterManager:
    """
    Central manager for all chunk_metadata_adapter components.
    
    Provides unified interface for validation, security, optimization,
    and monitoring of queries.
    
    Features:
    - Component initialization and configuration
    - Query processing pipeline
    - Performance monitoring
    - Caching and optimization
    - Security validation
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize manager with configuration.
        
        Args:
            config: Configuration dictionary for all components
        """
        self.config = config or {}
        
        # Initialize chunk_metadata_adapter components
        self.query_validator = QueryValidator()
        self.security_validator = SecurityValidator()
        self.ast_optimizer = ASTOptimizer()
        self.complexity_analyzer = ComplexityAnalyzer()
        self.filter_executor = FilterExecutor()
        
        # Initialize caches
        self.validation_cache: Dict[str, bool] = {}
        self.optimization_cache: Dict[str, Dict[str, Any]] = {}
        self.complexity_cache: Dict[str, Dict[str, Any]] = {}
        
        # Performance tracking
        self.performance_metrics: List[Dict[str, Any]] = []
        
        # Configuration
        self.enable_caching = self.config.get("enable_caching", True)
        self.enable_security = self.config.get("enable_security", True)
        self.enable_optimization = self.config.get("enable_optimization", True)
        self.enable_complexity_analysis = self.config.get("enable_complexity_analysis", True)
        
        # Thresholds
        self.max_filter_size = self.config.get("max_filter_size", 1024)
        self.max_nested_depth = self.config.get("max_nested_depth", 5)
        self.max_complexity_depth = self.config.get("max_complexity_depth", 10)
        self.slow_query_threshold = self.config.get("slow_query_threshold", 1.0)
        
        self.logger = logger
    
    def process_query(
        self,
        metadata_filter: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> QueryProcessingResult:
        """
        Process query through full validation pipeline.
        
        Args:
            metadata_filter: Metadata filter to process
            context: Additional context for processing
            
        Returns:
            QueryProcessingResult with processing results
        """
        start_time = time.time()
        context = context or {}
        
        try:
            # Check cache first
            if self.enable_caching:
                cache_key = self._generate_cache_key(metadata_filter)
                cached_result = self._get_cached_result(cache_key)
                if cached_result:
                    cached_result.cache_hit = True
                    return cached_result
            
            # Validate query
            validation_result = self._validate_query(metadata_filter)
            if not validation_result.is_valid:
                return QueryProcessingResult(
                    is_valid=False,
                    errors=validation_result.errors,
                    processing_time=time.time() - start_time
                )
            
            # Security check
            if self.enable_security:
                security_result = self._check_security(metadata_filter, context)
                if not security_result.is_safe:
                    return QueryProcessingResult(
                        is_valid=False,
                        errors=security_result.warnings,
                        processing_time=time.time() - start_time
                    )
            else:
                security_result = SecurityResult(is_safe=True, warnings=[])
            
            # Optimize query
            optimized_filter = metadata_filter
            if self.enable_optimization:
                optimized_filter = self._optimize_query(metadata_filter)
            
            # Analyze complexity
            complexity_analysis = None
            if self.enable_complexity_analysis:
                complexity_analysis = self._analyze_complexity(optimized_filter)
            
            # Monitor performance
            processing_time = time.time() - start_time
            self._monitor_performance(metadata_filter, processing_time, complexity_analysis)
            
            # Create result
            result = QueryProcessingResult(
                is_valid=True,
                optimized_filter=optimized_filter,
                complexity_analysis=complexity_analysis,
                security_result={
                    "is_safe": security_result.is_safe,
                    "warnings": security_result.warnings,
                    "risk_score": security_result.risk_score
                },
                processing_time=processing_time
            )
            
            # Cache result
            if self.enable_caching:
                self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Query processing failed: {str(e)}")
            return QueryProcessingResult(
                is_valid=False,
                errors=[f"Processing error: {str(e)}"],
                processing_time=time.time() - start_time
            )
    
    def _validate_query(self, metadata_filter: Dict[str, Any]) -> QueryProcessingResult:
        """
        Validate query using QueryValidator.
        
        Args:
            metadata_filter: Metadata filter to validate
            
        Returns:
            QueryProcessingResult with validation results
        """
        try:
            chunk_query = ChunkQuery(metadata=metadata_filter)
            validation_result = self.query_validator.validate(chunk_query)
            
            if validation_result.is_valid:
                return QueryProcessingResult(is_valid=True)
            else:
                errors = []
                for error in validation_result.errors:
                    if hasattr(error, 'message'):
                        errors.append(error.message)
                    else:
                        errors.append(str(error))
                
                return QueryProcessingResult(is_valid=False, errors=errors)
                
        except Exception as e:
            return QueryProcessingResult(
                is_valid=False,
                errors=[f"Validation error: {str(e)}"]
            )
    
    def _check_security(
        self,
        metadata_filter: Dict[str, Any],
        context: Dict[str, Any]
    ) -> SecurityResult:
        """
        Check security of query.
        
        Args:
            metadata_filter: Metadata filter to check
            context: Security context
            
        Returns:
            SecurityResult with security check results
        """
        warnings = []
        
        try:
            # Check using SecurityValidator
            chunk_query = ChunkQuery(metadata=metadata_filter)
            security_result = self.security_validator.validate(chunk_query)
            
            if not security_result.is_safe:
                warnings.extend(security_result.warnings)
            
            # Check resource limits
            resource_warnings = self._check_resource_limits(metadata_filter)
            warnings.extend(resource_warnings)
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(metadata_filter, warnings)
            
            is_safe = len(warnings) == 0
            
            # Log suspicious queries
            if not is_safe:
                self._log_suspicious_query(metadata_filter, warnings, context)
            
            return SecurityResult(
                is_safe=is_safe,
                warnings=warnings,
                risk_score=risk_score
            )
            
        except Exception as e:
            warnings.append(f"Security check error: {str(e)}")
            return SecurityResult(is_safe=False, warnings=warnings, risk_score=1.0)
    
    def _optimize_query(self, metadata_filter: Dict[str, Any]) -> Dict[str, Any]:
        """
        Optimize query using ASTOptimizer.
        
        Args:
            metadata_filter: Metadata filter to optimize
            
        Returns:
            Optimized metadata filter
        """
        try:
            chunk_query = ChunkQuery(metadata=metadata_filter)
            optimized_query = self.ast_optimizer.optimize(chunk_query)
            return optimized_query.metadata
            
        except Exception as e:
            self.logger.warning(f"Query optimization failed: {str(e)}")
            return metadata_filter  # Fallback to original filter
    
    def _analyze_complexity(self, metadata_filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyze complexity of the query using ComplexityAnalyzer.

        Args:
            metadata_filter: Filter to analyze

        Returns:
            Dict with complexity metrics or None
        """
        try:
            self.complexity_analyzer.visit(metadata_filter)
            metrics = self.complexity_analyzer.get_complexity_metrics()
            return metrics
        except Exception as e:
            self.logger.error(f"Complexity analysis failed: {e}")
            return None
    
    def _check_resource_limits(self, metadata_filter: Dict[str, Any]) -> List[str]:
        """
        Check resource limits for query.
        
        Args:
            metadata_filter: Metadata filter to check
            
        Returns:
            List of resource limit warnings
        """
        warnings = []
        
        # Check filter size
        filter_size = len(str(metadata_filter))
        if filter_size > self.max_filter_size:
            warnings.append(f"Filter too large: {filter_size} bytes")
        
        # Check nested depth
        max_depth = self._calculate_nested_depth(metadata_filter)
        if max_depth > self.max_nested_depth:
            warnings.append(f"Filter too deeply nested: {max_depth} levels")
        
        return warnings
    
    def _calculate_nested_depth(self, obj: Any, current_depth: int = 0) -> int:
        """
        Calculate maximum nested depth of an object.
        
        Args:
            obj: Object to analyze
            current_depth: Current depth level
            
        Returns:
            Maximum nested depth
        """
        if isinstance(obj, dict):
            max_depth = current_depth
            for value in obj.values():
                depth = self._calculate_nested_depth(value, current_depth + 1)
                max_depth = max(max_depth, depth)
            return max_depth
        elif isinstance(obj, list):
            max_depth = current_depth
            for item in obj:
                depth = self._calculate_nested_depth(item, current_depth + 1)
                max_depth = max(max_depth, depth)
            return max_depth
        else:
            return current_depth
    
    def _calculate_risk_score(
        self,
        metadata_filter: Dict[str, Any],
        warnings: List[str]
    ) -> float:
        """
        Calculate risk score for query.
        
        Args:
            metadata_filter: Metadata filter
            warnings: Security warnings
            
        Returns:
            Risk score from 0.0 to 1.0
        """
        base_score = len(warnings) * 0.1
        
        # Check for high-risk patterns
        filter_str = str(metadata_filter).lower()
        if any(pattern in filter_str for pattern in ["__proto__", "__init__", "eval", "exec"]):
            base_score += 0.5
        
        return min(base_score, 1.0)
    
    def _log_suspicious_query(
        self,
        metadata_filter: Dict[str, Any],
        warnings: List[str],
        context: Dict[str, Any]
    ) -> None:
        """
        Log suspicious query for monitoring.
        
        Args:
            metadata_filter: Metadata filter
            warnings: Security warnings
            context: Query context
        """
        self.logger.warning(
            "Suspicious query detected",
            extra={
                "filter": metadata_filter,
                "warnings": warnings,
                "context": context,
                "timestamp": time.time()
            }
        )
    
    def _monitor_performance(
        self,
        metadata_filter: Dict[str, Any],
        processing_time: float,
        complexity_analysis: Optional[Dict[str, Any]]
    ) -> None:
        """
        Monitor query performance.
        
        Args:
            metadata_filter: Metadata filter
            processing_time: Processing time in seconds
            complexity_analysis: Complexity analysis results
        """
        metrics = {
            "filter": metadata_filter,
            "processing_time": processing_time,
            "complexity_score": complexity_analysis.get("complexity_score", 0) if complexity_analysis else 0,
            "timestamp": time.time()
        }
        
        self.performance_metrics.append(metrics)
        
        # Keep only last 1000 metrics
        if len(self.performance_metrics) > 1000:
            self.performance_metrics = self.performance_metrics[-1000:]
        
        # Log slow queries
        if processing_time > self.slow_query_threshold:
            self.logger.warning(f"Slow query detected: {processing_time}s", extra=metrics)
    
    def _generate_cache_key(self, metadata_filter: Dict[str, Any]) -> str:
        """
        Generate cache key for metadata filter.
        
        Args:
            metadata_filter: Metadata filter
            
        Returns:
            Cache key string
        """
        return str(hash(str(metadata_filter)))
    
    def _get_cached_result(self, cache_key: str) -> Optional[QueryProcessingResult]:
        """
        Get cached result.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached result or None
        """
        return self.validation_cache.get(cache_key)
    
    def _cache_result(self, cache_key: str, result: QueryProcessingResult) -> None:
        """
        Cache processing result.
        
        Args:
            cache_key: Cache key
            result: Processing result to cache
        """
        self.validation_cache[cache_key] = result
        
        # Keep cache size manageable
        if len(self.validation_cache) > 1000:
            # Remove oldest entries
            oldest_keys = list(self.validation_cache.keys())[:100]
            for key in oldest_keys:
                del self.validation_cache[key]
    
    def get_performance_metrics(self) -> List[Dict[str, Any]]:
        """
        Get performance metrics.
        
        Returns:
            List of performance metrics
        """
        return self.performance_metrics.copy()
    
    def clear_caches(self) -> None:
        """Clear all caches."""
        self.validation_cache.clear()
        self.optimization_cache.clear()
        self.complexity_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Cache statistics
        """
        return {
            "validation_cache_size": len(self.validation_cache),
            "optimization_cache_size": len(self.optimization_cache),
            "complexity_cache_size": len(self.complexity_cache),
            "performance_metrics_count": len(self.performance_metrics)
        } 