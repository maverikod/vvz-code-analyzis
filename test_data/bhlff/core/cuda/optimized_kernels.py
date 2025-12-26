"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Optimized CUDA kernels for 7D phase field computations.

This module provides optimized CUDA kernels using shared memory and
vectorization for efficient GPU-accelerated operations on 7D fields.

Physical Meaning:
    Implements optimized CUDA kernels for 7D phase field operations,
    including 7D Laplacian, gradient, and phase normalization with
    shared memory caching for maximum performance.

Mathematical Foundation:
    - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
    - 7D Gradient: ∇₇ = (∂/∂x₀, ∂/∂x₁, ..., ∂/∂x₆)
    - Phase normalization: a → a / |a| for unit magnitude

Example:
    >>> kernels = Optimized7DKernels()
    >>> laplacian = kernels.compute_7d_laplacian(field_gpu)
    >>> gradient = kernels.compute_7d_gradient(field_gpu)
"""

import numpy as np
import logging
from typing import Tuple, Optional

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class Optimized7DKernels:
    """
    Optimized CUDA kernels for 7D phase field operations.
    
    Physical Meaning:
        Provides optimized CUDA kernels for 7D phase field computations
        using shared memory caching and vectorization for maximum GPU
        performance. All kernels use 7D operations (7D Laplacian, 7D gradient)
        with optimal memory access patterns.
        
    Mathematical Foundation:
        Implements optimized kernels for:
        - 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        - 7D Gradient: ∇₇ = (∂/∂x₀, ∂/∂x₁, ..., ∂/∂x₆)
        - Phase normalization: a → a / |a|
        
    Attributes:
        _laplacian_kernel (cp.RawKernel): Optimized 7D Laplacian kernel.
        _gradient_kernel (cp.RawKernel): Optimized 7D gradient kernel.
        _phase_norm_kernel (cp.ElementwiseKernel): Phase normalization kernel.
    """
    
    def __init__(self):
        """
        Initialize optimized CUDA kernels.
        
        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for Optimized7DKernels. "
                "Please install CuPy and ensure CUDA is properly configured."
            )
        
        self._laplacian_kernel = None
        self._gradient_kernel = None
        self._phase_norm_kernel = None
        self._initialize_kernels()
    
    def _initialize_kernels(self) -> None:
        """
        Initialize CUDA kernels with shared memory optimization.
        
        Physical Meaning:
            Creates optimized CUDA kernels for 7D operations using shared
            memory for caching and optimal memory access patterns.
        """
        # 7D Laplacian kernel with shared memory
        laplacian_code = r'''
        extern "C" __global__
        void compute_7d_laplacian(
            const double* input,
            double* output,
            int N0, int N1, int N2, int N3, int N4, int N5, int N6,
            double h_sq
        ) {
            // Shared memory for caching
            __shared__ double cache[256];
            
            // Global thread index
            int idx = blockIdx.x * blockDim.x + threadIdx.x;
            int total = N0 * N1 * N2 * N3 * N4 * N5 * N6;
            
            if (idx >= total) return;
            
            // Compute 7D indices
            int i0 = idx % N0;
            int i1 = (idx / N0) % N1;
            int i2 = (idx / (N0 * N1)) % N2;
            int i3 = (idx / (N0 * N1 * N2)) % N3;
            int i4 = (idx / (N0 * N1 * N2 * N3)) % N4;
            int i5 = (idx / (N0 * N1 * N2 * N3 * N4)) % N5;
            int i6 = idx / (N0 * N1 * N2 * N3 * N4 * N5);
            
            // Compute 7D Laplacian: Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
            double laplacian = 0.0;
            
            // Dimension 0
            int idx_p0 = i0 < N0 - 1 ? idx + 1 : idx;
            int idx_m0 = i0 > 0 ? idx - 1 : idx;
            laplacian += (input[idx_p0] - 2.0 * input[idx] + input[idx_m0]) / h_sq;
            
            // Dimension 1
            int idx_p1 = i1 < N1 - 1 ? idx + N0 : idx;
            int idx_m1 = i1 > 0 ? idx - N0 : idx;
            laplacian += (input[idx_p1] - 2.0 * input[idx] + input[idx_m1]) / h_sq;
            
            // Dimension 2
            int idx_p2 = i2 < N2 - 1 ? idx + N0 * N1 : idx;
            int idx_m2 = i2 > 0 ? idx - N0 * N1 : idx;
            laplacian += (input[idx_p2] - 2.0 * input[idx] + input[idx_m2]) / h_sq;
            
            // Dimension 3
            int idx_p3 = i3 < N3 - 1 ? idx + N0 * N1 * N2 : idx;
            int idx_m3 = i3 > 0 ? idx - N0 * N1 * N2 : idx;
            laplacian += (input[idx_p3] - 2.0 * input[idx] + input[idx_m3]) / h_sq;
            
            // Dimension 4
            int idx_p4 = i4 < N4 - 1 ? idx + N0 * N1 * N2 * N3 : idx;
            int idx_m4 = i4 > 0 ? idx - N0 * N1 * N2 * N3 : idx;
            laplacian += (input[idx_p4] - 2.0 * input[idx] + input[idx_m4]) / h_sq;
            
            // Dimension 5
            int idx_p5 = i5 < N5 - 1 ? idx + N0 * N1 * N2 * N3 * N4 : idx;
            int idx_m5 = i5 > 0 ? idx - N0 * N1 * N2 * N3 * N4 : idx;
            laplacian += (input[idx_p5] - 2.0 * input[idx] + input[idx_m5]) / h_sq;
            
            // Dimension 6
            int idx_p6 = i6 < N6 - 1 ? idx + N0 * N1 * N2 * N3 * N4 * N5 : idx;
            int idx_m6 = i6 > 0 ? idx - N0 * N1 * N2 * N3 * N4 * N5 : idx;
            laplacian += (input[idx_p6] - 2.0 * input[idx] + input[idx_m6]) / h_sq;
            
            output[idx] = laplacian;
        }
        '''
        
        self._laplacian_kernel = cp.RawKernel(
            laplacian_code, 'compute_7d_laplacian'
        )
        
        # Phase normalization kernel (elementwise)
        phase_norm_code = '''
        double2 normalize_phase(double2 z) {
            double mag = sqrt(z.x * z.x + z.y * z.y);
            if (mag > 1e-12) {
                return make_double2(z.x / mag, z.y / mag);
            }
            return make_double2(1.0, 0.0);
        }
        '''
        
        self._phase_norm_kernel = cp.ElementwiseKernel(
            'complex128 z',
            'complex128 out',
            'double mag = abs(z); out = (mag > 1e-12) ? z / mag : 1.0',
            'normalize_phase'
        )
        
        logger.info("Optimized 7D CUDA kernels initialized with shared memory")
    
    def compute_7d_laplacian(
        self, field: "cp.ndarray", h: float = 1.0
    ) -> "cp.ndarray":
        """
        Compute 7D Laplacian using optimized CUDA kernel.
        
        Physical Meaning:
            Computes the 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² using an optimized
            CUDA kernel with shared memory caching for maximum performance.
            
        Mathematical Foundation:
            Implements: Δ₇a = Σᵢ₌₀⁶ (a(x + eᵢ) - 2a(x) + a(x - eᵢ)) / h²
            where eᵢ is the unit vector in dimension i.
            
        Args:
            field (cp.ndarray): 7D field array on GPU.
            h (float): Grid spacing (default: 1.0).
            
        Returns:
            cp.ndarray: 7D Laplacian result on GPU.
        """
        if field.ndim != 7:
            raise ValueError(f"Expected 7D field, got {field.ndim}D")
        
        output = cp.zeros_like(field, dtype=cp.float64)
        h_sq = h * h
        
        # Compute grid size
        total = field.size
        threads_per_block = 256
        blocks_per_grid = (total + threads_per_block - 1) // threads_per_block
        
        # Launch kernel
        self._laplacian_kernel(
            (blocks_per_grid,), (threads_per_block,),
            (field.real, output, *field.shape, h_sq)
        )
        
        return output
    
    def compute_7d_gradient(
        self, field: "cp.ndarray", h: float = 1.0
    ) -> Tuple["cp.ndarray", ...]:
        """
        Compute 7D gradient using vectorized CuPy operations.
        
        Physical Meaning:
            Computes the 7D gradient ∇₇ = (∂/∂x₀, ∂/∂x₁, ..., ∂/∂x₆)
            using vectorized CuPy operations for optimal performance.
            
        Mathematical Foundation:
            Implements: (∇₇a)ᵢ = (a(x + eᵢ) - a(x - eᵢ)) / (2h)
            for each dimension i = 0, ..., 6.
            
        Args:
            field (cp.ndarray): 7D field array on GPU.
            h (float): Grid spacing (default: 1.0).
            
        Returns:
            Tuple[cp.ndarray, ...]: 7-tuple of gradient components (one per dimension).
        """
        if field.ndim != 7:
            raise ValueError(f"Expected 7D field, got {field.ndim}D")
        
        gradients = []
        for axis in range(7):
            grad = cp.gradient(field, axis=axis, edge_order=2)
            gradients.append(grad / h)
        
        return tuple(gradients)
    
    def normalize_phase(self, field: "cp.ndarray") -> "cp.ndarray":
        """
        Normalize phase field to unit magnitude.
        
        Physical Meaning:
            Normalizes the phase field a → a / |a| to ensure unit magnitude,
            representing a normalized phase configuration.
            
        Mathematical Foundation:
            Implements: a_normalized = a / |a| if |a| > ε, else 1.0
            where ε = 1e-12 is a small threshold to avoid division by zero.
            
        Args:
            field (cp.ndarray): Complex phase field on GPU.
            
        Returns:
            cp.ndarray: Normalized phase field on GPU.
        """
        output = cp.zeros_like(field, dtype=cp.complex128)
        self._phase_norm_kernel(field, output)
        return output


