"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Management mixin for BVP block processing system.

This module provides utility methods for memory management, statistics, and
runtime optimisation of the BVP block processing workflow.
"""

import gc
from typing import Any, Dict

from .bvp_block_processing_base import cp


class BVPBlockProcessingManagementMixin:
    """Mixin supplying management, optimisation, and cleanup utilities."""

    def _cleanup_memory(self) -> None:
        """Release cached memory resources on CPU and GPU."""
        gc.collect()
        if getattr(self, "block_processor", None) and getattr(
            self.block_processor, "cuda_available", False
        ) and cp is not None:
            cp.get_default_memory_pool().free_all_blocks()

    def get_processing_stats(self) -> Dict[str, Any]:
        """Return aggregated processing statistics and memory usage."""
        return {
            **self.stats,
            "memory_usage": self.memory_monitor.get_cpu_memory_usage(),
            "block_processor_stats": self.block_processor.get_processing_stats(),
        }

    def optimize_for_field(self, field) -> None:
        """Optimise processor settings based on a reference field."""
        self.block_processor.optimize_for_field(field)
        field_size_gb = field.nbytes / (1024**3)

        if field_size_gb > 1.0:
            self.config.envelope_tolerance = 1e-4
            self.config.max_envelope_iterations = 50
        else:
            self.config.envelope_tolerance = 1e-6
            self.config.max_envelope_iterations = 100

        self.logger.info(
            "Optimised BVP settings for field size %.2f GB", field_size_gb
        )

    def cleanup(self) -> None:
        """Cleanup block processor resources and release memory."""
        self.block_processor.cleanup()
        self._cleanup_memory()
        self.logger.info("BVP block processing system cleaned up")
