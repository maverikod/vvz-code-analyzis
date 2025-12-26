"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base scaling analysis functionality.

This module implements base scaling analysis functionality
for analyzing computational scaling behavior in
7D phase field theory simulations.

Theoretical Background:
    Base scaling analysis provides fundamental scaling
    analysis capabilities for computational efficiency
    evaluation in 7D phase field theory.

Example:
    >>> analyzer = BaseScalingAnalyzer(config)
    >>> results = analyzer.analyze_base_scaling()
"""

import numpy as np
import time
from typing import Dict, Any, List, Optional, Tuple


class BaseScalingAnalyzer:
    """
    Base scaling analysis for computational efficiency.

    Physical Meaning:
        Provides fundamental scaling analysis capabilities
        for evaluating computational efficiency in 7D
        phase field simulations.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize base scaling analyzer.

        Args:
            config: Configuration dictionary
        """
        self.config = config

    def analyze_base_scaling(self) -> Dict[str, Any]:
        """Analyze base scaling behavior."""
        # Test different problem sizes
        grid_sizes = [64, 128, 256, 512]
        domain_sizes = [10.0, 20.0, 40.0, 80.0]
        time_ranges = [1.0, 5.0, 10.0, 20.0]

        scaling_results = {}

        # Grid size scaling
        grid_scaling = self._test_grid_scaling(grid_sizes)
        scaling_results["grid_scaling"] = grid_scaling

        # Domain size scaling
        domain_scaling = self._test_domain_scaling(domain_sizes)
        scaling_results["domain_scaling"] = domain_scaling

        # Time range scaling
        time_scaling = self._test_time_scaling(time_ranges)
        scaling_results["time_scaling"] = time_scaling

        return scaling_results

    def _test_grid_scaling(self, grid_sizes: List[int]) -> Dict[str, Any]:
        """Test scaling with respect to grid size."""
        execution_times = []
        memory_usage = []

        for size in grid_sizes:
            # Simulate computation
            start_time = time.time()
            test_data = np.random.rand(size, size, size)
            result = np.fft.fftn(test_data)
            end_time = time.time()

            execution_times.append(end_time - start_time)
            memory_usage.append(test_data.nbytes / 1024 / 1024)  # MB

        # Analyze scaling
        scaling_exponent = self._compute_scaling_exponent(grid_sizes, execution_times)
        memory_scaling = self._compute_scaling_exponent(grid_sizes, memory_usage)

        return {
            "grid_sizes": grid_sizes,
            "execution_times": execution_times,
            "memory_usage": memory_usage,
            "scaling_exponent": scaling_exponent,
            "memory_scaling": memory_scaling,
            "scaling_type": self._classify_scaling(scaling_exponent),
        }

    def _test_domain_scaling(self, domain_sizes: List[float]) -> Dict[str, Any]:
        """Test scaling with respect to domain size."""
        execution_times = []
        memory_usage = []

        for size in domain_sizes:
            # Simulate computation based on domain size
            grid_size = int(size * 8)  # 8 points per unit
            start_time = time.time()
            test_data = np.random.rand(grid_size, grid_size, grid_size)
            result = np.fft.fftn(test_data)
            end_time = time.time()

            execution_times.append(end_time - start_time)
            memory_usage.append(test_data.nbytes / 1024 / 1024)  # MB

        # Analyze scaling
        scaling_exponent = self._compute_scaling_exponent(domain_sizes, execution_times)
        memory_scaling = self._compute_scaling_exponent(domain_sizes, memory_usage)

        return {
            "domain_sizes": domain_sizes,
            "execution_times": execution_times,
            "memory_usage": memory_usage,
            "scaling_exponent": scaling_exponent,
            "memory_scaling": memory_scaling,
            "scaling_type": self._classify_scaling(scaling_exponent),
        }

    def _test_time_scaling(self, time_ranges: List[float]) -> Dict[str, Any]:
        """Test scaling with respect to time range."""
        execution_times = []
        memory_usage = []

        for time_range in time_ranges:
            # Simulate computation based on time range
            time_steps = int(time_range * 100)  # 100 steps per unit time
            grid_size = 128

            start_time = time.time()
            for _ in range(time_steps):
                test_data = np.random.rand(grid_size, grid_size, grid_size)
                result = np.fft.fftn(test_data)
            end_time = time.time()

            execution_times.append(end_time - start_time)
            memory_usage.append(test_data.nbytes / 1024 / 1024)  # MB

        # Analyze scaling
        scaling_exponent = self._compute_scaling_exponent(time_ranges, execution_times)
        memory_scaling = self._compute_scaling_exponent(time_ranges, memory_usage)

        return {
            "time_ranges": time_ranges,
            "execution_times": execution_times,
            "memory_usage": memory_usage,
            "scaling_exponent": scaling_exponent,
            "memory_scaling": memory_scaling,
            "scaling_type": self._classify_scaling(scaling_exponent),
        }

    def _compute_scaling_exponent(
        self, sizes: List[float], times: List[float]
    ) -> float:
        """Compute scaling exponent from size-time relationship."""
        if len(sizes) < 2 or len(times) < 2:
            return 1.0

        # Fit power law: T(n) = a * n^b
        log_sizes = np.log(sizes)
        log_times = np.log(times)

        # Linear regression in log space
        if len(log_sizes) == 2:
            scaling_exponent = (log_times[1] - log_times[0]) / (
                log_sizes[1] - log_sizes[0]
            )
        else:
            scaling_exponent = np.polyfit(log_sizes, log_times, 1)[0]

        return float(scaling_exponent)

    def _classify_scaling(self, exponent: float) -> str:
        """Classify scaling behavior based on exponent."""
        if exponent < 1.0:
            return "sublinear"
        elif exponent < 1.5:
            return "linear"
        elif exponent < 2.0:
            return "quadratic"
        elif exponent < 3.0:
            return "cubic"
        else:
            return "supercubic"
