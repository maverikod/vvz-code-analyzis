"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA single block computation method mixin for radial profile computation.

This module provides _compute_cuda_single_block method as a mixin class.
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

# Import computation helpers
from .radial_profile_cuda_meshgrid import RadialProfileCUDAMeshgridMixin
from .radial_profile_cuda_amplitude import RadialProfileCUDAAmplitudeMixin
from .radial_profile_cuda_bincount import RadialProfileCUDABincountMixin


class RadialProfileCUDASingleMixin(
    RadialProfileCUDAMeshgridMixin,
    RadialProfileCUDAAmplitudeMixin,
    RadialProfileCUDABincountMixin
):
    """Mixin providing single block CUDA computation method."""
    
    def _compute_cuda_single_block(
        self, block: np.ndarray, center: List[float], stream=None
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile for a single block on GPU (direct, no swap check).

        Physical Meaning:
            Computes radial profile for a single spatial block on GPU,
            used in block processing pipeline. Block should already be on GPU.

        Args:
            block (np.ndarray or cp.ndarray): Block array (should be on GPU).
            center (List[float]): Center coordinates relative to block.
            stream: CUDA stream for parallel execution.

        Returns:
            Dict[str, np.ndarray]: Radial profile.
        """
        if len(block.shape) == 7:
            block_shape = block.shape[:3]
        else:
            block_shape = block.shape[:3]

        # STEP-BY-STEP LOGGING: Track every computation step
        import sys
        
        # Ensure block is on GPU - use cupy directly for all operations
        if self.use_cuda and CUDA_AVAILABLE:
            self.logger.info("[RADIAL COMPUTE] STEP 1: Ensuring block is on GPU")
            sys.stdout.flush()
            # Block should already be on GPU, but ensure it's cupy array
            if not isinstance(block, cp.ndarray):
                self.logger.warning(
                    f"[RADIAL COMPUTE] Block not on GPU! Type: {type(block)}, "
                    f"transferring to GPU..."
                )
                if stream is not None:
                    with stream:
                        block_gpu = cp.asarray(block)
                else:
                    block_gpu = cp.asarray(block)
            else:
                block_gpu = block
            
            # CRITICAL: Verify block is actually on GPU
            if not isinstance(block_gpu, cp.ndarray):
                raise RuntimeError(
                    f"Block not on GPU after transfer! Type: {type(block_gpu)}, "
                    f"expected cp.ndarray"
                )
            
            # DEBUG: Detailed GPU memory check
            try:
                mem_info_detailed = cp.cuda.runtime.memGetInfo()
                free_mem_detailed = mem_info_detailed[0] / 1e9
                total_mem_detailed = mem_info_detailed[1] / 1e9
                used_mem_detailed = total_mem_detailed - free_mem_detailed
                block_mem = block_gpu.nbytes / 1e9
                self.logger.info(
                    f"[RADIAL COMPUTE] Block on GPU: shape={block_gpu.shape}, "
                    f"dtype={block_gpu.dtype}, type={type(block_gpu).__name__}, "
                    f"block size: {block_mem:.3f}GB, GPU used: {used_mem_detailed:.2f}GB / "
                    f"{total_mem_detailed:.2f}GB ({used_mem_detailed/total_mem_detailed*100:.1f}%), "
                    f"free: {free_mem_detailed:.2f}GB"
                )
                sys.stdout.flush()
                
                # CRITICAL: Verify block is actually using GPU memory
                if block_mem > 0.01 and used_mem_detailed < 0.1:  # Block > 10MB but GPU < 100MB used
                    self.logger.warning(
                        f"[RADIAL COMPUTE WARNING] Block size {block_mem:.3f}GB but GPU only "
                        f"using {used_mem_detailed:.2f}GB! Block may not be on GPU!"
                    )
                    sys.stdout.flush()
            except Exception as e:
                self.logger.warning(f"Failed to check GPU memory: {e}")
        else:
            block_gpu = block
            self.logger.warning(
                f"[RADIAL COMPUTE] CPU MODE: Processing block on CPU! "
                f"use_cuda={self.use_cuda}, CUDA_AVAILABLE={CUDA_AVAILABLE}"
            )
            sys.stdout.flush()

        # Use helper methods for computation steps
        X, Y, Z, distances = self._compute_meshgrid_distances(block_shape, center, stream)
        amplitude, r_bins, r_centers, distances_flat, amplitude_flat, num_bins = self._compute_amplitude_bins(
            block_gpu, distances, stream
        )
        A_radial = self._compute_bincount_average(
            distances_flat, amplitude_flat, r_bins, num_bins, stream
        )

        self.logger.info("[RADIAL COMPUTE] STEP 9: Converting to numpy")
        sys.stdout.flush()
        
        # Convert back to numpy for return
        if self.use_cuda and CUDA_AVAILABLE:
            # Verify arrays are still on GPU before conversion
            if not isinstance(r_centers, cp.ndarray):
                self.logger.warning(f"r_centers not on GPU before conversion! Type: {type(r_centers)}")
            if not isinstance(A_radial, cp.ndarray):
                self.logger.warning(f"A_radial not on GPU before conversion! Type: {type(A_radial)}")
            
            result = {
                "r": cp.asnumpy(r_centers),
                "A": cp.asnumpy(A_radial),
            }
            self.logger.info("[RADIAL COMPUTE] COMPLETE - all operations on GPU")
            sys.stdout.flush()
            return result
        self.logger.warning(
            f"[RADIAL COMPUTE] CPU MODE: COMPLETE (CPU). "
            f"use_cuda={self.use_cuda}, CUDA_AVAILABLE={CUDA_AVAILABLE}. "
            f"This should not happen if CUDA is enabled!"
        )
        sys.stdout.flush()
        return {"r": r_centers, "A": A_radial}
