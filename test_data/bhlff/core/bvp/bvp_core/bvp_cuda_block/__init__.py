"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP CUDA block processing package.

This package provides CUDA-accelerated BVP block processing for 7D domains
with modular structure for maintainability and performance.

Physical Meaning:
    Provides modular CUDA-accelerated BVP block processing for 7D phase field
    computations, enabling memory-efficient BVP operations on large 7D
    space-time domains using GPU acceleration.
"""

from .bvp_cuda_block_processor import BVPCUDABlockProcessor

__all__ = ["BVPCUDABlockProcessor"]

