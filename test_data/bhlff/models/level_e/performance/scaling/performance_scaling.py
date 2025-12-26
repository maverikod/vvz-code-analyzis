"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Performance scaling analysis functionality.

This module implements performance scaling analysis
for evaluating computational efficiency in 7D phase
field theory simulations.

Theoretical Background:
    Performance scaling analysis evaluates the relationship
    between computational resources and problem complexity,
    providing optimization insights.

Example:
    >>> analyzer = PerformanceScalingAnalyzer(config)
    >>> results = analyzer.analyze_performance_scaling()
"""

import numpy as np
import time
import psutil
from typing import Dict, Any, List, Optional, Tuple
from scipy.optimize import curve_fit


class PerformanceScalingAnalyzer:
    """
    Performance scaling analysis for computational efficiency.

    Physical Meaning:
        Analyzes the relationship between computational
        performance and problem complexity in 7D phase
        field simulations.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize performance scaling analyzer.

        Args:
            config: Configuration dictionary
        """
        self.config = config

    def analyze_performance_scaling(self) -> Dict[str, Any]:
        """Analyze performance scaling behavior."""
        # Test different problem complexities
        problem_sizes = [64, 128, 256, 512, 1024]
        complexity_levels = [1, 2, 3, 4, 5]

        performance_results = {}

        # CPU scaling analysis
        cpu_scaling = self._analyze_cpu_scaling(problem_sizes)
        performance_results["cpu_scaling"] = cpu_scaling

        # Memory scaling analysis
        memory_scaling = self._analyze_memory_scaling(problem_sizes)
        performance_results["memory_scaling"] = memory_scaling

        # Complexity scaling analysis
        complexity_scaling = self._analyze_complexity_scaling(complexity_levels)
        performance_results["complexity_scaling"] = complexity_scaling

        # Overall performance analysis
        overall_performance = self._analyze_overall_performance(performance_results)
        performance_results["overall_performance"] = overall_performance

        return performance_results

    def _analyze_cpu_scaling(self, problem_sizes: List[int]) -> Dict[str, Any]:
        """Analyze CPU scaling behavior."""
        cpu_usage = []
        execution_times = []

        for size in problem_sizes:
            # Simulate CPU-intensive computation
            start_time = time.time()
            test_data = np.random.rand(size, size, size)

            # FFT computation (CPU intensive)
            result = np.fft.fftn(test_data)
            result = np.fft.ifftn(result)

            end_time = time.time()
            execution_times.append(end_time - start_time)

            # Simulate CPU usage measurement
            cpu_percent = min(100.0, size * 0.1)
            cpu_usage.append(cpu_percent)

        # Analyze CPU scaling
        cpu_scaling_exponent = self._compute_scaling_exponent(problem_sizes, cpu_usage)
        time_scaling_exponent = self._compute_scaling_exponent(
            problem_sizes, execution_times
        )

        return {
            "problem_sizes": problem_sizes,
            "cpu_usage": cpu_usage,
            "execution_times": execution_times,
            "cpu_scaling_exponent": cpu_scaling_exponent,
            "time_scaling_exponent": time_scaling_exponent,
            "cpu_efficiency": self._compute_cpu_efficiency(cpu_usage),
            "scaling_type": self._classify_scaling(cpu_scaling_exponent),
        }

    def _analyze_memory_scaling(self, problem_sizes: List[int]) -> Dict[str, Any]:
        """Analyze memory scaling behavior."""
        memory_usage = []
        memory_efficiency = []

        for size in problem_sizes:
            # Simulate memory allocation
            initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            # Allocate test data
            test_data = np.random.rand(size, size, size)
            final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            memory_usage.append(final_memory - initial_memory)

            # Compute memory efficiency
            theoretical_memory = (size**3) * 8 / 1024 / 1024  # 8 bytes per float64
            actual_memory = final_memory - initial_memory
            efficiency = (
                theoretical_memory / actual_memory if actual_memory > 0 else 0.0
            )
            memory_efficiency.append(efficiency)

        # Analyze memory scaling
        memory_scaling_exponent = self._compute_scaling_exponent(
            problem_sizes, memory_usage
        )
        efficiency_trend = self._compute_efficiency_trend(
            problem_sizes, memory_efficiency
        )

        return {
            "problem_sizes": problem_sizes,
            "memory_usage": memory_usage,
            "memory_efficiency": memory_efficiency,
            "memory_scaling_exponent": memory_scaling_exponent,
            "efficiency_trend": efficiency_trend,
            "scaling_type": self._classify_scaling(memory_scaling_exponent),
        }

    def _analyze_complexity_scaling(
        self, complexity_levels: List[int]
    ) -> Dict[str, Any]:
        """Analyze complexity scaling behavior."""
        execution_times = []
        resource_usage = []

        for complexity in complexity_levels:
            # Simulate computation with different complexity
            start_time = time.time()

            # Simulate nested loops based on complexity
            for _ in range(complexity):
                test_data = np.random.rand(64, 64, 64)
                result = np.fft.fftn(test_data)
                result = np.fft.ifftn(result)

            end_time = time.time()
            execution_times.append(end_time - start_time)

            # Simulate resource usage
            resource_usage.append(complexity * 20.0)  # 20% per complexity level

        # Analyze complexity scaling
        complexity_scaling_exponent = self._compute_scaling_exponent(
            complexity_levels, execution_times
        )
        resource_scaling_exponent = self._compute_scaling_exponent(
            complexity_levels, resource_usage
        )

        return {
            "complexity_levels": complexity_levels,
            "execution_times": execution_times,
            "resource_usage": resource_usage,
            "complexity_scaling_exponent": complexity_scaling_exponent,
            "resource_scaling_exponent": resource_scaling_exponent,
            "scaling_type": self._classify_scaling(complexity_scaling_exponent),
        }

    def _analyze_overall_performance(
        self, performance_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze overall performance characteristics."""
        cpu_scaling = performance_results["cpu_scaling"]
        memory_scaling = performance_results["memory_scaling"]
        complexity_scaling = performance_results["complexity_scaling"]

        # Compute overall efficiency
        cpu_efficiency = cpu_scaling["cpu_efficiency"]
        memory_efficiency = np.mean(memory_scaling["memory_efficiency"])
        overall_efficiency = (cpu_efficiency + memory_efficiency) / 2.0

        # Identify bottlenecks
        bottlenecks = []
        if cpu_scaling["cpu_scaling_exponent"] > 2.0:
            bottlenecks.append("cpu_bottleneck")
        if memory_scaling["memory_scaling_exponent"] > 2.0:
            bottlenecks.append("memory_bottleneck")
        if complexity_scaling["complexity_scaling_exponent"] > 2.0:
            bottlenecks.append("complexity_bottleneck")

        # Compute optimization potential
        optimization_potential = 1.0 - overall_efficiency

        return {
            "overall_efficiency": float(overall_efficiency),
            "cpu_efficiency": float(cpu_efficiency),
            "memory_efficiency": float(memory_efficiency),
            "bottlenecks": bottlenecks,
            "optimization_potential": float(optimization_potential),
            "performance_grade": self._compute_performance_grade(overall_efficiency),
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

    def _compute_cpu_efficiency(self, cpu_usage: List[float]) -> float:
        """Compute CPU efficiency from usage data."""
        if not cpu_usage:
            return 0.0

        # Efficiency is inversely related to CPU usage
        avg_cpu_usage = np.mean(cpu_usage)
        efficiency = 1.0 / (1.0 + avg_cpu_usage / 100.0)
        return float(efficiency)

    def _compute_efficiency_trend(
        self, sizes: List[int], efficiencies: List[float]
    ) -> str:
        """Compute efficiency trend from size-efficiency data."""
        if len(efficiencies) < 2:
            return "stable"

        # Compute trend
        trend = np.polyfit(sizes, efficiencies, 1)[0]

        if trend > 0.01:
            return "improving"
        elif trend < -0.01:
            return "degrading"
        else:
            return "stable"

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

    def _compute_performance_grade(self, efficiency: float) -> str:
        """Compute performance grade based on efficiency."""
        if efficiency >= 0.9:
            return "A"
        elif efficiency >= 0.8:
            return "B"
        elif efficiency >= 0.7:
            return "C"
        elif efficiency >= 0.6:
            return "D"
        else:
            return "F"
