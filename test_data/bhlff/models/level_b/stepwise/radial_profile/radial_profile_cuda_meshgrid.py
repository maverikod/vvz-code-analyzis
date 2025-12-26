"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA meshgrid and distances computation for radial profile.

This module provides _compute_meshgrid_distances method for GPU computation.
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


class RadialProfileCUDAMeshgridMixin:
    """Mixin providing meshgrid and distances computation."""
    
    def _compute_meshgrid_distances(
        self, block_shape: Tuple[int, int, int], center: list, stream=None
    ) -> Tuple[cp.ndarray, cp.ndarray, cp.ndarray, cp.ndarray]:
        """
        Compute meshgrid and distances on GPU.
        
        Physical Meaning:
            Creates spatial coordinate grids and computes distances
            from center point for radial profile computation.
            
        Args:
            block_shape (Tuple[int, int, int]): Spatial shape of block.
            center (list): Center coordinates.
            stream: CUDA stream for parallel execution.
            
        Returns:
            Tuple[cp.ndarray, cp.ndarray, cp.ndarray, cp.ndarray]: (X, Y, Z) meshgrid arrays and distances array.
        """
        self.logger.info("[RADIAL COMPUTE] STEP 2: Creating meshgrid on GPU")
        sys.stdout.flush()
        
        # DEBUG: Check GPU memory before meshgrid
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                mem_before = cp.cuda.runtime.memGetInfo()
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] Before meshgrid: GPU memory "
                    f"{mem_before[0]/1e9:.3f}GB free / {mem_before[1]/1e9:.3f}GB total"
                )
                sys.stdout.flush()
            except Exception as e:
                self.logger.warning(f"[RADIAL COMPUTE DEBUG] Failed to check GPU memory: {e}")
        
        # CRITICAL: Use cp directly for GPU operations to ensure vectors are on GPU
        if self.use_cuda and CUDA_AVAILABLE:
            x = cp.arange(block_shape[0], dtype=cp.float32)
            y = cp.arange(block_shape[1], dtype=cp.float32)
            z = cp.arange(block_shape[2], dtype=cp.float32)
            X, Y, Z = cp.meshgrid(x, y, z, indexing="ij")
            
            # CRITICAL: Verify meshgrid arrays are on GPU
            if not isinstance(X, cp.ndarray) or not isinstance(Y, cp.ndarray) or not isinstance(Z, cp.ndarray):
                raise RuntimeError(
                    f"Meshgrid not on GPU! X type: {type(X)}, Y type: {type(Y)}, Z type: {type(Z)}"
                )
            
            # Force GPU memory allocation by accessing arrays
            _ = X.device
            _ = Y.device
            _ = Z.device
        else:
            x = np.arange(block_shape[0], dtype=np.float32)
            y = np.arange(block_shape[1], dtype=np.float32)
            z = np.arange(block_shape[2], dtype=np.float32)
            X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        
        # Verify meshgrid is on GPU and check memory
        if self.use_cuda and CUDA_AVAILABLE:
            if not isinstance(X, cp.ndarray):
                raise RuntimeError(f"Meshgrid not on GPU! Type: {type(X)}")
            
            # DEBUG: Check GPU memory after meshgrid
            try:
                mem_after = cp.cuda.runtime.memGetInfo()
                meshgrid_mem = (X.nbytes + Y.nbytes + Z.nbytes) / 1e9
                meshgrid_mem_mb = (X.nbytes + Y.nbytes + Z.nbytes) / 1e6
                memory_change_mb = (mem_before[0] - mem_after[0]) / 1e6
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] After meshgrid: GPU memory "
                    f"{mem_after[0]/1e9:.3f}GB free / {mem_after[1]/1e9:.3f}GB total, "
                    f"meshgrid size: {meshgrid_mem_mb:.2f}MB ({meshgrid_mem:.6f}GB), "
                    f"memory change: {memory_change_mb:.2f}MB, "
                    f"X shape={X.shape}, dtype={X.dtype}, device={X.device}"
                )
                sys.stdout.flush()
                
                # CRITICAL: If meshgrid memory is very small, it may not be using GPU properly
                if meshgrid_mem_mb < 1.0:  # Less than 1MB
                    self.logger.warning(
                        f"[RADIAL COMPUTE WARNING] Meshgrid memory very small ({meshgrid_mem_mb:.2f}MB)! "
                        f"Expected ~{block_shape[0]*block_shape[1]*block_shape[2]*3*4/1e6:.2f}MB for float32. "
                        f"GPU may not be storing arrays!"
                    )
                    sys.stdout.flush()
            except Exception as e:
                self.logger.warning(f"[RADIAL COMPUTE DEBUG] Failed to check GPU memory: {e}")

        self.logger.info("[RADIAL COMPUTE] STEP 3: Computing distances on GPU")
        sys.stdout.flush()
        
        # DEBUG: Check GPU memory before distances
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                mem_before_dist = cp.cuda.runtime.memGetInfo()
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] Before distances: GPU memory "
                    f"{mem_before_dist[0]/1e9:.3f}GB free / {mem_before_dist[1]/1e9:.3f}GB total"
                )
                sys.stdout.flush()
            except Exception:
                pass
        
        # CRITICAL: Use cp directly for GPU operations
        if self.use_cuda and CUDA_AVAILABLE:
            center_array = cp.array(center, dtype=cp.float32)
            distances = cp.sqrt(
                (X - center_array[0]) ** 2
                + (Y - center_array[1]) ** 2
                + (Z - center_array[2]) ** 2
            )
            
            # CRITICAL: Verify distances is on GPU
            if not isinstance(distances, cp.ndarray):
                raise RuntimeError(f"Distances not on GPU! Type: {type(distances)}")
            
            # Force GPU computation by accessing device
            _ = distances.device
        else:
            center_array = np.array(center, dtype=np.float32)
            distances = np.sqrt(
                (X - center_array[0]) ** 2
                + (Y - center_array[1]) ** 2
                + (Z - center_array[2]) ** 2
            )
        
        # DEBUG: Check GPU memory after distances
        if self.use_cuda and CUDA_AVAILABLE:
            try:
                mem_after_dist = cp.cuda.runtime.memGetInfo()
                distances_mem_gb = distances.nbytes / 1e9
                distances_mem_mb = distances.nbytes / 1e6
                memory_change_mb = (mem_before_dist[0] - mem_after_dist[0]) / 1e6
                self.logger.info(
                    f"[RADIAL COMPUTE DEBUG] After distances: GPU memory "
                    f"{mem_after_dist[0]/1e9:.3f}GB free / {mem_after_dist[1]/1e9:.3f}GB total, "
                    f"distances size: {distances_mem_mb:.2f}MB ({distances_mem_gb:.6f}GB), "
                    f"memory change: {memory_change_mb:.2f}MB, "
                    f"shape={distances.shape}, dtype={distances.dtype}, device={distances.device}"
                )
                sys.stdout.flush()
                
                # CRITICAL: If distances memory is very small, it may not be using GPU properly
                if distances_mem_mb < 1.0:  # Less than 1MB
                    self.logger.warning(
                        f"[RADIAL COMPUTE WARNING] Distances memory very small ({distances_mem_mb:.2f}MB)! "
                        f"Expected ~{np.prod(distances.shape)*4/1e6:.2f}MB for float32. "
                        f"GPU may not be storing arrays!"
                    )
                    sys.stdout.flush()
            except Exception:
                pass

        if self.use_cuda and CUDA_AVAILABLE and stream is None:
            cp.cuda.Stream.null.synchronize()
        
        return X, Y, Z, distances

