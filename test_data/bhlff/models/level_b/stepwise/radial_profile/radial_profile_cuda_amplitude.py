"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA amplitude and bin computation for radial profile.

This module provides _compute_amplitude_bins method for GPU computation.
"""

import numpy as np
from typing import Tuple
import logging
import sys

# CUDA support
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class RadialProfileCUDAAmplitudeMixin:
    """Mixin providing amplitude and bin computation."""
    
    def _compute_amplitude_bins(
        self, block_gpu, distances: cp.ndarray, stream=None
    ) -> Tuple[cp.ndarray, cp.ndarray, cp.ndarray, cp.ndarray, cp.ndarray, int]:
        """
        Compute amplitude and bin arrays on GPU.
        
        Physical Meaning:
            Extracts field amplitude and prepares binning arrays
            for radial profile computation.
            
        Args:
            block_gpu: Block array on GPU.
            distances (cp.ndarray): Distance array from meshgrid.
            stream: CUDA stream for parallel execution.
            
        Returns:
            Tuple containing (amplitude, r_bins, r_centers, distances_flat, amplitude_flat, num_bins).
        """
        self.logger.info("[RADIAL COMPUTE] STEP 4: Extracting amplitude on GPU")
        sys.stdout.flush()
        
        # DEBUG: Check GPU memory before amplitude
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                mem_before_amp = cp.cuda.runtime.memGetInfo()
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] Before amplitude: GPU memory "
                    f"{mem_before_amp[0]/1e9:.3f}GB free / {mem_before_amp[1]/1e9:.3f}GB total"
                )
                sys.stdout.flush()
            except Exception:
                pass
        
        # CRITICAL: Use cp directly for GPU operations
        if self.use_cuda and CUDA_AVAILABLE:
            if len(block_gpu.shape) == 7:
                center_phi = block_gpu.shape[3] // 2
                center_t = block_gpu.shape[6] // 2
                amplitude = cp.abs(
                    block_gpu[:, :, :, center_phi, center_phi, center_phi, center_t]
                )
            else:
                amplitude = cp.abs(block_gpu)
            
            # CRITICAL: Verify amplitude is on GPU
            if not isinstance(amplitude, cp.ndarray):
                raise RuntimeError(f"Amplitude not on GPU! Type: {type(amplitude)}")
            
            # Force GPU computation
            _ = amplitude.device
        else:
            if len(block_gpu.shape) == 7:
                center_phi = block_gpu.shape[3] // 2
                center_t = block_gpu.shape[6] // 2
                amplitude = np.abs(
                    block_gpu[:, :, :, center_phi, center_phi, center_phi, center_t]
                )
            else:
                amplitude = np.abs(block_gpu)
        
        # DEBUG: Verify amplitude is on GPU and check memory
        if self.use_cuda and CUDA_AVAILABLE:
            if not isinstance(amplitude, cp.ndarray):
                raise RuntimeError(f"Amplitude not on GPU! Type: {type(amplitude)}")
            try:
                mem_after_amp = cp.cuda.runtime.memGetInfo()
                amplitude_mem_gb = amplitude.nbytes / 1e9
                amplitude_mem_mb = amplitude.nbytes / 1e6
                memory_change_mb = (mem_before_amp[0] - mem_after_amp[0]) / 1e6
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] After amplitude: GPU memory "
                    f"{mem_after_amp[0]/1e9:.3f}GB free / {mem_after_amp[1]/1e9:.3f}GB total, "
                    f"amplitude size: {amplitude_mem_mb:.2f}MB ({amplitude_mem_gb:.6f}GB), "
                    f"memory change: {memory_change_mb:.2f}MB, "
                    f"shape={amplitude.shape}, dtype={amplitude.dtype}, device={amplitude.device}"
                )
                sys.stdout.flush()
                
                # CRITICAL: If amplitude memory is very small, it may not be using GPU properly
                if amplitude_mem_mb < 1.0:  # Less than 1MB
                    self.logger.warning(
                        f"[RADIAL COMPUTE WARNING] Amplitude memory very small ({amplitude_mem_mb:.2f}MB)! "
                        f"Expected ~{np.prod(amplitude.shape)*4/1e6:.2f}MB for float32. "
                        f"GPU may not be storing arrays!"
                    )
                    sys.stdout.flush()
            except Exception:
                pass

        if self.use_cuda and CUDA_AVAILABLE and stream is None:
            cp.cuda.Stream.null.synchronize()

        self.logger.info("[RADIAL COMPUTE] STEP 5: Computing bins on GPU")
        sys.stdout.flush()
        
        # CRITICAL: Use cp directly for GPU operations
        if self.use_cuda and CUDA_AVAILABLE:
            r_max = float(cp.max(distances))
            num_bins = min(100, max(20, int(r_max)))
            r_bins = cp.linspace(0.0, r_max, num_bins + 1)
            r_centers = (r_bins[:-1] + r_bins[1:]) / 2.0

            distances_flat = distances.ravel()
            amplitude_flat = amplitude.ravel()
            
            # CRITICAL: Verify arrays are on GPU
            if not isinstance(r_bins, cp.ndarray) or not isinstance(r_centers, cp.ndarray):
                raise RuntimeError(
                    f"Bins not on GPU! r_bins type: {type(r_bins)}, r_centers type: {type(r_centers)}"
                )
            if not isinstance(distances_flat, cp.ndarray) or not isinstance(amplitude_flat, cp.ndarray):
                raise RuntimeError(
                    f"Flattened arrays not on GPU! distances_flat type: {type(distances_flat)}, "
                    f"amplitude_flat type: {type(amplitude_flat)}"
                )
        else:
            r_max = float(np.max(distances))
            num_bins = min(100, max(20, int(r_max)))
            r_bins = np.linspace(0.0, r_max, num_bins + 1)
            r_centers = (r_bins[:-1] + r_bins[1:]) / 2.0

            distances_flat = distances.ravel()
            amplitude_flat = amplitude.ravel()

        if self.use_cuda and CUDA_AVAILABLE and stream is None:
            cp.cuda.Stream.null.synchronize()

        return amplitude, r_bins, r_centers, distances_flat, amplitude_flat, num_bins

