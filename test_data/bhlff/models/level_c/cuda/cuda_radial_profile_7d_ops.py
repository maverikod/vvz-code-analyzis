"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D radial profile computation operations for CUDA.

This module provides GPU-accelerated 7D radial profile computation operations
for Level C boundary analysis with block-based processing optimized for 80% GPU memory.

Physical Meaning:
    Implements 7D radial profile computation in space-time:
    A(r) = (1/Ω₆) ∫_S(r) |a(x)|² dS
    where S(r) is the 6-sphere surface at radius r in 7D space-time M₇,
    and Ω₆ = 16π³/15 is the surface area of unit 6-sphere.

Mathematical Foundation:
    For 7D field a(x₁, x₂, x₃, φ₁, φ₂, φ₃, t), computes radial distance:
    |x - x₀|² = (x-x₀)² + (y-y₀)² + (z-z₀)² + (φ₁-φ₁₀)² + (φ₂-φ₂₀)² + (φ₃-φ₃₀)² + (t-t₀)²
    Uses block-based processing to fit in 80% of available GPU memory.

Example:
    >>> amplitudes = compute_unblocked_cuda_7d(field_gpu, center_gpu, radii_gpu, shape, L, L_phi, L_t)
"""

from typing import Tuple
import numpy as np

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


def compute_unblocked_cuda_7d(
    field_gpu: "cp.ndarray",
    center_gpu: "cp.ndarray",
    radii_gpu: "cp.ndarray",
    shape: Tuple[int, ...],
    L: float,
    L_phi: float,
    L_t: float,
) -> "cp.ndarray":
    """
    Compute 7D radial profile without blocking (small fields).

    Physical Meaning:
        Computes radial profile for 7D field that fits entirely in GPU memory.
        Uses 7D radial distance: |x-x₀|² = Σᵢ (xᵢ - x₀ᵢ)² for i=1..7.

    Mathematical Foundation:
        Creates 7D coordinate meshgrid and computes distances:
        |x - x₀|² = (x-x₀)² + (y-y₀)² + (z-z₀)² + (φ₁-φ₁₀)² + (φ₂-φ₂₀)² + (φ₃-φ₃₀)² + (t-t₀)²

    Args:
        field_gpu (cp.ndarray): 7D field on GPU (float64/complex128).
        center_gpu (cp.ndarray): 7D center point on GPU (float64).
        radii_gpu (cp.ndarray): Radii on GPU (float64).
        shape (Tuple[int, ...]): 7D shape (N_x, N_y, N_z, N_phi1, N_phi2, N_phi3, N_t).
        L (float): Spatial domain size.
        L_phi (float): Phase domain size.
        L_t (float): Temporal domain size.

    Returns:
        cp.ndarray: Radial profile amplitudes on GPU (float64).
    """
    N_x, N_y, N_z, N_phi1, N_phi2, N_phi3, N_t = shape
    
    # Create 7D coordinate arrays on GPU
    x = cp.linspace(0, L, N_x, dtype=cp.float64)
    y = cp.linspace(0, L, N_y, dtype=cp.float64)
    z = cp.linspace(0, L, N_z, dtype=cp.float64)
    phi1 = cp.linspace(0, L_phi, N_phi1, dtype=cp.float64)
    phi2 = cp.linspace(0, L_phi, N_phi2, dtype=cp.float64)
    phi3 = cp.linspace(0, L_phi, N_phi3, dtype=cp.float64)
    t = cp.linspace(0, L_t, N_t, dtype=cp.float64)
    
    # Create 7D meshgrid
    X, Y, Z, Phi1, Phi2, Phi3, T = cp.meshgrid(
        x, y, z, phi1, phi2, phi3, t, indexing="ij"
    )
    
    # Compute 7D distance from center (vectorized GPU operations)
    dX = X - center_gpu[0]
    dY = Y - center_gpu[1]
    dZ = Z - center_gpu[2]
    dPhi1 = Phi1 - center_gpu[3]
    dPhi2 = Phi2 - center_gpu[4]
    dPhi3 = Phi3 - center_gpu[5]
    dT = T - center_gpu[6]
    
    # 7D radial distance squared
    distances_sq = (
        dX**2 + dY**2 + dZ**2 + dPhi1**2 + dPhi2**2 + dPhi3**2 + dT**2
    )
    distances = cp.sqrt(distances_sq)
    
    # Compute field amplitude squared (GPU operation)
    field_abs_sq = cp.abs(field_gpu) ** 2
    
    # GPU sync point before reduction loop
    cp.cuda.Stream.null.synchronize()
    
    # Compute profile for each radius
    num_radii = len(radii_gpu)
    amplitudes = cp.zeros(num_radii, dtype=cp.float64)
    
    # Shell thickness based on smallest grid spacing
    min_spacing = min(L / N_x, L / N_y, L / N_z, L_phi / N_phi1, L_t / N_t)
    shell_thickness = min_spacing / 2
    
    for i, r in enumerate(radii_gpu):
        # Create shell mask (vectorized)
        shell_mask = (distances >= (r - shell_thickness)) & (
            distances <= (r + shell_thickness)
        )
        
        # Compute amplitude in shell (vectorized reduction on GPU)
        shell_values = field_abs_sq[shell_mask]
        if shell_values.size > 0:
            amplitudes[i] = cp.sqrt(cp.mean(shell_values))
        else:
            amplitudes[i] = 0.0
    
    # GPU sync point: ensure all reductions complete
    cp.cuda.Stream.null.synchronize()
    
    return amplitudes


def compute_blocked_cuda_7d(
    field_gpu: "cp.ndarray",
    center_gpu: "cp.ndarray",
    radii_gpu: "cp.ndarray",
    shape: Tuple[int, ...],
    L: float,
    L_phi: float,
    L_t: float,
    block_size: int,
) -> "cp.ndarray":
    """
    Compute 7D radial profile using block-based processing on GPU.

    Physical Meaning:
        Computes radial profile for large 7D fields using block-based
        processing optimized for 80% GPU memory usage. Processes field
        in blocks to fit in GPU memory while maintaining 7D structure.

    Mathematical Foundation:
        Uses 7D radial distance computed per block:
        |x-x₀|² = Σᵢ (xᵢ - x₀ᵢ)² for i=1..7
        Blocks are processed sequentially to fit in GPU memory (80% limit).

    Args:
        field_gpu (cp.ndarray): 7D field on GPU (float64/complex128).
        center_gpu (cp.ndarray): 7D center point on GPU (float64).
        radii_gpu (cp.ndarray): Radii on GPU (float64).
        shape (Tuple[int, ...]): 7D shape (N_x, N_y, N_z, N_phi1, N_phi2, N_phi3, N_t).
        L (float): Spatial domain size.
        L_phi (float): Phase domain size.
        L_t (float): Temporal domain size.
        block_size (int): Block size per dimension (optimized for 80% GPU memory).

    Returns:
        cp.ndarray: Radial profile amplitudes on GPU (float64).
    """
    N_x, N_y, N_z, N_phi1, N_phi2, N_phi3, N_t = shape
    
    # Compute field amplitude squared (once, reused for all radii)
    field_abs_sq = cp.abs(field_gpu) ** 2
    
    # Compute profile for each radius
    num_radii = len(radii_gpu)
    amplitudes = cp.zeros(num_radii, dtype=cp.float64)
    
    # Shell thickness based on smallest grid spacing
    min_spacing = min(L / N_x, L / N_y, L / N_z, L_phi / N_phi1, L_t / N_t)
    shell_thickness = min_spacing / 2
    
    # Block sizes per dimension (optimized for 80% GPU memory)
    block_sizes = [
        min(block_size, N_x),
        min(block_size, N_y),
        min(block_size, N_z),
        min(block_size, N_phi1),
        min(block_size, N_phi2),
        min(block_size, N_phi3),
        min(block_size, N_t),
    ]
    
    num_blocks = [
        (N_x + block_sizes[0] - 1) // block_sizes[0],
        (N_y + block_sizes[1] - 1) // block_sizes[1],
        (N_z + block_sizes[2] - 1) // block_sizes[2],
        (N_phi1 + block_sizes[3] - 1) // block_sizes[3],
        (N_phi2 + block_sizes[4] - 1) // block_sizes[4],
        (N_phi3 + block_sizes[5] - 1) // block_sizes[5],
        (N_t + block_sizes[6] - 1) // block_sizes[6],
    ]
    
    # Create coordinate arrays (full size, reused)
    x = cp.linspace(0, L, N_x, dtype=cp.float64)
    y = cp.linspace(0, L, N_y, dtype=cp.float64)
    z = cp.linspace(0, L, N_z, dtype=cp.float64)
    phi1 = cp.linspace(0, L_phi, N_phi1, dtype=cp.float64)
    phi2 = cp.linspace(0, L_phi, N_phi2, dtype=cp.float64)
    phi3 = cp.linspace(0, L_phi, N_phi3, dtype=cp.float64)
    t = cp.linspace(0, L_t, N_t, dtype=cp.float64)
    
    # Process each radius
    for i_radius, r in enumerate(radii_gpu):
        total_amplitude = cp.float64(0.0)
        total_count = cp.int64(0)
        
        # Process 7D field in blocks
        for i in range(num_blocks[0]):
            for j in range(num_blocks[1]):
                for k in range(num_blocks[2]):
                    for l in range(num_blocks[3]):
                        for m in range(num_blocks[4]):
                            for n in range(num_blocks[5]):
                                for o in range(num_blocks[6]):
                                    # Compute block indices
                                    i_start = i * block_sizes[0]
                                    i_end = min(i_start + block_sizes[0], N_x)
                                    j_start = j * block_sizes[1]
                                    j_end = min(j_start + block_sizes[1], N_y)
                                    k_start = k * block_sizes[2]
                                    k_end = min(k_start + block_sizes[2], N_z)
                                    l_start = l * block_sizes[3]
                                    l_end = min(l_start + block_sizes[3], N_phi1)
                                    m_start = m * block_sizes[4]
                                    m_end = min(m_start + block_sizes[4], N_phi2)
                                    n_start = n * block_sizes[5]
                                    n_end = min(n_start + block_sizes[5], N_phi3)
                                    o_start = o * block_sizes[6]
                                    o_end = min(o_start + block_sizes[6], N_t)
                                    
                                    # Extract block coordinates
                                    x_block = x[i_start:i_end]
                                    y_block = y[j_start:j_end]
                                    z_block = z[k_start:k_end]
                                    phi1_block = phi1[l_start:l_end]
                                    phi2_block = phi2[m_start:m_end]
                                    phi3_block = phi3[n_start:n_end]
                                    t_block = t[o_start:o_end]
                                    
                                    # Create 7D meshgrid for block
                                    X_b, Y_b, Z_b, Phi1_b, Phi2_b, Phi3_b, T_b = (
                                        cp.meshgrid(
                                            x_block, y_block, z_block,
                                            phi1_block, phi2_block, phi3_block, t_block,
                                            indexing="ij"
                                        )
                                    )
                                    
                                    # Compute 7D distance from center for this block
                                    dX = X_b - center_gpu[0]
                                    dY = Y_b - center_gpu[1]
                                    dZ = Z_b - center_gpu[2]
                                    dPhi1 = Phi1_b - center_gpu[3]
                                    dPhi2 = Phi2_b - center_gpu[4]
                                    dPhi3 = Phi3_b - center_gpu[5]
                                    dT = T_b - center_gpu[6]
                                    
                                    distances_block_sq = (
                                        dX**2 + dY**2 + dZ**2 +
                                        dPhi1**2 + dPhi2**2 + dPhi3**2 + dT**2
                                    )
                                    distances_block = cp.sqrt(distances_block_sq)
                                    
                                    # Create shell mask
                                    shell_mask = (
                                        (distances_block >= (r - shell_thickness)) &
                                        (distances_block <= (r + shell_thickness))
                                    )
                                    
                                    # Extract field values in shell
                                    field_block = field_abs_sq[
                                        i_start:i_end,
                                        j_start:j_end,
                                        k_start:k_end,
                                        l_start:l_end,
                                        m_start:m_end,
                                        n_start:n_end,
                                        o_start:o_end,
                                    ]
                                    shell_values = field_block[shell_mask]
                                    
                                    if shell_values.size > 0:
                                        total_amplitude += cp.sum(shell_values)
                                        total_count += shell_values.size
                                    
                                    # Free block coordinate arrays to save memory
                                    del X_b, Y_b, Z_b, Phi1_b, Phi2_b, Phi3_b, T_b
                                    del dX, dY, dZ, dPhi1, dPhi2, dPhi3, dT
                                    del distances_block_sq, distances_block, shell_mask
        
        # GPU sync point after block processing for this radius
        cp.cuda.Stream.null.synchronize()
        
        # Compute average amplitude
        if total_count > 0:
            amplitudes[i_radius] = cp.sqrt(total_amplitude / total_count)
        else:
            amplitudes[i_radius] = 0.0
    
    # Final GPU sync point: ensure all reductions complete
    cp.cuda.Stream.null.synchronize()
    
    return amplitudes