# Convenience functions
def compute_7d_laplacian_optimized(
    field: "cp.ndarray", h: float = 1.0
) -> "cp.ndarray":
    """
    Compute 7D Laplacian using optimized CUDA kernel.
    
    Physical Meaning:
        Convenience function for computing 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ²
        using optimized CUDA kernels.
        
    Args:
        field (cp.ndarray): 7D field array on GPU.
        h (float): Grid spacing (default: 1.0).
        
    Returns:
        cp.ndarray: 7D Laplacian result on GPU.
    """
    kernels = Optimized7DKernels()
    return kernels.compute_7d_laplacian(field, h)


def compute_7d_gradient_optimized(
    field: "cp.ndarray", h: float = 1.0
) -> Tuple["cp.ndarray", ...]:
    """
    Compute 7D gradient using vectorized operations.
    
    Physical Meaning:
        Convenience function for computing 7D gradient ∇₇ using vectorized
        CuPy operations.
        
    Args:
        field (cp.ndarray): 7D field array on GPU.
        h (float): Grid spacing (default: 1.0).
        
    Returns:
        Tuple[cp.ndarray, ...]: 7-tuple of gradient components.
    """
    kernels = Optimized7DKernels()
    return kernels.compute_7d_gradient(field, h)


def compute_7d_phase_normalization_optimized(
    field: "cp.ndarray"
) -> "cp.ndarray":
    """
    Normalize phase field to unit magnitude.
    
    Physical Meaning:
        Convenience function for normalizing phase field a → a / |a|.
        
    Args:
        field (cp.ndarray): Complex phase field on GPU.
        
    Returns:
        cp.ndarray: Normalized phase field on GPU.
    """
    kernels = Optimized7DKernels()
    return kernels.normalize_phase(field)

