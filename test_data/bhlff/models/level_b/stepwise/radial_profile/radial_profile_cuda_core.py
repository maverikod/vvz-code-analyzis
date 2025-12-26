"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA core methods mixin for radial profile computation.

This module provides _compute_cuda and _compute_cuda_with_swap methods
as a mixin class.
"""

import numpy as np
from typing import Dict, List
import logging
import sys

# CUDA support
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class RadialProfileCUDACoreMixin:
    """Mixin providing core CUDA computation methods."""
    
    def _compute_cuda(
        self, field: np.ndarray, center: List[float]
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile with CUDA acceleration and automatic swap/blocking.

        Physical Meaning:
            Computes radial profile A(r) using CUDA for efficient
            processing of large 7D fields with automatic swap and block processing
            when GPU memory is insufficient.

        Args:
            field (np.ndarray): Field array (GPU or CPU).
            center (List[float]): Center coordinates [x, y, z].

        Returns:
            Dict[str, np.ndarray]: Radial profile with 'r' and 'A' arrays.
        """
        if len(field.shape) == 7:
            shape = field.shape[:3]
        else:
            shape = field.shape[:3]

        # Check if field is already swapped to disk (memory-mapped)
        is_swapped = isinstance(field, np.memmap)

        # CRITICAL: This method should only be called for non-7D fields or when
        # _compute_cuda_with_swap is not appropriate. For 7D fields, window-based
        # processing should be handled in compute() method.
        # This is a fallback for smaller fields that don't need windowing.
        field_size_bytes = field.nbytes
        field_size_gb = field_size_bytes / 1e9

        # For 7D fields, should have been handled in compute() method
        # But if we get here, use window-based processing anyway
        if len(field.shape) == 7:
            self.logger.warning(
                f"7D field in _compute_cuda (should use _compute_cuda_with_swap), "
                f"falling back to window-based processing. Shape={field.shape}, size={field_size_gb:.3f}GB"
            )
            return self._compute_cuda_with_swap(field, center, shape)
        
        # For non-7D fields, check if window-based processing is needed
        # Use same logic as FFT solver: check if field fits in single window
        use_window_processing = is_swapped
        
        if self.use_cuda and CUDA_AVAILABLE and not is_swapped:
            try:
                from ....utils.cuda_utils import calculate_optimal_window_memory
                
                # Calculate optimal window size (same as FFT solver)
                # Overhead: meshgrid (3x), distances (1x), amplitude (1x), temp arrays (2x) = ~5x
                max_window_elements, _, _ = calculate_optimal_window_memory(
                    gpu_memory_ratio=self.gpu_memory_ratio,
                    overhead_factor=5.0,
                    logger=self.logger,
                )
                
                field_elements = np.prod(field.shape)
                
                # If field doesn't fit in single window, use window-based processing
                if field_elements > max_window_elements:
                    use_window_processing = True
                    self.logger.info(
                        f"Field size {field_size_gb:.3f}GB ({field_elements/1e6:.1f}M elements) "
                        f"exceeds window size {max_window_elements/1e6:.1f}M elements, "
                        f"using window-based processing for maximum GPU utilization"
                    )
            except Exception as e:
                self.logger.warning(
                    f"Failed to check GPU memory: {e}, using window-based processing"
                )
                use_window_processing = True

        # Use window-based processing for large fields or swapped fields
        if use_window_processing:
            return self._compute_cuda_with_swap(field, center, shape)

        # Standard computation for smaller fields that fit in GPU memory
        self.logger.info(
            f"[RADIAL PROFILE] GPU MODE: Standard computation (field fits in GPU). "
            f"Field shape={field.shape}, using xp={self.xp.__name__}, "
            f"xp is cupy={self.xp is cp}"
        )
        sys.stdout.flush()
        
        x = self.xp.arange(shape[0], dtype=self.xp.float32)
        y = self.xp.arange(shape[1], dtype=self.xp.float32)
        z = self.xp.arange(shape[2], dtype=self.xp.float32)
        X, Y, Z = self.xp.meshgrid(x, y, z, indexing="ij")
        
        # DEBUG: Verify arrays are on GPU
        if self.use_cuda and CUDA_AVAILABLE:
            if not isinstance(X, cp.ndarray):
                self.logger.warning(
                    f"[RADIAL PROFILE] CPU MODE: Meshgrid not on GPU! Type: {type(X)}"
                )
                sys.stdout.flush()
            else:
                self.logger.info(
                    f"[RADIAL PROFILE] GPU MODE: Meshgrid on GPU, shape={X.shape}"
                )
                sys.stdout.flush()

        center_array = self.xp.array(center, dtype=self.xp.float32)
        distances = self.xp.sqrt(
            (X - center_array[0]) ** 2
            + (Y - center_array[1]) ** 2
            + (Z - center_array[2]) ** 2
        )

        # Synchronize GPU after distance computation
        if self.use_cuda:
            cp.cuda.Stream.null.synchronize()

        # Transfer field to GPU with memory check
        try:
            field_gpu = self.xp.asarray(field)
        except Exception as e:
            if "OutOfMemoryError" in str(type(e).__name__) or "out of memory" in str(e).lower():
                self.logger.warning(
                    f"GPU out of memory during field transfer: {e}, "
                    f"falling back to swap/block processing"
                )
                return self._compute_cuda_with_swap(field, center, shape)
            raise
        if len(field.shape) == 7:
            center_phi = field.shape[3] // 2
            center_t = field.shape[6] // 2
            amplitude = self.xp.abs(
                field_gpu[:, :, :, center_phi, center_phi, center_phi, center_t]
            )
        else:
            amplitude = self.xp.abs(field_gpu)

        # Synchronize before max operation
        if self.use_cuda:
            cp.cuda.Stream.null.synchronize()

        r_max = float(self.xp.max(distances))
        num_bins = min(100, max(20, int(r_max)))
        r_bins = self.xp.linspace(0.0, r_max, num_bins + 1)
        r_centers = (r_bins[:-1] + r_bins[1:]) / 2.0

        distances_flat = distances.ravel()
        amplitude_flat = amplitude.ravel()

        # Synchronize before searchsorted
        if self.use_cuda:
            cp.cuda.Stream.null.synchronize()

        bin_indices = self.xp.searchsorted(r_bins[1:], distances_flat, side="right")
        bin_indices = self.xp.clip(bin_indices, 0, num_bins - 1)

        A_radial = self.xp.zeros(num_bins, dtype=self.xp.float32)
        if hasattr(self.xp, "bincount"):
            # Synchronize before bincount
            if self.use_cuda:
                cp.cuda.Stream.null.synchronize()

            bin_sums = self.xp.bincount(
                bin_indices, weights=amplitude_flat, minlength=num_bins
            )
            bin_counts = self.xp.bincount(bin_indices, minlength=num_bins)

            # Synchronize after bincount
            if self.use_cuda:
                cp.cuda.Stream.null.synchronize()

            valid_mask = bin_counts > 0
            A_radial[valid_mask] = bin_sums[valid_mask] / bin_counts[valid_mask]
        else:
            for i in range(num_bins):
                mask = bin_indices == i
                if self.xp.any(mask):
                    A_radial[i] = self.xp.mean(amplitude_flat[mask])

        # Final synchronization before return
        if self.use_cuda:
            cp.cuda.Stream.null.synchronize()

        # Always convert back to numpy for return
        if self.use_cuda:
            return {
                "r": cp.asnumpy(r_centers),
                "A": cp.asnumpy(A_radial),
            }
        return {"r": r_centers, "A": A_radial}



    def _compute_cuda_with_swap(
        self, field: np.ndarray, center: List[float], shape: tuple
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile using swap and block processing for large fields.

        Physical Meaning:
            Computes radial profile for large fields by using swap manager
            and block processing to avoid GPU memory issues. Works with
            memory-mapped arrays from swap automatically.

        Args:
            field (np.ndarray): Field array (may be memory-mapped if swapped).
            center (List[float]): Center coordinates.
            shape (tuple): Spatial shape.

        Returns:
            Dict[str, np.ndarray]: Radial profile.
        """
        # If field is already swapped (memory-mapped), process in blocks
        if isinstance(field, np.memmap):
            self.logger.info(
                f"Field already on disk (swap), processing in blocks: shape={field.shape}"
            )
            return self._compute_cuda_blocked_from_swap(field, center, shape)

        # Field is not swapped yet - wrap in FieldArray for automatic swap
        try:
            from bhlff.core.arrays.field_array import FieldArray

            # DEBUG: Check field size before wrapping
            self.logger.info(
                f"[RADIAL PROFILE DEBUG] Before FieldArray wrap: field shape={field.shape}, "
                f"size={field.nbytes/1e9:.3f}GB, type={type(field).__name__}"
            )
            sys.stdout.flush()

            # Wrap field - FieldArray will automatically use swap if field is large
            self.logger.info("[RADIAL PROFILE DEBUG] Creating FieldArray...")
            sys.stdout.flush()
            field_wrapped = FieldArray(array=field)
            self.logger.info(
                f"[RADIAL PROFILE DEBUG] FieldArray created: is_swapped={isinstance(field_wrapped.array, np.memmap)}, "
                f"type={type(field_wrapped.array).__name__}"
            )
            sys.stdout.flush()

            # If FieldArray converted to swap, use swapped array
            if isinstance(field_wrapped.array, np.memmap):
                self.logger.info(
                    f"Field automatically swapped to disk by FieldArray, "
                    f"processing in blocks: shape={field_wrapped.array.shape}"
                )
                return self._compute_cuda_blocked_from_swap(
                    field_wrapped.array, center, shape
                )

        except Exception as e:
            self.logger.warning(
                f"[RADIAL PROFILE] FieldArray swap failed: {e}, using direct block processing"
            )
            sys.stdout.flush()

        # Process in blocks directly (field fits in memory but not in GPU)
        return self._compute_cuda_blocked_from_swap(field, center, shape)

