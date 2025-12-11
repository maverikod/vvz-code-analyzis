"""
Security manager for query security validation and monitoring.

This module provides comprehensive security validation for queries,
including protection against injections, resource limits, and monitoring.

Features:
- Security validation using SecurityValidator
- Resource limit checking
- Suspicious query detection and logging
- Risk assessment and scoring
- Security monitoring and alerting

Architecture:
- Security validation pipeline
- Resource monitoring
- Threat detection
- Audit logging

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from chunk_metadata_adapter import ChunkQuery
from chunk_metadata_adapter.security_validator import SecurityValidator
from chunk_metadata_adapter.complexity_analyzer import ComplexityAnalyzer

from vector_store.exceptions import CommandError

logger = logging.getLogger("vector_store.utils.security_manager")


@dataclass
class SecurityValidationResult:
    """
    Result of security validation.
    
    Contains security check results, risk assessment,
    and recommendations for query safety.
    """
    
    is_safe: bool
    """Whether the query is considered safe."""
    
    warnings: List[str]
    """List of security warnings."""
    
    risk_score: float
    """Risk score from 0.0 (safe) to 1.0 (high risk)."""
    
    blocked_reason: Optional[str] = None
    """Reason why query was blocked if not safe."""
    
    recommendations: List[str] = None
    """Security recommendations."""
    
    validation_time: float = 0.0
    """Time taken for validation."""
    
    def __post_init__(self):
        """Initialize default values."""
        if self.recommendations is None:
            self.recommendations = []


@dataclass
class ResourceLimits:
    """
    Resource limits configuration.
    
    Defines limits for query resources to prevent abuse.
    """
    
    max_filter_size: int = 1024
    """Maximum filter size in bytes."""
    
    max_nested_depth: int = 5
    """Maximum nested depth of filter."""
    
    max_conditions: int = 50
    """Maximum number of conditions in filter."""
    
    max_complexity_score: float = 0.8
    """Maximum complexity score."""
    
    max_execution_time: float = 10.0
    """Maximum execution time in seconds."""
    
    rate_limit_per_minute: int = 100
    """Rate limit per minute per user."""


class SecurityManager:
    """
    Manager for query security validation and monitoring.
    
    Handles security checks, logging, and monitoring of suspicious queries.
    
    Features:
    - Multi-layer security validation
    - Resource limit enforcement
    - Threat detection and logging
    - Risk assessment and scoring
    - Security monitoring and alerting
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize security manager.
        
        Args:
            config: Security configuration
        """
        self.config = config or {}
        
        # Initialize components
        self.security_validator = SecurityValidator()
        self.complexity_analyzer = ComplexityAnalyzer()
        
        # Resource limits
        self.resource_limits = ResourceLimits(
            max_filter_size=self.config.get("max_filter_size", 1024),
            max_nested_depth=self.config.get("max_nested_depth", 5),
            max_conditions=self.config.get("max_conditions", 50),
            max_complexity_score=self.config.get("max_complexity_score", 0.8),
            max_execution_time=self.config.get("max_execution_time", 10.0),
            rate_limit_per_minute=self.config.get("rate_limit_per_minute", 100)
        )
        
        # Security patterns
        self.forbidden_patterns = self.config.get("forbidden_patterns", [
            "__proto__", "__init__", "eval", "exec", "system", "shell",
            "javascript:", "vbscript:", "data:", "file://"
        ])
        
        self.allowed_fields = self.config.get("allowed_fields", [
            "category", "type", "status", "source_id", "tags", "rating",
            "created_at", "updated_at", "author", "title", "content"
        ])
        
        # Monitoring
        self.enable_monitoring = self.config.get("enable_monitoring", True)
        self.enable_logging = self.config.get("enable_logging", True)
        self.enable_rate_limiting = self.config.get("enable_rate_limiting", True)
        
        # Rate limiting
        self.rate_limit_cache: Dict[str, List[float]] = {}
        
        # Security metrics
        self.security_metrics: List[Dict[str, Any]] = []
        
        self.logger = logger
    
    def validate_security(
        self,
        metadata_filter: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SecurityValidationResult:
        """
        Validate security of query.
        
        Args:
            metadata_filter: Metadata filter to validate
            context: Security context (user_id, ip, etc.)
            
        Returns:
            SecurityValidationResult with validation results
        """
        start_time = time.time()
        context = context or {}
        
        try:
            warnings = []
            risk_score = 0.0
            
            # Check rate limiting
            if self.enable_rate_limiting:
                rate_limit_warnings = self._check_rate_limit(context)
                warnings.extend(rate_limit_warnings)
                if rate_limit_warnings:
                    risk_score += 0.3
            
            # Check using SecurityValidator
            validator_warnings = self._validate_with_security_validator(metadata_filter)
            warnings.extend(validator_warnings)
            if validator_warnings:
                risk_score += 0.4
            
            # Check resource limits
            resource_warnings = self._check_resource_limits(metadata_filter)
            warnings.extend(resource_warnings)
            if resource_warnings:
                risk_score += 0.2
            
            # Check for forbidden patterns
            pattern_warnings = self._check_forbidden_patterns(metadata_filter)
            warnings.extend(pattern_warnings)
            if pattern_warnings:
                risk_score += 0.5
            
            # Check field access
            field_warnings = self._check_field_access(metadata_filter)
            warnings.extend(field_warnings)
            if field_warnings:
                risk_score += 0.3
            
            # Check complexity
            complexity_warnings = self._check_complexity(metadata_filter)
            warnings.extend(complexity_warnings)
            if complexity_warnings:
                risk_score += 0.2
            
            # Determine if query is safe
            is_safe = len(warnings) == 0
            blocked_reason = None if is_safe else "; ".join(warnings[:3])
            
            # Generate recommendations
            recommendations = self._generate_security_recommendations(warnings)
            
            # Log suspicious queries
            if not is_safe and self.enable_logging:
                self._log_suspicious_query(metadata_filter, warnings, context, risk_score)
            
            # Update metrics
            if self.enable_monitoring:
                self._update_security_metrics(metadata_filter, is_safe, risk_score, context)
            
            validation_time = time.time() - start_time
            
            return SecurityValidationResult(
                is_safe=is_safe,
                warnings=warnings,
                risk_score=min(risk_score, 1.0),
                blocked_reason=blocked_reason,
                recommendations=recommendations,
                validation_time=validation_time
            )
            
        except Exception as e:
            self.logger.error(f"Security validation failed: {str(e)}")
            return SecurityValidationResult(
                is_safe=False,
                warnings=[f"Security validation error: {str(e)}"],
                risk_score=1.0,
                blocked_reason=f"Security validation error: {str(e)}",
                validation_time=time.time() - start_time
            )
    
    def _validate_with_security_validator(self, metadata_filter: Dict[str, Any]) -> List[str]:
        """
        Validate using SecurityValidator.
        
        Args:
            metadata_filter: Metadata filter to validate
            
        Returns:
            List of security warnings
        """
        warnings = []
        
        try:
            chunk_query = ChunkQuery(metadata=metadata_filter)
            security_result = self.security_validator.validate(chunk_query)
            
            if not security_result.is_safe:
                warnings.extend(security_result.warnings)
                
        except Exception as e:
            warnings.append(f"Security validator error: {str(e)}")
        
        return warnings
    
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
        if filter_size > self.resource_limits.max_filter_size:
            warnings.append(
                f"Filter too large: {filter_size} bytes (limit: {self.resource_limits.max_filter_size})"
            )
        
        # Check nested depth
        max_depth = self._calculate_nested_depth(metadata_filter)
        if max_depth > self.resource_limits.max_nested_depth:
            warnings.append(
                f"Filter too deeply nested: {max_depth} levels (limit: {self.resource_limits.max_nested_depth})"
            )
        
        # Check number of conditions
        condition_count = self._count_conditions(metadata_filter)
        if condition_count > self.resource_limits.max_conditions:
            warnings.append(
                f"Too many conditions: {condition_count} (limit: {self.resource_limits.max_conditions})"
            )
        
        return warnings
    
    def _check_forbidden_patterns(self, metadata_filter: Dict[str, Any]) -> List[str]:
        """
        Check for forbidden patterns in filter.
        
        Args:
            metadata_filter: Metadata filter to check
            
        Returns:
            List of pattern violation warnings
        """
        warnings = []
        filter_str = str(metadata_filter).lower()
        
        for pattern in self.forbidden_patterns:
            if pattern.lower() in filter_str:
                warnings.append(f"Forbidden pattern detected: {pattern}")
        
        return warnings
    
    def _check_field_access(self, metadata_filter: Dict[str, Any]) -> List[str]:
        """
        Check field access permissions.
        
        Args:
            metadata_filter: Metadata filter to check
            
        Returns:
            List of field access warnings
        """
        warnings = []
        
        def check_fields(obj: Any) -> None:
            if isinstance(obj, dict):
                for field in obj.keys():
                    if field not in self.allowed_fields and not field.startswith("$"):
                        warnings.append(f"Unauthorized field access: {field}")
                for value in obj.values():
                    check_fields(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_fields(item)
        
        check_fields(metadata_filter)
        return warnings
    
    def _check_complexity(self, metadata_filter: Dict[str, Any]) -> List[str]:
        warnings = []
        try:
            self.complexity_analyzer.visit(metadata_filter)
            metrics = self.complexity_analyzer.get_complexity_metrics()
            # Пример: если score слишком большой — warning
            if metrics.get("complexity_score", 0.0) > self.resource_limits.max_complexity_score:
                warnings.append("Complexity score exceeds limit")
        except Exception as e:
            warnings.append(f"Complexity analysis failed: {e}")
        return warnings
    
    def _check_rate_limit(self, context: Dict[str, Any]) -> List[str]:
        """
        Check rate limiting.
        
        Args:
            context: Query context with user information
            
        Returns:
            List of rate limit warnings
        """
        warnings = []
        
        user_id = context.get("user_id", "anonymous")
        current_time = time.time()
        
        # Get user's query history
        if user_id not in self.rate_limit_cache:
            self.rate_limit_cache[user_id] = []
        
        user_queries = self.rate_limit_cache[user_id]
        
        # Remove old queries (older than 1 minute)
        user_queries = [t for t in user_queries if current_time - t < 60]
        self.rate_limit_cache[user_id] = user_queries
        
        # Check rate limit
        if len(user_queries) >= self.resource_limits.rate_limit_per_minute:
            warnings.append(
                f"Rate limit exceeded: {len(user_queries)} queries per minute "
                f"(limit: {self.resource_limits.rate_limit_per_minute})"
            )
        else:
            # Add current query
            user_queries.append(current_time)
            self.rate_limit_cache[user_id] = user_queries
        
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
    
    def _count_conditions(self, obj: Any) -> int:
        """
        Count number of conditions in filter.
        
        Args:
            obj: Object to analyze
            
        Returns:
            Number of conditions
        """
        count = 0
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.startswith("$"):
                    count += 1
                else:
                    count += self._count_conditions(value)
        elif isinstance(obj, list):
            for item in obj:
                count += self._count_conditions(item)
        
        return count
    
    def _generate_security_recommendations(self, warnings: List[str]) -> List[str]:
        """
        Generate security recommendations based on warnings.
        
        Args:
            warnings: Security warnings
            
        Returns:
            List of security recommendations
        """
        recommendations = []
        
        for warning in warnings:
            if "too large" in warning.lower():
                recommendations.append("Consider using more specific filters to reduce size")
            elif "too deeply nested" in warning.lower():
                recommendations.append("Flatten nested conditions to improve performance")
            elif "too many conditions" in warning.lower():
                recommendations.append("Split query into multiple smaller queries")
            elif "forbidden pattern" in warning.lower():
                recommendations.append("Remove potentially dangerous patterns from query")
            elif "unauthorized field" in warning.lower():
                recommendations.append("Use only allowed fields in your query")
            elif "rate limit" in warning.lower():
                recommendations.append("Reduce query frequency or implement caching")
            elif "too complex" in warning.lower():
                recommendations.append("Simplify query structure for better performance")
        
        return recommendations
    
    def _log_suspicious_query(
        self,
        metadata_filter: Dict[str, Any],
        warnings: List[str],
        context: Dict[str, Any],
        risk_score: float
    ) -> None:
        """
        Log suspicious query for monitoring.
        
        Args:
            metadata_filter: Metadata filter
            warnings: Security warnings
            context: Query context
            risk_score: Risk score
        """
        self.logger.warning(
            "Suspicious query detected",
            extra={
                "filter": metadata_filter,
                "warnings": warnings,
                "context": context,
                "risk_score": risk_score,
                "timestamp": time.time(),
                "user_id": context.get("user_id", "unknown"),
                "ip_address": context.get("ip_address", "unknown")
            }
        )
    
    def _update_security_metrics(
        self,
        metadata_filter: Dict[str, Any],
        is_safe: bool,
        risk_score: float,
        context: Dict[str, Any]
    ) -> None:
        """
        Update security metrics.
        
        Args:
            metadata_filter: Metadata filter
            is_safe: Whether query is safe
            risk_score: Risk score
            context: Query context
        """
        metrics = {
            "timestamp": time.time(),
            "is_safe": is_safe,
            "risk_score": risk_score,
            "user_id": context.get("user_id", "unknown"),
            "filter_size": len(str(metadata_filter)),
            "condition_count": self._count_conditions(metadata_filter)
        }
        
        self.security_metrics.append(metrics)
        
        # Keep only last 1000 metrics
        if len(self.security_metrics) > 1000:
            self.security_metrics = self.security_metrics[-1000:]
    
    def get_security_metrics(self) -> List[Dict[str, Any]]:
        """
        Get security metrics.
        
        Returns:
            List of security metrics
        """
        return self.security_metrics.copy()
    
    def get_rate_limit_stats(self) -> Dict[str, Any]:
        """
        Get rate limiting statistics.
        
        Returns:
            Rate limiting statistics
        """
        stats = {}
        current_time = time.time()
        
        for user_id, queries in self.rate_limit_cache.items():
            recent_queries = [t for t in queries if current_time - t < 60]
            stats[user_id] = {
                "queries_last_minute": len(recent_queries),
                "rate_limit": self.resource_limits.rate_limit_per_minute,
                "limit_exceeded": len(recent_queries) >= self.resource_limits.rate_limit_per_minute
            }
        
        return stats
    
    def clear_rate_limit_cache(self) -> None:
        """Clear rate limiting cache."""
        self.rate_limit_cache.clear()
    
    def clear_security_metrics(self) -> None:
        """Clear security metrics."""
        self.security_metrics.clear() 