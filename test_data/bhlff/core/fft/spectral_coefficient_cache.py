"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral Coefficient Cache for BHLFF Framework.

This module provides caching for spectral coefficients of the fractional operator,
enabling efficient reuse of pre-computed coefficients for repeated operations.

Theoretical Background:
    The spectral coefficients μ|k|^(2β) + λ for the fractional operator depend
    only on the parameters μ, β, λ and domain shape. Caching these coefficients
    avoids redundant computation and improves performance.

Example:
    >>> cache = SpectralCoefficientCache()
    >>> coeffs = cache.get_coefficients(mu=1.0, beta=1.0, lambda_param=0.0, domain_shape=(256, 256, 256))
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import logging
import hashlib
import time
import gc


class SpectralCoefficientCache:
    """
    Cache for spectral coefficients of fractional operator.

    Physical Meaning:
        Caches spectral coefficients μ|k|^(2β) + λ for the fractional
        operator, enabling efficient reuse of pre-computed coefficients
        for repeated operations.

    Mathematical Foundation:
        - Pre-computation: coefficients depend only on parameters
        - Caching: reuse for identical parameters
        - Invalidation: update when parameters change
        - Memory management: limit cache size and manage memory usage

    Attributes:
        cache (Dict): Cache storage for coefficients.
        max_cache_size (int): Maximum number of cached entries.
        access_count (Dict): Access count for each cache entry.
        memory_usage (int): Current memory usage in bytes.
        hit_count (int): Number of cache hits.
        miss_count (int): Number of cache misses.
    """

    def __init__(self, max_cache_size: int = 100):
        """
        Initialize spectral coefficient cache.

        Physical Meaning:
            Sets up the cache for spectral coefficients with
            configurable size limits and memory management.

        Args:
            max_cache_size: Maximum number of cached entries.
        """
        self.cache = {}
        self.max_cache_size = max_cache_size
        self.access_count = {}
        self.memory_usage = 0
        self.hit_count = 0
        self.miss_count = 0

        # Setup logging
        self.logger = logging.getLogger(__name__)

        self.logger.info(
            f"SpectralCoefficientCache initialized: max_size={max_cache_size}"
        )

    def get_coefficients(
        self, mu: float, beta: float, lambda_param: float, domain_shape: Tuple[int, ...]
    ) -> np.ndarray:
        """
        Get spectral coefficients from cache.

        Physical Meaning:
            Returns spectral coefficients for the fractional operator,
            using cache for optimization or computing new ones if needed.

        Args:
            mu: Diffusion coefficient.
            beta: Fractional order.
            lambda_param: Damping parameter.
            domain_shape: Domain dimensions.

        Returns:
            np.ndarray: Spectral coefficients μ|k|^(2β) + λ.
        """
        # Create cache key
        cache_key = self._create_cache_key(mu, beta, lambda_param, domain_shape)

        # Check cache
        if cache_key in self.cache:
            self.hit_count += 1
            self.access_count[cache_key] += 1
            return self.cache[cache_key].copy()

        # Cache miss - compute new coefficients
        self.miss_count += 1
        coefficients = self._compute_coefficients(mu, beta, lambda_param, domain_shape)

        # Add to cache
        self._add_to_cache(cache_key, coefficients)

        return coefficients

    def clear_cache(self) -> None:
        """
        Clear all cached coefficients.

        Physical Meaning:
            Removes all cached coefficients to free memory
            and reset the cache state.
        """
        self.cache.clear()
        self.access_count.clear()
        self.memory_usage = 0
        gc.collect()

        self.logger.info("Spectral coefficient cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Physical Meaning:
            Returns detailed statistics about cache performance
            and memory usage.

        Returns:
            Dict[str, Any]: Cache statistics.
        """
        total_requests = self.hit_count + self.miss_count
        hit_rate = self.hit_count / max(1, total_requests)

        return {
            "cache_size": len(self.cache),
            "max_cache_size": self.max_cache_size,
            "memory_usage_bytes": self.memory_usage,
            "memory_usage_mb": self.memory_usage / 1024**2,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "hit_rate": hit_rate,
            "total_requests": total_requests,
            "cache_utilization": len(self.cache) / self.max_cache_size,
        }

    def optimize_cache(self) -> None:
        """
        Optimize cache by removing least used entries.

        Physical Meaning:
            Performs cache optimization by removing entries that
            are least frequently accessed to make room for new ones.
        """
        if len(self.cache) < self.max_cache_size:
            return

        # Sort by access count (ascending)
        sorted_entries = sorted(self.access_count.items(), key=lambda x: x[1])

        # Remove least used entries (keep top 80%)
        entries_to_remove = int(0.2 * len(self.cache))

        for cache_key, _ in sorted_entries[:entries_to_remove]:
            if cache_key in self.cache:
                self._remove_from_cache(cache_key)

        self.logger.info(
            f"Cache optimization complete: {entries_to_remove} entries removed"
        )

    def _create_cache_key(
        self, mu: float, beta: float, lambda_param: float, domain_shape: Tuple[int, ...]
    ) -> str:
        """
        Create cache key for parameters.

        Physical Meaning:
            Creates a unique key for the given parameters to
            identify cached coefficients.

        Args:
            mu: Diffusion coefficient.
            beta: Fractional order.
            lambda_param: Damping parameter.
            domain_shape: Domain dimensions.

        Returns:
            str: Cache key.
        """
        # Create hash of parameters
        params_str = f"{mu:.10f}_{beta:.10f}_{lambda_param:.10f}_{domain_shape}"
        return hashlib.md5(params_str.encode()).hexdigest()

    def _compute_coefficients(
        self, mu: float, beta: float, lambda_param: float, domain_shape: Tuple[int, ...]
    ) -> np.ndarray:
        """
        Compute spectral coefficients.

        Physical Meaning:
            Computes spectral coefficients μ|k|^(2β) + λ for the
            fractional operator in the given domain.

        Args:
            mu: Diffusion coefficient.
            beta: Fractional order.
            lambda_param: Damping parameter.
            domain_shape: Domain dimensions.

        Returns:
            np.ndarray: Spectral coefficients.
        """
        # Create wave vectors
        k_vectors = []
        for n in domain_shape:
            k = np.fft.fftfreq(n, d=1.0 / n)
            k *= 2 * np.pi  # Convert to angular frequency
            k_vectors.append(k)

        # Create meshgrid of wave vectors
        K_mesh = np.meshgrid(*k_vectors, indexing="ij")
        k_magnitude = np.sqrt(sum(K**2 for K in K_mesh))

        # Compute coefficients
        coefficients = mu * (k_magnitude ** (2 * beta)) + lambda_param

        # Handle k=0 mode
        if lambda_param == 0:
            coefficients[tuple([0] * len(domain_shape))] = 1.0

        return coefficients.astype(np.float64)

    def _add_to_cache(self, cache_key: str, coefficients: np.ndarray) -> None:
        """
        Add coefficients to cache.

        Physical Meaning:
            Adds computed coefficients to the cache with
            memory management and access tracking.

        Args:
            cache_key: Cache key.
            coefficients: Coefficients to cache.
        """
        # Check cache size limit
        if len(self.cache) >= self.max_cache_size:
            self.optimize_cache()

        # Add to cache
        self.cache[cache_key] = coefficients.copy()
        self.access_count[cache_key] = 1
        self.memory_usage += coefficients.nbytes

        self.logger.debug(
            f"Added coefficients to cache: key={cache_key[:8]}..., "
            f"shape={coefficients.shape}, memory={coefficients.nbytes/1024**2:.2f}MB"
        )

    def _remove_from_cache(self, cache_key: str) -> None:
        """
        Remove coefficients from cache.

        Physical Meaning:
            Removes coefficients from cache and updates
            memory usage tracking.

        Args:
            cache_key: Cache key to remove.
        """
        if cache_key in self.cache:
            coefficients = self.cache[cache_key]
            self.memory_usage -= coefficients.nbytes
            del self.cache[cache_key]
            del self.access_count[cache_key]

    def _estimate_memory_usage(self, domain_shape: Tuple[int, ...]) -> int:
        """
        Estimate memory usage for coefficients.

        Physical Meaning:
            Estimates the memory required to store coefficients
            for the given domain shape.

        Args:
            domain_shape: Domain dimensions.

        Returns:
            int: Estimated memory usage in bytes.
        """
        total_elements = np.prod(domain_shape)
        bytes_per_element = 8  # float64
        return total_elements * bytes_per_element

    def get_memory_info(self) -> Dict[str, Any]:
        """
        Get memory information for cache.

        Physical Meaning:
            Returns detailed memory usage information
            for the coefficient cache.

        Returns:
            Dict[str, Any]: Memory information.
        """
        return {
            "memory_usage_bytes": self.memory_usage,
            "memory_usage_mb": self.memory_usage / 1024**2,
            "memory_usage_gb": self.memory_usage / 1024**3,
            "cache_entries": len(self.cache),
            "average_entry_size_mb": (self.memory_usage / max(1, len(self.cache)))
            / 1024**2,
        }
