"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

GPU (CUDA) FFT helpers with physics and ortho normalization.

This module provides GPU-accelerated FFT operations for 7D phase field
calculations. For Level C code paths, CUDA is required with no CPU fallback.
All operations use explicit stream synchronization and block-based processing
for optimal GPU memory usage (80%).
"""

from typing import Tuple, Optional
import numpy as np
from bhlff.utils.cuda_utils import (
    get_global_backend,
    get_cuda_backend_required,
    CUDABackend,
)
from .volume import compute_volume_element

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


def forward_fft_gpu(
    field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    level_c_required: bool = False,
) -> np.ndarray:
    """
    Perform forward FFT on GPU with normalization.

    Physical Meaning:
        Computes forward FFT in spectral space for 7D phase field,
        preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. For Level C,
        GPU-only execution is enforced with no CPU fallback.

    Args:
        field (np.ndarray): Input field array.
        normalization (str): Normalization type ("ortho" or "physics").
        domain_shape (Tuple[int, ...]): Domain shape for normalization.
        level_c_required (bool): If True, requires CUDA backend (no CPU fallback).

    Returns:
        np.ndarray: FFT result with appropriate normalization.

    Raises:
        RuntimeError: If Level C requires CUDA but GPU memory is insufficient.
    """
    # For Level C, use get_cuda_backend_required() to ensure GPU-only execution
    if level_c_required:
        backend = get_cuda_backend_required()
    else:
        backend = get_global_backend()

    axes = tuple(range(field.ndim)) if field.ndim > 0 else None
    n_total = np.prod(domain_shape)

    # For Level C, no CPU fallback - raise error with guidance if memory insufficient
    if level_c_required:
        # Verify backend is CUDA
        if not isinstance(backend, CUDABackend):
            raise RuntimeError(
                "Level C requires CUDA backend. Use get_cuda_backend_required() "
                "instead of get_global_backend() for Level C code paths."
            )
        # Check memory and raise with guidance if insufficient
        try:
            mem = backend.get_memory_info()
            needed = field.nbytes * 4
            if needed > mem.get("free_memory", 0):
                from bhlff.utils.cuda_utils import raise_insufficient_memory_error

                raise raise_insufficient_memory_error(
                    required_memory=needed,
                    available_memory=mem.get("free_memory", 0),
                    operation_name="7D forward FFT (Level C)",
                    field_shape=field.shape,
                )
        except Exception as e:
            # If error is already raised_insufficient_memory_error, re-raise it
            if isinstance(e, RuntimeError) and "Insufficient GPU memory" in str(e):
                raise
            # Otherwise, let backend handle it
            pass
    # CUDA is required - no CPU fallback
    # If backend is not CUDA, raise error
    if not isinstance(backend, CUDABackend):
        raise RuntimeError(
            "CUDA backend is required for FFT operations. "
            "CPU fallback is not supported."
        )

    # STEP-BY-STEP LOGGING: Track every operation to identify hang points
    import logging
    import sys
    logger = logging.getLogger(__name__)
    
    # Step 1: Check memory before transfer
    if isinstance(backend, CUDABackend):
        try:
            mem_info = backend.get_memory_info()
            free_mb = mem_info.get("free_memory", 0) / (1024**2)
            total_mb = mem_info.get("total_memory", 0) / (1024**2)
            field_mb = field.nbytes / (1024**2)
            logger.info(
                f"[STEP 1] forward_fft_gpu: START - field {field.shape} ({field_mb:.2f}MB), "
                f"GPU: free={free_mb:.2f}MB/{total_mb:.2f}MB"
            )
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
    
    # Step 2: Transfer to GPU
    logger.info(f"[STEP 2] forward_fft_gpu: Transferring to GPU...")
    sys.stdout.flush()
    if CUDA_AVAILABLE and isinstance(field, cp.ndarray):
        field_gpu = field
        logger.info(f"[STEP 2] forward_fft_gpu: Field already on GPU (cupy array)")
    else:
        field_gpu = backend.array(field)
        logger.info(f"[STEP 2] forward_fft_gpu: Field transferred to GPU via backend.array()")
        # Verify it's actually on GPU
        if CUDA_AVAILABLE:
            assert isinstance(field_gpu, cp.ndarray), f"ERROR: Field not on GPU! Type: {type(field_gpu)}"
            logger.info(f"[STEP 2] forward_fft_gpu: Verified field is on GPU device {field_gpu.device}")
    sys.stdout.flush()
    
    # Step 3: Perform FFT on GPU
    logger.info(f"[STEP 3] forward_fft_gpu: Performing FFT on GPU using backend.fft()...")
    sys.stdout.flush()
    if CUDA_AVAILABLE:
        assert isinstance(field_gpu, cp.ndarray), f"ERROR: Input not on GPU before FFT! Type: {type(field_gpu)}"
    spec_gpu = backend.fft(field_gpu, axes=axes)
    if CUDA_AVAILABLE:
        assert isinstance(spec_gpu, cp.ndarray), f"ERROR: FFT result not on GPU! Type: {type(spec_gpu)}"
        logger.info(f"[STEP 3] forward_fft_gpu: FFT completed on GPU device {spec_gpu.device}")
    else:
        logger.info(f"[STEP 3] forward_fft_gpu: FFT completed")
    sys.stdout.flush()
    
    # Step 4: Normalization on GPU
    logger.info(f"[STEP 4] forward_fft_gpu: Applying normalization '{normalization}' on GPU...")
    sys.stdout.flush()
    # CRITICAL: Use cupy operations for GPU arrays, not numpy
    if CUDA_AVAILABLE and isinstance(spec_gpu, cp.ndarray):
        sqrt_n = cp.sqrt(n_total)  # Use cupy.sqrt for GPU
        logger.info(f"[STEP 4] forward_fft_gpu: Using cupy.sqrt for GPU normalization")
    else:
        # This should not happen if CUDA is properly configured
        raise RuntimeError(
            f"ERROR: spec_gpu is not a cupy array! Type: {type(spec_gpu)}, "
            f"CUDA_AVAILABLE: {CUDA_AVAILABLE}"
        )
    spec_gpu /= sqrt_n  # In-place division on GPU
    if normalization == "physics":
        vol = compute_volume_element(domain_shape)
        spec_gpu *= vol  # Multiplication on GPU
    elif normalization != "ortho":
        raise ValueError(f"Unsupported normalization type: {normalization}")
    logger.info(f"[STEP 4] forward_fft_gpu: Normalization completed on GPU")
    sys.stdout.flush()
    
    # Step 5: Transfer back to CPU (only at the end, all computation on GPU)
    logger.info(f"[STEP 5] forward_fft_gpu: Transferring result to CPU (all GPU ops completed)...")
    sys.stdout.flush()
    if CUDA_AVAILABLE:
        assert isinstance(spec_gpu, cp.ndarray), f"ERROR: Result not on GPU before transfer! Type: {type(spec_gpu)}"
        logger.info(f"[STEP 5] forward_fft_gpu: Result is on GPU device {spec_gpu.device}, transferring to CPU")
    result = backend.to_numpy(spec_gpu)
    logger.info(f"[STEP 5] forward_fft_gpu: Result transferred to CPU, shape: {result.shape}")
    sys.stdout.flush()
    
    # Step 6: Final memory check
    if isinstance(backend, CUDABackend):
        try:
            mem_info = backend.get_memory_info()
            free_mb = mem_info.get("free_memory", 0) / (1024**2)
            logger.info(
                f"[STEP 6] forward_fft_gpu: COMPLETE - GPU memory: free={free_mb:.2f}MB"
            )
            sys.stdout.flush()
        except Exception:
            pass
    
    return result


def inverse_fft_gpu(
    spectral_field: np.ndarray,
    normalization: str,
    domain_shape: Tuple[int, ...],
    level_c_required: bool = False,
) -> np.ndarray:
    """
    Perform inverse FFT on GPU with normalization.

    Physical Meaning:
        Computes inverse FFT from spectral space back to real space for 7D
        phase field, preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ. For Level C,
        GPU-only execution is enforced with no CPU fallback.

    Args:
        spectral_field (np.ndarray): Input spectral field array.
        normalization (str): Normalization type ("ortho" or "physics").
        domain_shape (Tuple[int, ...]): Domain shape for normalization.
        level_c_required (bool): If True, requires CUDA backend (no CPU fallback).

    Returns:
        np.ndarray: Inverse FFT result with appropriate normalization.

    Raises:
        RuntimeError: If Level C requires CUDA but GPU memory is insufficient.
    """
    # For Level C, use get_cuda_backend_required() to ensure GPU-only execution
    if level_c_required:
        backend = get_cuda_backend_required()
    else:
        backend = get_global_backend()

    axes = tuple(range(spectral_field.ndim)) if spectral_field.ndim > 0 else None
    n_total = np.prod(domain_shape)

    # For Level C, no CPU fallback - raise error with guidance if memory insufficient
    if level_c_required:
        # Verify backend is CUDA
        if not isinstance(backend, CUDABackend):
            raise RuntimeError(
                "Level C requires CUDA backend. Use get_cuda_backend_required() "
                "instead of get_global_backend() for Level C code paths."
            )
        # Check memory and raise with guidance if insufficient
        try:
            mem = backend.get_memory_info()
            needed = spectral_field.nbytes * 4
            if needed > mem.get("free_memory", 0):
                from bhlff.utils.cuda_utils import raise_insufficient_memory_error

                raise raise_insufficient_memory_error(
                    required_memory=needed,
                    available_memory=mem.get("free_memory", 0),
                    operation_name="7D inverse FFT (Level C)",
                    field_shape=spectral_field.shape,
                )
        except Exception as e:
            # If error is already raised_insufficient_memory_error, re-raise it
            if isinstance(e, RuntimeError) and "Insufficient GPU memory" in str(e):
                raise
            # Otherwise, let backend handle it
            pass
    # CUDA is required - no CPU fallback
    # If backend is not CUDA, raise error
    if not isinstance(backend, CUDABackend):
        raise RuntimeError(
            "CUDA backend is required for FFT operations. "
            "CPU fallback is not supported."
        )

    # STEP-BY-STEP LOGGING: Track every operation to identify hang points
    import logging
    import sys
    logger = logging.getLogger(__name__)
    
    logger.info(f"[STEP 1] inverse_fft_gpu: START - field {spectral_field.shape}")
    sys.stdout.flush()
    
    logger.info(f"[STEP 2] inverse_fft_gpu: Transferring to GPU...")
    sys.stdout.flush()
    spec_gpu = backend.array(spectral_field)
    logger.info(f"[STEP 2] inverse_fft_gpu: Field transferred to GPU")
    sys.stdout.flush()
    
    if normalization == "ortho":
        logger.info(f"[STEP 3] inverse_fft_gpu: Applying ortho normalization...")
        sys.stdout.flush()
        # Use backend's sqrt to ensure correct dtype (cp.sqrt for GPU, np.sqrt for CPU)
        if CUDA_AVAILABLE and isinstance(spec_gpu, cp.ndarray):
            sqrt_n = cp.sqrt(n_total)
        else:
            sqrt_n = np.sqrt(n_total)
        spec_gpu = spec_gpu * sqrt_n
        logger.info(f"[STEP 4] inverse_fft_gpu: Performing IFFT...")
        sys.stdout.flush()
        out_gpu = backend.ifft(spec_gpu, axes=axes)
        logger.info(f"[STEP 5] inverse_fft_gpu: Transferring result to CPU...")
        sys.stdout.flush()
        result = backend.to_numpy(out_gpu)
        logger.info(f"[STEP 6] inverse_fft_gpu: COMPLETE")
        sys.stdout.flush()
        return result
    if normalization == "physics":
        logger.info(f"[STEP 3] inverse_fft_gpu: Applying physics normalization...")
        sys.stdout.flush()
        vol = compute_volume_element(domain_shape)
        # Use backend's sqrt to ensure correct dtype (cp.sqrt for GPU, np.sqrt for CPU)
        if CUDA_AVAILABLE and isinstance(spec_gpu, cp.ndarray):
            sqrt_n = cp.sqrt(n_total)
        else:
            sqrt_n = np.sqrt(n_total)
        spec_gpu = spec_gpu / vol * sqrt_n
        logger.info(f"[STEP 4] inverse_fft_gpu: Performing IFFT...")
        sys.stdout.flush()
        out = backend.to_numpy(backend.ifft(spec_gpu, axes=axes))
        logger.info(f"[STEP 5] inverse_fft_gpu: Applying phase correction...")
        sys.stdout.flush()
        first = out.reshape(-1)[0]
        if np.abs(first) > 0:
            out = out * np.exp(-1j * np.angle(first))
        logger.info(f"[STEP 6] inverse_fft_gpu: Applying normalization...")
        sys.stdout.flush()
        norm = np.linalg.norm(out)
        if norm > 0:
            out = out / norm
        logger.info(f"[STEP 7] inverse_fft_gpu: COMPLETE")
        sys.stdout.flush()
        return out
    raise ValueError(f"Unsupported normalization type: {normalization}")
