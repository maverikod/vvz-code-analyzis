"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory monitoring utilities for BHLFF project.

This module provides comprehensive memory monitoring functionality
for both CPU and GPU memory usage, ensuring efficient memory management
in the 7D phase field theory computations.

Physical Meaning:
    Monitors memory usage during phase field computations to ensure
    efficient resource utilization and prevent memory overflow.

Mathematical Foundation:
    Tracks memory allocation patterns and provides optimization
    recommendations for large-scale 7D computations.

Example:
    >>> monitor = MemoryMonitor()
    >>> monitor.start_monitoring()
    >>> # ... perform computations ...
    >>> memory_stats = monitor.get_memory_stats()
"""

import psutil
import gc
import logging
from typing import Dict, Any, Optional, List
import time
import threading
from contextlib import contextmanager

# CUDA memory monitoring
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False


class MemoryMonitor:
    """
    Memory monitoring utility for CPU and GPU memory.

    Physical Meaning:
        Monitors memory usage during phase field computations
        to ensure efficient resource utilization.
    """

    def __init__(self, log_interval: float = 1.0):
        """
        Initialize memory monitor.

        Args:
            log_interval (float): Interval for logging memory stats (seconds).
        """
        self.log_interval = log_interval
        self.logger = logging.getLogger(__name__)
        self.monitoring = False
        self.monitor_thread = None
        self.memory_history = []
        self.cuda_available = CUDA_AVAILABLE

        # Memory thresholds (in MB)
        self.cpu_warning_threshold = 1000  # 1GB
        self.cpu_critical_threshold = 2000  # 2GB
        self.gpu_warning_threshold = 500  # 500MB
        self.gpu_critical_threshold = 1000  # 1GB

    def get_cpu_memory_usage(self) -> Dict[str, float]:
        """
        Get CPU memory usage statistics.

        Physical Meaning:
            Returns current CPU memory usage statistics
            for monitoring and optimization.

        Returns:
            Dict[str, float]: CPU memory statistics in MB.
        """
        memory = psutil.virtual_memory()
        return {
            "total_mb": memory.total / (1024 * 1024),
            "available_mb": memory.available / (1024 * 1024),
            "used_mb": memory.used / (1024 * 1024),
            "percentage": memory.percent,
            "free_mb": memory.free / (1024 * 1024),
        }

    def get_gpu_memory_usage(self) -> Optional[Dict[str, float]]:
        """
        Get GPU memory usage statistics.

        Physical Meaning:
            Returns current GPU memory usage statistics
            for CUDA computations monitoring.

        Returns:
            Optional[Dict[str, float]]: GPU memory statistics in MB, or None if CUDA not available.
        """
        if not self.cuda_available:
            return None

        try:
            mempool = cp.get_default_memory_pool()
            pinned_mempool = cp.get_default_pinned_memory_pool()

            return {
                "total_mb": cp.cuda.Device().mem_info[1] / (1024 * 1024),
                "used_mb": (cp.cuda.Device().mem_info[1] - cp.cuda.Device().mem_info[0])
                / (1024 * 1024),
                "free_mb": cp.cuda.Device().mem_info[0] / (1024 * 1024),
                "mempool_used_mb": mempool.used_bytes() / (1024 * 1024),
                "mempool_total_mb": mempool.total_bytes() / (1024 * 1024),
                "pinned_used_mb": pinned_mempool.used_bytes() / (1024 * 1024),
                "pinned_total_mb": pinned_mempool.total_bytes() / (1024 * 1024),
            }
        except Exception as e:
            self.logger.warning(f"Failed to get GPU memory stats: {e}")
            return None

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive memory statistics.

        Physical Meaning:
            Returns complete memory usage statistics
            for both CPU and GPU memory.

        Returns:
            Dict[str, Any]: Complete memory statistics.
        """
        stats = {
            "timestamp": time.time(),
            "cpu": self.get_cpu_memory_usage(),
            "gpu": self.get_gpu_memory_usage(),
        }

        # Add warnings if thresholds exceeded
        cpu_stats = stats["cpu"]
        if cpu_stats["used_mb"] > self.cpu_critical_threshold:
            stats["warnings"] = stats.get("warnings", [])
            stats["warnings"].append(
                f"CRITICAL: CPU memory usage {cpu_stats['used_mb']:.1f}MB exceeds threshold {self.cpu_critical_threshold}MB"
            )
        elif cpu_stats["used_mb"] > self.cpu_warning_threshold:
            stats["warnings"] = stats.get("warnings", [])
            stats["warnings"].append(
                f"WARNING: CPU memory usage {cpu_stats['used_mb']:.1f}MB exceeds threshold {self.cpu_warning_threshold}MB"
            )

        if stats["gpu"]:
            gpu_stats = stats["gpu"]
            if gpu_stats["used_mb"] > self.gpu_critical_threshold:
                stats["warnings"] = stats.get("warnings", [])
                stats["warnings"].append(
                    f"CRITICAL: GPU memory usage {gpu_stats['used_mb']:.1f}MB exceeds threshold {self.gpu_critical_threshold}MB"
                )
            elif gpu_stats["used_mb"] > self.gpu_warning_threshold:
                stats["warnings"] = stats.get("warnings", [])
                stats["warnings"].append(
                    f"WARNING: GPU memory usage {gpu_stats['used_mb']:.1f}MB exceeds threshold {self.gpu_warning_threshold}MB"
                )

        return stats

    def start_monitoring(self) -> None:
        """
        Start continuous memory monitoring.

        Physical Meaning:
            Starts background monitoring of memory usage
            to track resource utilization patterns.
        """
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Memory monitoring started")

    def stop_monitoring(self) -> None:
        """
        Stop continuous memory monitoring.

        Physical Meaning:
            Stops background monitoring of memory usage.
        """
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        self.logger.info("Memory monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self.monitoring:
            try:
                stats = self.get_memory_stats()
                self.memory_history.append(stats)

                # Log warnings
                if "warnings" in stats:
                    for warning in stats["warnings"]:
                        self.logger.warning(warning)

                # Keep only last 100 entries
                if len(self.memory_history) > 100:
                    self.memory_history = self.memory_history[-100:]

                time.sleep(self.log_interval)
            except Exception as e:
                self.logger.error(f"Error in memory monitoring: {e}")
                time.sleep(self.log_interval)

    def force_garbage_collection(self) -> None:
        """
        Force garbage collection.

        Physical Meaning:
            Forces garbage collection to free unused memory
            and optimize memory usage.
        """
        gc.collect()
        if self.cuda_available:
            try:
                cp.get_default_memory_pool().free_all_blocks()
                cp.get_default_pinned_memory_pool().free_all_blocks()
            except Exception as e:
                self.logger.warning(f"Failed to free GPU memory: {e}")

        self.logger.info("Forced garbage collection completed")

    def get_memory_history(self) -> List[Dict[str, Any]]:
        """
        Get memory usage history.

        Physical Meaning:
            Returns historical memory usage data
            for analysis and optimization.

        Returns:
            List[Dict[str, Any]]: Memory usage history.
        """
        return self.memory_history.copy()

    def clear_memory_history(self) -> None:
        """Clear memory usage history."""
        self.memory_history.clear()

    def set_memory_thresholds(
        self,
        cpu_warning: float = None,
        cpu_critical: float = None,
        gpu_warning: float = None,
        gpu_critical: float = None,
    ) -> None:
        """
        Set memory usage thresholds.

        Physical Meaning:
            Updates memory usage thresholds for warnings
            and critical alerts.

        Args:
            cpu_warning (float, optional): CPU warning threshold in MB.
            cpu_critical (float, optional): CPU critical threshold in MB.
            gpu_warning (float, optional): GPU warning threshold in MB.
            gpu_critical (float, optional): GPU critical threshold in MB.
        """
        if cpu_warning is not None:
            self.cpu_warning_threshold = cpu_warning
        if cpu_critical is not None:
            self.cpu_critical_threshold = cpu_critical
        if gpu_warning is not None:
            self.gpu_warning_threshold = gpu_warning
        if gpu_critical is not None:
            self.gpu_critical_threshold = gpu_critical

        self.logger.info(
            f"Memory thresholds updated: CPU warning={self.cpu_warning_threshold}MB, "
            f"CPU critical={self.cpu_critical_threshold}MB, "
            f"GPU warning={self.gpu_warning_threshold}MB, "
            f"GPU critical={self.gpu_critical_threshold}MB"
        )

    def get_memory_recommendations(self) -> List[str]:
        """
        Get memory optimization recommendations.

        Physical Meaning:
            Analyzes memory usage patterns and provides
            optimization recommendations.

        Returns:
            List[str]: Memory optimization recommendations.
        """
        recommendations = []

        if not self.memory_history:
            return ["No memory history available for analysis"]

        # Analyze CPU memory trends
        cpu_usage = [entry["cpu"]["used_mb"] for entry in self.memory_history]
        if cpu_usage:
            avg_cpu = sum(cpu_usage) / len(cpu_usage)
            max_cpu = max(cpu_usage)

            if max_cpu > self.cpu_critical_threshold:
                recommendations.append(
                    f"CRITICAL: Peak CPU memory usage {max_cpu:.1f}MB exceeds critical threshold"
                )
            elif avg_cpu > self.cpu_warning_threshold:
                recommendations.append(
                    f"WARNING: Average CPU memory usage {avg_cpu:.1f}MB is high"
                )

            if max_cpu - min(cpu_usage) > 500:  # Large memory fluctuations
                recommendations.append(
                    "Consider implementing memory pooling to reduce fluctuations"
                )

        # Analyze GPU memory trends
        gpu_usage = [
            entry["gpu"]["used_mb"] for entry in self.memory_history if entry["gpu"]
        ]
        if gpu_usage:
            avg_gpu = sum(gpu_usage) / len(gpu_usage)
            max_gpu = max(gpu_usage)

            if max_gpu > self.gpu_critical_threshold:
                recommendations.append(
                    f"CRITICAL: Peak GPU memory usage {max_gpu:.1f}MB exceeds critical threshold"
                )
            elif avg_gpu > self.gpu_warning_threshold:
                recommendations.append(
                    f"WARNING: Average GPU memory usage {avg_gpu:.1f}MB is high"
                )

            if max_gpu - min(gpu_usage) > 200:  # Large GPU memory fluctuations
                recommendations.append(
                    "Consider using GPU memory pooling to reduce fluctuations"
                )

        # General recommendations
        if not recommendations:
            recommendations.append("Memory usage is within acceptable limits")

        return recommendations

    def __repr__(self) -> str:
        """String representation of memory monitor."""
        status = "monitoring" if self.monitoring else "stopped"
        return f"MemoryMonitor(status={status}, history_entries={len(self.memory_history)})"


@contextmanager
def memory_monitor_context(
    monitor: Optional[MemoryMonitor] = None, auto_cleanup: bool = True
):
    """
    Context manager for memory monitoring.

    Physical Meaning:
        Provides automatic memory monitoring and cleanup
        for computational blocks.

    Args:
        monitor (Optional[MemoryMonitor]): Memory monitor instance.
        auto_cleanup (bool): Whether to force garbage collection on exit.
    """
    if monitor is None:
        monitor = MemoryMonitor()

    try:
        monitor.start_monitoring()
        yield monitor
    finally:
        monitor.stop_monitoring()
        if auto_cleanup:
            monitor.force_garbage_collection()


def create_memory_monitor(log_interval: float = 1.0) -> MemoryMonitor:
    """
    Create a memory monitor instance.

    Physical Meaning:
        Creates a configured memory monitor for
        tracking resource usage.

    Args:
        log_interval (float): Monitoring interval in seconds.

    Returns:
        MemoryMonitor: Configured memory monitor.
    """
    return MemoryMonitor(log_interval=log_interval)
