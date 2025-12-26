"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Backward compatibility module for BVP CUDA block processor.

This module provides backward compatibility for the old import path.
The actual implementation has been moved to bvp_cuda_block package.

Physical Meaning:
    Provides backward compatibility import for BVPCUDABlockProcessor.
    The actual implementation is in bvp_cuda_block package.

Example:
    >>> from bhlff.core.bvp.bvp_core.bvp_cuda_block_processor import BVPCUDABlockProcessor
    >>> bvp_processor = BVPCUDABlockProcessor(domain, config, block_size=8)
    >>> envelope = bvp_processor.solve_envelope_cuda_blocked(source)
"""

# Import from new package structure for backward compatibility
from .bvp_cuda_block import BVPCUDABlockProcessor

__all__ = ["BVPCUDABlockProcessor"]
