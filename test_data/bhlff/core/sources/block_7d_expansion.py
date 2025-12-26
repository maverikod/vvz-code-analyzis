"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D block expansion utilities for explicit construction from 3D spatial blocks.

This module provides utilities for explicit 7D block construction from 3D spatial
blocks, replacing blind broadcasting with explicit phase and time dimension
expansion. CUDA is required - no CPU fallback. Uses optimized GPU vectorization.

Physical Meaning:
    In 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, spatial blocks need to be expanded
    to include phase and temporal dimensions. This module provides explicit
    expansion that respects 7D dimensionality and avoids unintended broadcasting.

Mathematical Foundation:
    For 3D spatial block with shape (N_x, N_y, N_z), explicit 7D expansion:
    - Spatial dimensions: (N_x, N_y, N_z) preserved
    - Phase dimensions: (N_φ₁, N_φ₂, N_φ₃) added via outer product
    - Temporal dimension: (N_t) added via outer product
    Result: (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)

Example:
    >>> spatial_block = np.ones((8, 8, 8))
    >>> block_7d = expand_spatial_to_7d(spatial_block, N_phi=4, N_t=8)
    >>> assert block_7d.shape == (8, 8, 8, 4, 4, 4, 8)
"""

import numpy as np
from typing import Tuple, Optional, Union
import logging

logger = logging.getLogger(__name__)

# Try to import CUDA
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


def compute_optimal_7d_block_size(
    N_phi: int,
    N_t: int,
    dtype: type = np.complex128,
    use_cuda: bool = False,
    overhead_factor: float = 5.0,
) -> Tuple[int, int]:
    """
    Compute optimal block size for 7D expansion with 80% GPU memory usage.

    Physical Meaning:
        Calculates optimal phase and time block sizes for 7D expansion that
        use 80% of available GPU memory, ensuring efficient memory usage
        while avoiding OOM errors. Preserves 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For 7D block expansion:
        - Available memory: 80% of free GPU memory
        - Block size: (available_memory / (bytes_per_element * overhead_factor)) ^ (1/7)
        - Ensures blocks fit in GPU memory while preserving 7D structure

    Args:
        N_phi (int): Number of grid points per phase dimension.
        N_t (int): Number of grid points for temporal dimension.
        dtype (type): Data type for memory calculation (default: complex128 = 16 bytes).
        use_cuda (bool): Whether to use CUDA for memory calculation.
        overhead_factor (float): Memory overhead factor for operations (default 5.0).

    Returns:
        Tuple[int, int]: Optimal (N_phi_block, N_t_block) for 7D expansion.
    """
    # CUDA is required - no CPU fallback
    if not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA is required for 7D block expansion. "
            "CPU fallback is not supported. Please ensure CUDA is properly configured."
        )
    
    if not use_cuda:
        raise ValueError(
            "use_cuda must be True. CPU fallback is not supported."
        )

    try:
        # Get GPU memory info
        mem_info = cp.cuda.runtime.memGetInfo()
        free_memory_bytes = mem_info[0]

        # Use 80% of free memory
        available_memory_bytes = int(free_memory_bytes * 0.8)

        # Memory per element
        bytes_per_element = np.dtype(dtype).itemsize

        # Maximum elements per 7D block
        max_elements_per_block = available_memory_bytes // (
            bytes_per_element * overhead_factor
        )

        # For 7D expansion, we have 3 spatial dims + 3 phase dims + 1 time dim
        # Calculate base block size per dimension
        elements_per_dim_base = max_elements_per_block ** (1.0 / 7.0)

        # Phase dimensions: use moderate blocks (1.0x base)
        N_phi_block = max(4, min(int(elements_per_dim_base), N_phi))

        # Temporal dimension: use smaller blocks (0.8x base) for sequential access
        N_t_block = max(4, min(int(elements_per_dim_base * 0.8), N_t))

        logger.debug(
            f"Optimal 7D block size: N_phi={N_phi_block}, N_t={N_t_block} "
            f"(available GPU memory: {available_memory_bytes / 1e9:.2f} GB, using 80%)"
        )

        return (N_phi_block, N_t_block)

    except Exception as e:
        logger.warning(
            f"Failed to compute optimal 7D block size: {e}, using full dimensions"
        )
        return (N_phi, N_t)


def expand_spatial_to_7d(
    spatial_block: np.ndarray,
    N_phi: int,
    N_t: int,
    phase_coords: Optional[np.ndarray] = None,
    time_coords: Optional[np.ndarray] = None,
    use_cuda: bool = False,
    optimize_block_size: bool = True,
) -> np.ndarray:
    """
    Explicitly expand 3D spatial block to 7D with phase and time dimensions.

    Physical Meaning:
        Expands a 3D spatial block (N_x, N_y, N_z) to 7D space-time
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ by explicitly adding phase and temporal dimensions.
        This replaces blind broadcasting with explicit construction that respects
        the 7D structure of the phase field theory. For large blocks, uses
        block-wise processing to manage memory constraints (80% GPU memory limit).

    Mathematical Foundation:
        For 3D spatial block a(x,y,z), creates 7D block:
        a_7d(x, y, z, φ₁, φ₂, φ₃, t) = a(x, y, z) ⊗ 1_φ₁ ⊗ 1_φ₂ ⊗ 1_φ₃ ⊗ 1_t
        where ⊗ is outer product and 1_φᵢ, 1_t are unit vectors in phase/time.
        For large blocks, processes in chunks preserving 7D structure.

    Args:
        spatial_block (np.ndarray): 3D spatial block with shape (N_x, N_y, N_z).
        N_phi (int): Number of grid points per phase dimension.
        N_t (int): Number of grid points for temporal dimension.
        phase_coords (Optional[np.ndarray]): Phase coordinate arrays for
            explicit coordinate-dependent expansion. If None, uses uniform expansion.
        time_coords (Optional[np.ndarray]): Time coordinate array for
            explicit coordinate-dependent expansion. If None, uses uniform expansion.
        use_cuda (bool): Whether to use CUDA for expansion (if available).
        optimize_block_size (bool): Whether to optimize block size for 80% GPU memory.

    Returns:
        np.ndarray: 7D block with shape (N_x, N_y, N_z, N_phi, N_phi, N_phi, N_t).

    Raises:
        ValueError: If spatial_block is not 3D or shape is invalid.
    """
    if spatial_block.ndim != 3:
        raise ValueError(
            f"Expected 3D spatial block, got {spatial_block.ndim}D array "
            f"with shape {spatial_block.shape}"
        )

    N_x, N_y, N_z = spatial_block.shape

    # CUDA is required - no CPU fallback
    if not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA is required for 7D block expansion. "
            "CPU fallback is not supported. Please ensure CUDA is properly configured."
        )
    
    if not use_cuda:
        raise ValueError(
            "use_cuda must be True. CPU fallback is not supported."
        )
    
    # Use CUDA for expansion
    from .block_7d_expansion_cuda import expand_spatial_to_7d_cuda

    return expand_spatial_to_7d_cuda(
        spatial_block,
        N_phi,
        N_t,
        phase_coords,
        time_coords,
        optimize_block_size=optimize_block_size,
    )


def expand_block_to_7d_explicit(
    block: np.ndarray,
    target_shape: Tuple[int, ...],
    block_start: Optional[Tuple[int, ...]] = None,
    use_cuda: bool = False,
) -> np.ndarray:
    """
    Explicitly expand block to 7D target shape with concrete phase/time extents.

    Physical Meaning:
        Expands a block (which may be 3D spatial or partial 7D) to full 7D shape
        with explicit phase and time dimensions, respecting the 7D structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        For block with shape (B_x, B_y, B_z, ...), expands to target 7D shape:
        (B_x, B_y, B_z, B_φ₁, B_φ₂, B_φ₃, B_t)
        where B_φᵢ and B_t are extracted from target_shape and block_start.

    Args:
        block (np.ndarray): Input block (3D spatial or partial 7D).
        target_shape (Tuple[int, ...]): Target 7D shape (N_x, N_y, N_z, N_phi, N_phi, N_phi, N_t).
        block_start (Optional[Tuple[int, ...]]): Starting indices of block in target domain.
            Used to extract phase/time extents for this specific block.
        use_cuda (bool): Whether to use CUDA for expansion.

    Returns:
        np.ndarray: Expanded 7D block matching target_shape dimensions.

    Raises:
        ValueError: If target_shape is not 7D or block dimensions are incompatible.
    """
    if len(target_shape) != 7:
        raise ValueError(
            f"Target shape must be 7D, got {len(target_shape)}D: {target_shape}"
        )

    N_x, N_y, N_z, N_phi, N_phi2, N_phi3, N_t = target_shape

    if N_phi != N_phi2 or N_phi != N_phi3:
        raise ValueError(
            f"Phase dimensions must be equal, got ({N_phi}, {N_phi2}, {N_phi3})"
        )

    # Extract phase and time extents for this block
    if block_start is not None:
        # Extract phase and time block extents from block_start
        # This allows generating only the needed phase/time slice
        phase_start = block_start[3] if len(block_start) > 3 else 0
        phase_end = phase_start + N_phi
        time_start = block_start[6] if len(block_start) > 6 else 0
        time_end = time_start + N_t
    else:
        # Use full phase and time extents
        phase_start = 0
        phase_end = N_phi
        time_start = 0
        time_end = N_t

    # Determine block dimensions
    block_ndim = block.ndim

    if block_ndim == 3:
        # 3D spatial block: expand to 7D
        return expand_spatial_to_7d(
            block,
            N_phi=phase_end - phase_start,
            N_t=time_end - time_start,
            use_cuda=use_cuda,
        )
    elif block_ndim == 7:
        # Already 7D: verify shape matches or expand as needed
        if block.shape == target_shape:
            return block
        else:
            # Partial 7D block: expand to full 7D with explicit construction
            # This handles the case where block is a subset of 7D domain
            # Use explicit 7D construction that respects M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ

            # Determine expansion strategy based on block dimensions
            block_shape = block.shape

            # Check if block needs expansion in spatial dimensions
            if block_shape[:3] != target_shape[:3]:
                # Spatial dimensions differ: need to expand spatial block first
                # Extract spatial block (first 3 dimensions)
                spatial_block = block[
                    :, :, :, 0, 0, 0, 0
                ]  # Take first phase/time slice
                # Expand to full 7D
                return expand_spatial_to_7d(
                    spatial_block,
                    N_phi=target_shape[3],
                    N_t=target_shape[6],
                    use_cuda=use_cuda,
                    optimize_block_size=True,
                )

            # Check if block needs expansion in phase/time dimensions only
            if block_shape[3:] != target_shape[3:]:
                # Phase/time dimensions differ: expand using explicit construction
                # Allocate full 7D array with explicit shape
                expanded = np.zeros(target_shape, dtype=block.dtype)

                # Copy block to appropriate location in expanded array
                # If block_start is provided, use it to determine position
                if block_start is not None and len(block_start) >= 7:
                    # Copy block to specific location
                    expanded[
                        block_start[0] : block_start[0] + block_shape[0],
                        block_start[1] : block_start[1] + block_shape[1],
                        block_start[2] : block_start[2] + block_shape[2],
                        block_start[3] : block_start[3] + block_shape[3],
                        block_start[4] : block_start[4] + block_shape[4],
                        block_start[5] : block_start[5] + block_shape[5],
                        block_start[6] : block_start[6] + block_shape[6],
                    ] = block
                else:
                    # Copy to origin (0,0,0,0,0,0,0)
                    expanded[
                        : block_shape[0],
                        : block_shape[1],
                        : block_shape[2],
                        : block_shape[3],
                        : block_shape[4],
                        : block_shape[5],
                        : block_shape[6],
                    ] = block

                return expanded
            else:
                # Shape matches but might be a different array: return as-is or copy
                return block
    else:
        raise ValueError(
            f"Cannot expand {block_ndim}D block to 7D. "
            f"Expected 3D spatial or 7D block, got shape {block.shape}"
        )


def generate_7d_block_on_device(
    spatial_block: np.ndarray,
    N_phi: int,
    N_t: int,
    domain: "Domain",
    use_cuda: bool = True,
) -> "cp.ndarray":
    """
    Generate 7D block directly on GPU with explicit construction.

    Physical Meaning:
        Generates 7D block directly on GPU with explicit phase and time dimensions,
        avoiding unnecessary transfers and respecting 7D structure.
        CUDA is required - no CPU fallback.

    Mathematical Foundation:
        Creates 7D block a(x, y, z, φ₁, φ₂, φ₃, t) from 3D spatial block a(x, y, z)
        using explicit construction that respects the 7D space-time structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Args:
        spatial_block (np.ndarray): 3D spatial block (N_x, N_y, N_z).
        N_phi (int): Number of grid points per phase dimension.
        N_t (int): Number of grid points for temporal dimension.
        domain (Domain): Domain object with 7D structure information.
        use_cuda (bool): Must be True. CUDA is required.

    Returns:
        cp.ndarray: 7D block on GPU with shape (N_x, N_y, N_z, N_phi, N_phi, N_phi, N_t).

    Raises:
        RuntimeError: If CUDA is not available.
        ValueError: If use_cuda is False.
    """
    # CUDA is required - no CPU fallback
    if not CUDA_AVAILABLE:
        raise RuntimeError(
            "CUDA is required for 7D block generation. "
            "CPU fallback is not supported. Please ensure CUDA is properly configured."
        )
    
    if not use_cuda:
        raise ValueError(
            "use_cuda must be True. CPU fallback is not supported."
        )
    
    # Use CUDA for expansion
    from .block_7d_expansion_cuda import expand_spatial_to_7d_cuda

    return expand_spatial_to_7d_cuda(spatial_block, N_phi, N_t)
