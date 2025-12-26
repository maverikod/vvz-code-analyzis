"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA bincount and average computation for radial profile.

This module provides _compute_bincount_average method for GPU computation.
"""

import numpy as np
from typing import Dict
import logging
import sys

# CUDA support
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class RadialProfileCUDABincountMixin:
    """Mixin providing bincount and average computation."""
    
    def _compute_bincount_average(
        self, distances_flat: cp.ndarray, amplitude_flat: cp.ndarray,
        r_bins: cp.ndarray, num_bins: int, stream=None
    ) -> cp.ndarray:
        """
        Compute bincount and average on GPU.
        
        Physical Meaning:
            Computes radial profile by binning distances and averaging
            amplitudes within each radial bin.
            
        Args:
            distances_flat (cp.ndarray): Flattened distance array.
            amplitude_flat (cp.ndarray): Flattened amplitude array.
            r_bins (cp.ndarray): Radial bin edges.
            num_bins (int): Number of bins.
            stream: CUDA stream for parallel execution.
            
        Returns:
            cp.ndarray: Radial profile A(r) array.
        """
        self.logger.info("[RADIAL COMPUTE] STEP 6: Computing bin indices on GPU")
        sys.stdout.flush()
        
        # CRITICAL: Use cp directly for GPU operations
        if self.use_cuda and CUDA_AVAILABLE:
            bin_indices = cp.searchsorted(r_bins[1:], distances_flat, side="right")
            bin_indices = cp.clip(bin_indices, 0, num_bins - 1)
            
            # CRITICAL: Convert to int32 for bincount (required by CuPy)
            bin_indices = bin_indices.astype(cp.int32)
            
            # CRITICAL: Verify bin_indices is on GPU
            if not isinstance(bin_indices, cp.ndarray):
                raise RuntimeError(f"bin_indices not on GPU! Type: {type(bin_indices)}")
        else:
            bin_indices = np.searchsorted(r_bins[1:], distances_flat, side="right")
            bin_indices = np.clip(bin_indices, 0, num_bins - 1)
            self.logger.info(
                f"[RADIAL COMPUTE DEBUG] bin_indices: shape={bin_indices.shape}, "
                f"dtype={bin_indices.dtype}, min={int(cp.min(bin_indices))}, "
                f"max={int(cp.max(bin_indices))}, num_bins={num_bins}"
            )
            sys.stdout.flush()

        # CRITICAL: Use cp directly for GPU operations
        if self.use_cuda and CUDA_AVAILABLE:
            A_radial = cp.zeros(num_bins, dtype=cp.float32)
            
            if stream is None:
                cp.cuda.Stream.null.synchronize()

            self.logger.info("[RADIAL COMPUTE] STEP 7: Computing bincount on GPU")
            sys.stdout.flush()
            
            # CRITICAL: Use int32 for bincount and ensure weights are correct dtype
            # Ensure weights are float32 for efficiency
            amplitude_flat_bincount = amplitude_flat.astype(cp.float32)
            bin_sums = cp.bincount(
                bin_indices, weights=amplitude_flat_bincount, minlength=num_bins
            )
            bin_counts = cp.bincount(bin_indices, minlength=num_bins)
            
            # CRITICAL: Verify bincount results are on GPU
            if not isinstance(bin_sums, cp.ndarray) or not isinstance(bin_counts, cp.ndarray):
                raise RuntimeError(
                    f"Bincount results not on GPU! bin_sums type: {type(bin_sums)}, "
                    f"bin_counts type: {type(bin_counts)}"
                )
            
            # DEBUG: Check results
            self.logger.info(
                f"[RADIAL COMPUTE DEBUG] bincount complete: "
                f"bin_sums shape={bin_sums.shape}, dtype={bin_sums.dtype}, "
                f"bin_counts shape={bin_counts.shape}, dtype={bin_counts.dtype}, "
                f"non_zero_bins={int(cp.count_nonzero(bin_counts))}"
            )
            sys.stdout.flush()

            if stream is None:
                cp.cuda.Stream.null.synchronize()

            self.logger.info("[RADIAL COMPUTE] STEP 8: Computing averages on GPU")
            sys.stdout.flush()
            
            # CRITICAL: Use cp directly for GPU operations
            valid_mask = bin_counts > 0
            A_radial[valid_mask] = bin_sums[valid_mask] / bin_counts[valid_mask]
            
            # CRITICAL: Verify A_radial is on GPU
            if not isinstance(A_radial, cp.ndarray):
                raise RuntimeError(f"A_radial not on GPU! Type: {type(A_radial)}")
            
            # Force GPU computation
            _ = A_radial.device
        else:
            A_radial = np.zeros(num_bins, dtype=np.float32)
            bin_sums = np.bincount(
                bin_indices, weights=amplitude_flat, minlength=num_bins
            )
            bin_counts = np.bincount(bin_indices, minlength=num_bins)
            valid_mask = bin_counts > 0
            A_radial[valid_mask] = bin_sums[valid_mask] / bin_counts[valid_mask]

        if self.use_cuda and CUDA_AVAILABLE:
            if stream is not None:
                stream.synchronize()
            else:
                cp.cuda.Stream.null.synchronize()

        return A_radial

