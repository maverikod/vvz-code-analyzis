"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory monitoring methods for phase vector.

This module provides memory monitoring methods as a mixin class.
"""

from typing import Dict, Any


class PhaseVectorMemoryMixin:
    """Mixin providing memory monitoring methods."""
    
    def _check_memory_usage(self, operation_name: str = "operation") -> None:
        """
        Check memory usage and log warnings if needed.
        
        Physical Meaning:
            Monitors memory usage during computations
            and provides warnings if thresholds are exceeded.
            
        Args:
            operation_name (str): Name of the operation being performed.
        """
        if not self.memory_monitor:
            return
        
        try:
            stats = self.memory_monitor.get_memory_stats()
            
            # Log memory usage
            cpu_used = stats["cpu"]["used_mb"]
            gpu_used = stats["gpu"]["used_mb"] if stats["gpu"] else 0
            
            self.logger.debug(
                f"{operation_name}: CPU memory {cpu_used:.1f}MB, GPU memory {gpu_used:.1f}MB"
            )
            
            # Check for warnings
            if "warnings" in stats:
                for warning in stats["warnings"]:
                    self.logger.warning(f"{operation_name}: {warning}")
        
        except Exception as e:
            self.logger.warning(
                f"Failed to check memory usage for {operation_name}: {e}"
            )
    
    def start_memory_monitoring(self) -> None:
        """
        Start memory monitoring.
        
        Physical Meaning:
            Starts continuous monitoring of memory usage
            during phase vector computations.
        """
        if self.memory_monitor:
            self.memory_monitor.start_monitoring()
            self.logger.info("Memory monitoring started")
    
    def stop_memory_monitoring(self) -> None:
        """
        Stop memory monitoring.
        
        Physical Meaning:
            Stops continuous monitoring of memory usage.
        """
        if self.memory_monitor:
            self.memory_monitor.stop_monitoring()
            self.logger.info("Memory monitoring stopped")
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get current memory statistics.
        
        Physical Meaning:
            Returns current memory usage statistics
            for both CPU and GPU memory.
            
        Returns:
            Dict[str, Any]: Memory statistics.
        """
        if self.memory_monitor:
            return self.memory_monitor.get_memory_stats()
        return {}
    
    def force_memory_cleanup(self) -> None:
        """
        Force memory cleanup.
        
        Physical Meaning:
            Forces garbage collection and memory cleanup
            to optimize memory usage.
        """
        if self.memory_monitor:
            self.memory_monitor.force_garbage_collection()
            self.logger.info("Memory cleanup completed")

