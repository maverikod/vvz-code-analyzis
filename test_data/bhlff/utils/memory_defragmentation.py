"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Memory defragmentation utilities for BHLFF project.

This module provides memory defragmentation functionality for GPU and CPU
memory to prevent OOM errors even when sufficient free memory exists.

Physical Meaning:
    Provides memory defragmentation utilities to prevent memory fragmentation
    issues that can lead to OOM errors during long-running computations.

Mathematical Foundation:
    Memory defragmentation reorganizes memory allocation patterns to reduce
    fragmentation and maximize available contiguous memory blocks.

Example:
    >>> from bhlff.utils.memory_defragmentation import defragment_gpu_memory
    >>> defragment_gpu_memory()
"""

import logging
import gc

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


def defragment_gpu_memory() -> None:
    """
    Defragment GPU memory by freeing all blocks and synchronizing.
    
    Physical Meaning:
        Performs GPU memory defragmentation by freeing all memory pool
        blocks and forcing synchronization to ensure complete cleanup.
        This helps prevent OOM errors even when sufficient free memory exists.
    """
    if not CUDA_AVAILABLE:
        logger.warning("CUDA not available - cannot defragment GPU memory")
        return
    
    try:
        # Get memory pools
        mempool = cp.get_default_memory_pool()
        pinned_mempool = cp.get_default_pinned_memory_pool()
        
        # Free all blocks in memory pools
        mempool.free_all_blocks()
        pinned_mempool.free_all_blocks()
        
        # Force synchronization to ensure complete cleanup
        cp.cuda.Stream.null.synchronize()
        
        logger.info("GPU memory defragmentation completed")
    except Exception as e:
        logger.error(f"Failed to defragment GPU memory: {e}")


def defragment_cpu_memory() -> None:
    """
    Defragment CPU memory by forcing garbage collection.
    
    Physical Meaning:
        Performs CPU memory defragmentation by forcing garbage collection
        to free unused memory and optimize memory allocation patterns.
    """
    try:
        # Force garbage collection
        gc.collect()
        logger.info("CPU memory defragmentation completed")
    except Exception as e:
        logger.error(f"Failed to defragment CPU memory: {e}")


def defragment_all_memory() -> None:
    """
    Defragment both GPU and CPU memory.
    
    Physical Meaning:
        Performs defragmentation of both GPU and CPU memory to optimize
        memory allocation patterns and prevent fragmentation issues.
    """
    defragment_gpu_memory()
    defragment_cpu_memory()
    logger.info("Complete memory defragmentation completed")

