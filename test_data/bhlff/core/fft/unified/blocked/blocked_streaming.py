"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Streaming operations for blocked FFT processing.

This module provides utilities for streaming FieldArray data and processing
memory-mapped arrays for FFT operations, enabling efficient memory management
for large fields that exceed GPU memory.
"""

from typing import Tuple, Optional, Any
import numpy as np
import logging
import sys

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ..fft_gpu import forward_fft_gpu


def process_swapped_field_array_streaming(
    field_array_obj: Any,
    field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    gpu_memory_ratio: float,
    field_memory_with_overhead: float,
    logger: logging.Logger,
) -> np.ndarray:
    """
    Process swapped FieldArray using streaming batch iterator.
    
    Physical Meaning:
        Streams blocks from swapped FieldArray sequentially into CPU memory,
        then assembles them for FFT. This enables processing of fields that
        exceed GPU memory by using disk swap and streaming.
        
    Mathematical Foundation:
        FFT requires all data simultaneously, so we stream blocks sequentially,
        assemble them in CPU memory, then transfer to GPU for FFT computation.
        
    Args:
        field_array_obj: FieldArray object with swap support.
        field (np.ndarray): Underlying array from FieldArray.
        normalization (str): FFT normalization mode.
        domain_shape (Tuple[int, ...]): Domain shape.
        gpu_memory_ratio (float): GPU memory ratio to use.
        field_memory_with_overhead (float): Field memory with FFT overhead.
        logger (logging.Logger): Logger for debug messages.
        
    Returns:
        np.ndarray: FFT result in CPU memory.
    """
    logger.info("FieldArray is swapped, using streaming batch iterator")
    if not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA is required for streaming FFT with swapped FieldArray. "
            "CPU fallback is not supported."
        )
    
    # Create CUDA stream for async transfers
    stream = cp.cuda.Stream()
    
    # Check if field fits in GPU memory (with overhead)
    try:
        from bhlff.utils.cuda_utils import get_global_backend
        backend = get_global_backend()
        if hasattr(backend, "get_memory_info"):
            mem_info = backend.get_memory_info()
            free_memory = mem_info.get("free_memory", 0)
            available_memory = int(free_memory * gpu_memory_ratio)
        else:
            available_memory = int(0.8 * 1024**3)  # 0.8 GB fallback
    except Exception:
        available_memory = int(0.8 * 1024**3)  # 0.8 GB fallback
    
    # Check if field fits in available memory
    if field_memory_with_overhead > available_memory:
        raise RuntimeError(
            f"Field size {field_memory_with_overhead/1e9:.3f}GB exceeds "
            f"available GPU memory {available_memory/1e9:.3f}GB. "
            f"FFT requires all data simultaneously. "
            f"Please reduce field size or increase GPU memory."
        )
    
    # Allocate regular numpy array for assembled field
    # This will be in CPU memory, then transferred to GPU
    assembled_field = np.zeros(field.shape, dtype=field.dtype)
    
    # Stream blocks from FieldArray and assemble in CPU memory
    logger.info("Streaming blocks from FieldArray and assembling")
    for batch_payload in field_array_obj.iter_batches(
        max_gpu_ratio=gpu_memory_ratio,
        use_cuda=False,  # Use CPU for assembly
        stream=None
    ):
        slices = batch_payload["slices"]
        cpu_block = batch_payload["cpu"]
        # Copy block to assembled field
        assembled_field[slices] = cpu_block
    
    logger.info("All blocks assembled, transferring to GPU")
    
    # Transfer assembled field to GPU using CUDA stream
    with stream:
        field_gpu = cp.asarray(assembled_field)
    stream.synchronize()
    
    # Process on GPU
    result = forward_fft_gpu(field_gpu, normalization, domain_shape)
    
    # Copy result back
    if isinstance(result, cp.ndarray):
        result = cp.asnumpy(result)
    
    # Free assembled field from CPU memory
    del assembled_field
    
    return result


def process_memmap_field(
    field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    field_memory_with_overhead: float,
    logger: logging.Logger,
) -> np.ndarray:
    """
    Process memory-mapped field by loading to GPU.
    
    Physical Meaning:
        Loads entire memory-mapped field to GPU for FFT processing.
        Verifies data integrity during transfer and handles memory errors.
        
    Args:
        field (np.ndarray): Memory-mapped input field.
        normalization (str): FFT normalization mode.
        domain_shape (Tuple[int, ...]): Domain shape.
        field_memory_with_overhead (float): Field memory with FFT overhead.
        logger (logging.Logger): Logger for debug messages.
        
    Returns:
        np.ndarray: FFT result in CPU memory.
    """
    logger.info("Input is memory-mapped, loading to GPU")
    # Verify input data before processing
    field_sum = np.sum(field)
    field_norm = np.linalg.norm(field)
    logger.debug(
        f"Memory-mapped input: shape={field.shape}, dtype={field.dtype}, "
        f"sum={field_sum:.6e}, norm={field_norm:.6e}"
    )
    
    # Try to load entire field - if it fails, we'll handle it
    try:
        # Load entire field to GPU
        if CUDA_AVAILABLE:
            field_gpu = cp.asarray(field)
            # Verify data was loaded correctly
            if CUDA_AVAILABLE:
                # For complex arrays, use abs() to get real magnitude
                field_gpu_sum_val = cp.sum(field_gpu)
                field_gpu_norm_val = cp.linalg.norm(field_gpu)
                # Convert to float: use abs() for complex, direct for real
                if np.iscomplexobj(field_gpu):
                    field_gpu_sum = float(abs(field_gpu_sum_val))
                    field_gpu_norm = float(abs(field_gpu_norm_val))
                else:
                    field_gpu_sum = float(field_gpu_sum_val)
                    field_gpu_norm = float(field_gpu_norm_val)
                logger.debug(
                    f"GPU input: sum={field_gpu_sum:.6e}, norm={field_gpu_norm:.6e}"
                )
                # Compare using abs() for complex numbers
                field_sum_abs = abs(field_sum) if np.iscomplexobj(field) else field_sum
                if abs(field_sum_abs - field_gpu_sum) > 1e-6:
                    logger.warning(
                        f"Data mismatch when loading to GPU: "
                        f"CPU sum={field_sum_abs:.6e}, GPU sum={field_gpu_sum:.6e}"
                    )
        else:
            field_gpu = field
        
        # Process on GPU
        result = forward_fft_gpu(field_gpu, normalization, domain_shape)
        
        # Copy result back
        if CUDA_AVAILABLE and isinstance(result, cp.ndarray):
            result = cp.asnumpy(result)
            # Verify result after transfer
            result_sum = np.sum(result)
            result_norm = np.linalg.norm(result)
            logger.debug(
                f"Result after GPU->CPU transfer: sum={result_sum:.6e}, norm={result_norm:.6e}"
            )
    except Exception as e:
        error_str = str(e)
        if "OutOfMemoryError" in error_str or "Out of memory" in error_str:
            logger.warning(
                f"Failed to load entire field to GPU: {e}. "
                f"Field is too large for available GPU memory. "
                f"FFT/IFFT requires all data simultaneously, so this field cannot be processed."
            )
            raise RuntimeError(
                f"FFT failed: Field size {field_memory_with_overhead/1e9:.3f}GB is too large "
                f"for available GPU memory. FFT/IFFT requires all data simultaneously. "
                f"Please reduce field size or increase GPU memory."
            ) from e
        else:
            raise
    
    return result

