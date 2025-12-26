"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Forward FFT blocked processing.

This module provides forward FFT blocked processing functions.
FFT is a global operation that requires all data simultaneously.
This implementation processes the entire field at once, using
swap/memory-mapped arrays for memory management with maximum block sizes.
"""

from typing import Tuple
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
from .blocked_tiling import compute_optimal_7d_block_tiling
from .blocked_copy import copy_with_max_blocks
from .blocked_streaming import (
    process_swapped_field_array_streaming,
    process_memmap_field,
)


def forward_fft_blocked(
    field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    gpu_memory_ratio: float,
) -> np.ndarray:
    """
    Perform forward FFT with 7D block processing.
    
    Physical Meaning:
        Computes forward FFT in spectral space for 7D phase field using
        swap/memory-mapped arrays for memory management. FFT is a global
        operation that requires all data simultaneously, so we process
        the entire field at once, using swap for large fields.
    """
    if len(field.shape) == 7 and len(domain_shape) == 7:
        # 7D block processing - process entire field with swap support
        return _forward_fft_blocked_7d(field, normalization, domain_shape, gpu_memory_ratio)
    else:
        # Non-7D: process only last dimension
        t_len = field.shape[-1]
        block_tiling = compute_optimal_7d_block_tiling(field.shape, gpu_memory_ratio)
        block = block_tiling[-1] if len(block_tiling) > 0 else t_len
        out = np.empty_like(field)
        start = 0
        while start < t_len:
            end = min(t_len, start + block)
            slab = field[..., start:end]
            slab_shape = tuple(list(domain_shape[:-1]) + [slab.shape[-1]])
            out[..., start:end] = forward_fft_gpu(slab, normalization, slab_shape)
            start = end
        return out


def _forward_fft_blocked_7d(
    field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    gpu_memory_ratio: float,
) -> np.ndarray:
    """
    Perform forward FFT for 7D field using swap/memory-mapped arrays.
    
    Physical Meaning:
        Computes forward FFT for entire 7D phase field. FFT is a global
        operation requiring all data simultaneously. This implementation:
        - Processes entire field at once on GPU (if memory allows)
        - Uses memory-mapped arrays for input/output if field is too large
        - Uses maximum block sizes for swap operations (80% GPU memory)
        - Supports streaming from FieldArray with iter_batches for swapped fields
        - Ensures correct normalization using full domain_shape
        
    Mathematical Foundation:
        FFT is computed as: F(k) = Σ f(x) * exp(-2πi k·x / N)
        This requires all spatial points simultaneously, so we cannot
        split the field into independent windows. Instead, we use swap
        to manage memory while processing the entire field. For swapped
        FieldArray, we stream blocks sequentially into pinned memory,
        then assemble for FFT to simulate a contiguous array.
    """
    logger = logging.getLogger(__name__)
    
    # Check if field is FieldArray with swap support
    field_array_obj = None
    if hasattr(field, 'is_swapped') and hasattr(field, 'iter_batches'):
        # FieldArray with streaming support
        field_array_obj = field
        field = field.array  # Extract underlying array
        logger.info(
            f"FieldArray detected: is_swapped={field_array_obj.is_swapped}, "
            f"shape={field.shape}"
        )
    
    field_size_mb = field.nbytes / (1024**2)
    logger.info(
        f"_forward_fft_blocked_7d: processing entire field {field.shape} "
        f"({field_size_mb:.2f}MB) with swap support"
    )
    sys.stdout.flush()
    
    # Calculate field memory requirements
    field_elements = np.prod(field.shape)
    bytes_per_element = 16  # complex128 = 16 bytes
    field_memory_bytes = field_elements * bytes_per_element
    # FFT overhead: input + output + temp arrays = 4x
    field_memory_with_overhead = field_memory_bytes * 4.0
    
    # Check available GPU memory
    use_swap = False
    if CUDA_AVAILABLE:
        try:
            from bhlff.utils.cuda_utils import get_global_backend
            backend = get_global_backend()
            if hasattr(backend, "get_memory_info"):
                mem_info = backend.get_memory_info()
                free_memory = mem_info.get("free_memory", 0)
                total_memory = mem_info.get("total_memory", 0)
                
                logger.info(
                    f"GPU memory: free={free_memory/1e9:.3f}GB, total={total_memory/1e9:.3f}GB, "
                    f"field with overhead={field_memory_with_overhead/1e9:.3f}GB"
                )
                
                # Use swap if field with overhead exceeds 80% of free memory
                if field_memory_with_overhead > free_memory * 0.8:
                    use_swap = True
                    logger.info(
                        f"Field with overhead ({field_memory_with_overhead/1e9:.3f}GB) exceeds "
                        f"80% of free GPU memory ({free_memory/1e9:.3f}GB), using swap"
                    )
                else:
                    logger.info(
                        f"Field fits in GPU memory, processing directly "
                        f"(field={field_memory_with_overhead/1e9:.3f}GB, free={free_memory/1e9:.3f}GB)"
                    )
        except Exception as e:
            logger.warning(f"Failed to check GPU memory: {e}, using swap for safety")
            use_swap = True
    
    # Create output array - use swap if needed
    output_dtype = np.complex128  # Always complex for FFT output
    
    if use_swap or isinstance(field, np.memmap):
        # Use memory-mapped arrays for large fields
        from ..swap_manager import get_swap_manager
        swap_manager = get_swap_manager()
        
        # Create memory-mapped output array
        out = swap_manager.create_swap_array(
            shape=field.shape,
            dtype=output_dtype,
            array_id=f"fft_forward_{id(field)}"
        )
        
        logger.info(
            f"Created memory-mapped output array: shape={out.shape}, dtype={out.dtype}"
        )
    else:
        # Use regular array for small fields
        out = np.zeros(field.shape, dtype=output_dtype)
        logger.info(
            f"Created regular output array: shape={out.shape}, dtype={out.dtype}"
        )
    
    # Verify output array properties
    if not np.iscomplexobj(out):
        raise ValueError(
            f"Output array must be complex for FFT, got dtype {out.dtype}"
        )
    if out.shape != field.shape:
        raise ValueError(
            f"Output array shape mismatch: expected {field.shape}, got {out.shape}"
        )
    
    # CRITICAL: FFT is a global operation - process entire field at once
    # Use swap/memory-mapped arrays for memory management, but process all data together
    # However, if field is too large, we need to handle OutOfMemoryError gracefully
    # by using memory-mapped arrays and processing in chunks if necessary
    try:
        logger.info("Processing entire field with FFT (global operation)")
        sys.stdout.flush()
        
        # For swapped FieldArray, use streaming batch iterator
        if field_array_obj is not None and field_array_obj.is_swapped:
            result = process_swapped_field_array_streaming(
                field_array_obj=field_array_obj,
                field=field,
                normalization=normalization,
                domain_shape=domain_shape,
                gpu_memory_ratio=gpu_memory_ratio,
                field_memory_with_overhead=field_memory_with_overhead,
                logger=logger,
            )
        # For memory-mapped arrays, load to GPU
        elif isinstance(field, np.memmap):
            result = process_memmap_field(
                field=field,
                normalization=normalization,
                domain_shape=domain_shape,
                field_memory_with_overhead=field_memory_with_overhead,
                logger=logger,
            )
        else:
            # Regular array - process directly
            result = forward_fft_gpu(field, normalization, domain_shape)
        
        # Copy result to output array
        # Use maximum block size for swap operations (80% GPU memory)
        if isinstance(out, np.memmap) or isinstance(result, np.memmap):
            # For memory-mapped arrays, copy in large blocks
            copy_with_max_blocks(result, out, gpu_memory_ratio, logger)
        else:
            # For regular arrays, direct copy
            out[:] = result
        
        # Verify data integrity after copy
        if isinstance(result, np.ndarray) and isinstance(out, np.ndarray):
            if not np.allclose(result, out, rtol=1e-10, atol=1e-10):
                max_diff = np.max(np.abs(result - out))
                logger.error(
                    f"Data integrity check failed after copy: "
                    f"max difference = {max_diff:.2e}, "
                    f"result shape={result.shape}, out shape={out.shape}, "
                    f"result dtype={result.dtype}, out dtype={out.dtype}"
                )
                raise RuntimeError(
                    f"Data integrity check failed: max difference = {max_diff:.2e}"
                )
            else:
                logger.debug("Data integrity check passed after copy")
        
        logger.info("FFT completed successfully")
        sys.stdout.flush()
        
    except Exception as e:
        error_str = str(e)
        if "OutOfMemoryError" in error_str or "Out of memory" in error_str or "Insufficient GPU memory" in error_str:
            logger.error(
                f"FFT failed with memory error: {e}. "
                f"Field size: {field_memory_with_overhead/1e9:.3f}GB. "
                f"FFT/IFFT requires all data simultaneously, so this field cannot be processed with current GPU memory."
            )
            raise RuntimeError(
                f"FFT failed with memory error: {e}. "
                f"Cannot process field of size {field_memory_with_overhead/1e9:.3f}GB. "
                f"FFT/IFFT requires all data simultaneously. "
                f"Please reduce field size or increase GPU memory."
            ) from e
        else:
            raise
    
    # Flush if memory-mapped
    if isinstance(out, np.memmap):
        logger.info("Flushing memory-mapped output array")
        sys.stdout.flush()
        out.flush()
    
    # Final verification
    if np.any(np.isnan(out)) or np.any(np.isinf(out)):
        logger.warning(
            f"Output array contains NaN or Inf values: "
            f"NaN count={np.sum(np.isnan(out))}, Inf count={np.sum(np.isinf(out))}"
        )
    
    if not np.iscomplexobj(out):
        raise ValueError(
            f"Final output array must be complex, got dtype {out.dtype}"
        )
    
    logger.info(
        f"_forward_fft_blocked_7d: COMPLETE - output shape={out.shape}, dtype={out.dtype}"
    )
    sys.stdout.flush()
    
    return out
