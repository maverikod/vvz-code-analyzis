"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA optimization utilities for 7D phase field computations.

This package provides optimized CUDA kernels and memory management utilities
for efficient GPU-accelerated computations in the 7D phase field theory.
"""

from .optimized_kernels import (
    Optimized7DKernels,
    compute_7d_laplacian_optimized,
    compute_7d_gradient_optimized,
    compute_7d_phase_normalization_optimized,
)
from .memory_management import (
    CUDAMemoryManager,
    allocate_pinned_memory,
    async_transfer_and_compute,
)
from .advanced_features import (
    CUDAAdvancedFeatures,
    tensor_cores_available,
    allocate_unified_memory as allocate_unified,
    optimize_dimension_order,
)
from .tensor_cores import TensorCoreSupport
from .unified_memory import UnifiedMemoryManager
from .dimension_optimizer import DimensionOptimizer

__all__ = [
    "Optimized7DKernels",
    "compute_7d_laplacian_optimized",
    "compute_7d_gradient_optimized",
    "compute_7d_phase_normalization_optimized",
    "CUDAMemoryManager",
    "allocate_pinned_memory",
    "async_transfer_and_compute",
    "CUDAAdvancedFeatures",
    "tensor_cores_available",
    "allocate_unified",
    "optimize_dimension_order",
    "TensorCoreSupport",
    "UnifiedMemoryManager",
    "DimensionOptimizer",
]

