"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for radial profile computation.

This module provides the base RadialProfileComputerBase class with common
initialization and main compute methods.

Theoretical Background:
    Radial profiles A(r) are computed by averaging field values over
    spherical shells centered at defects, enabling analysis of decay
    behavior and layer structure in 7D space-time.

Example:
    >>> profiler = RadialProfileComputer(use_cuda=True)
    >>> profile = profiler.compute(field, center)
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

# Import mixins
from .radial_profile_cuda_core import RadialProfileCUDACoreMixin
from .radial_profile_cuda_blocked import RadialProfileCUDABlockedMixin
from .radial_profile_cuda_single import RadialProfileCUDASingleMixin


class RadialProfileComputerBase(
    RadialProfileCUDACoreMixin,
    RadialProfileCUDABlockedMixin,
    RadialProfileCUDASingleMixin
):
    """
    Base class for radial profile computation.
    
    Physical Meaning:
        Provides base functionality for computing radial profiles by
        averaging field values over spherical shells, supporting both
        CPU and CUDA acceleration.
        
    Mathematical Foundation:
        For a field a(x), the radial profile A(r) is computed as:
        A(r) = (1/V_r) ∫_{|x-c|=r} |a(x)| dS
        where V_r is the volume of the spherical shell at radius r.
    """
    
    def __init__(self, use_cuda: bool = True, gpu_memory_ratio: float = 0.8):
        """
        Initialize radial profile computer.
        
        Physical Meaning:
            Sets up computer with CUDA acceleration for efficient
            computation of radial profiles in 7D phase fields.
            
        Args:
            use_cuda (bool): Whether to use CUDA acceleration.
            gpu_memory_ratio (float): GPU memory utilization ratio (0-1).
        """
        self.use_cuda = use_cuda and CUDA_AVAILABLE
        self.gpu_memory_ratio = gpu_memory_ratio
        self.logger = logging.getLogger(__name__)
        
        if self.use_cuda:
            self.xp = cp
            try:
                from ....utils.cuda_utils import get_global_backend
                self.backend = get_global_backend()
            except ImportError:
                self.backend = None
        else:
            self.xp = np
            self.backend = None
    
    def compute(self, field: np.ndarray, center: List[float]) -> Dict[str, np.ndarray]:
        """
        Compute radial profile of the field with automatic swap/blocking.
        
        Physical Meaning:
            Computes the radial profile A(r) by averaging the field
            over spherical shells centered at the defect. Automatically
            uses FieldArray for transparent swap and block processing
            when field size exceeds GPU memory.
            
        Args:
            field (np.ndarray): 3D or 7D field array (will be wrapped in FieldArray
                for automatic swap management if needed).
            center (List[float]): Center coordinates [x, y, z].
                
        Returns:
            Dict[str, np.ndarray]: Radial profile with 'r' and 'A' arrays.
        """
        field_size_mb = field.nbytes / (1024**2) if hasattr(field, 'nbytes') else 0
        self.logger.info(
            f"[RADIAL PROFILE] compute: START - field shape={field.shape}, "
            f"size={field_size_mb:.2f}MB, center={center}, use_cuda={self.use_cuda}"
        )
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Automatically wrap field in FieldArray for transparent swap management
        from bhlff.core.arrays.field_array import FieldArray
        
        self.logger.info(f"[RADIAL PROFILE] STEP 1: Wrapping field in FieldArray if needed...")
        sys.stdout.flush()
        sys.stderr.flush()
        if not isinstance(field, FieldArray):
            field_wrapped = FieldArray(array=field)
            self.logger.info(f"[RADIAL PROFILE] STEP 1 COMPLETE: Field wrapped in FieldArray")
        else:
            field_wrapped = field
            self.logger.info(f"[RADIAL PROFILE] STEP 1 COMPLETE: Field already FieldArray")
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Extract array (may be memory-mapped if swapped)
        self.logger.info(f"[RADIAL PROFILE] STEP 2: Extracting array...")
        sys.stdout.flush()
        sys.stderr.flush()
        field_array = field_wrapped.array
        is_swapped = isinstance(field_array, np.memmap)
        self.logger.info(
            f"[RADIAL PROFILE] STEP 2 COMPLETE: Array extracted, shape={field_array.shape if field_array is not None else None}, "
            f"is_swapped={is_swapped}, type={type(field_array).__name__}"
        )
        sys.stdout.flush()
        sys.stderr.flush()
        
        # CRITICAL: For 7D fields, ALWAYS use window-based processing to maximize GPU utilization
        if self.use_cuda and len(field_array.shape) == 7:
            self.logger.info(
                f"[RADIAL PROFILE] STEP 3: 7D field detected, using window-based GPU processing "
                f"(is_swapped={is_swapped})"
            )
            sys.stdout.flush()
            return self._compute_cuda_with_swap(field_array, center, field_array.shape[:3])
        
        if self.use_cuda:
            self.logger.info(
                f"[RADIAL PROFILE] GPU MODE: Using CUDA for non-7D field. "
                f"Field shape={field_array.shape}, size={field_array.nbytes/1e9:.3f}GB"
            )
            sys.stdout.flush()
            return self._compute_cuda(field_array, center)
        else:
            self.logger.warning(
                f"[RADIAL PROFILE] CPU MODE: use_cuda=False, using CPU. "
                f"Field shape={field_array.shape}, size={field_array.nbytes/1e9:.3f}GB"
            )
            sys.stdout.flush()
            from .radial_profile_cpu import RadialProfileComputerCPU
            cpu_computer = RadialProfileComputerCPU(logger=self.logger)
            return cpu_computer._compute_cpu(field_array, center)
    
    def compute_substrate(
        self, substrate: np.ndarray, center: List[float]
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile of substrate transparency.
        
        Physical Meaning:
            Computes the radial profile T(r) by averaging the substrate
            transparency over spherical shells centered at the defect
            using vectorized operations for efficiency.
            
        Args:
            substrate (np.ndarray): 7D substrate field.
            center (List[float]): Center coordinates [x, y, z].
                
        Returns:
            Dict[str, np.ndarray]: Radial profile with 'r' and 'A' arrays.
        """
        use_cuda_here = self.use_cuda
        xp = self.xp if use_cuda_here else np
        
        # Convert numpy array to cupy if CUDA is enabled
        if use_cuda_here and isinstance(substrate, np.ndarray):
            substrate = xp.asarray(substrate)
        
        if len(substrate.shape) == 7:
            shape = substrate.shape[:3]
        else:
            shape = substrate.shape[:3]
        
        x = xp.arange(shape[0], dtype=xp.float32)
        y = xp.arange(shape[1], dtype=xp.float32)
        z = xp.arange(shape[2], dtype=xp.float32)
        X, Y, Z = xp.meshgrid(x, y, z, indexing="ij")
        
        center_array = xp.array(center, dtype=xp.float32)
        distances = xp.sqrt(
            (X - center_array[0]) ** 2
            + (Y - center_array[1]) ** 2
            + (Z - center_array[2]) ** 2
        )
        
        if len(substrate.shape) == 7:
            center_phi = substrate.shape[3] // 2
            center_t = substrate.shape[6] // 2
            transparency = xp.abs(
                substrate[:, :, :, center_phi, center_phi, center_phi, center_t]
            )
        else:
            transparency = xp.abs(substrate)
        
        r_max = float(xp.max(distances))
        num_bins = max(20, min(100, int(r_max * 10)))
        r_bins = xp.linspace(0.0, r_max, num_bins + 1)
        r_centers = (r_bins[:-1] + r_bins[1:]) / 2.0
        
        distances_flat = distances.ravel()
        transparency_flat = transparency.ravel()
        bin_indices = xp.searchsorted(r_bins[1:], distances_flat, side="right")
        bin_indices = xp.clip(bin_indices, 0, num_bins - 1)
        
        T_radial = xp.zeros(num_bins, dtype=xp.float32)
        if hasattr(xp, "bincount"):
            bin_sums = xp.bincount(
                bin_indices, weights=transparency_flat, minlength=num_bins
            )
            bin_counts = xp.bincount(bin_indices, minlength=num_bins)
            valid_mask = bin_counts > 0
            T_radial[valid_mask] = bin_sums[valid_mask] / bin_counts[valid_mask]
        else:
            for i in range(num_bins):
                mask = bin_indices == i
                if xp.any(mask):
                    T_radial[i] = xp.mean(transparency_flat[mask])
        
        # Always convert back to numpy for return
        if use_cuda_here:
            T_radial = cp.asnumpy(T_radial)
            r_centers = cp.asnumpy(r_centers)
        
        return {"r": r_centers, "A": T_radial}

