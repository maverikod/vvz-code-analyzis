"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA window processing helper methods for radial profile computation.

This module provides helper methods for processing individual windows
in blocked computation, extracted to keep file sizes manageable.
"""

import numpy as np
from typing import Dict, List, Tuple
import logging
import sys

# CUDA support
try:
    import cupy as cp
    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class RadialProfileCUDAWindowProcessingMixin:
    """Mixin providing window processing helper methods."""
    
    def _process_single_window(
        self,
        window_cpu: np.ndarray,
        window_center: List[float],
        window_idx: int,
        total_windows: int,
        x_start: int,
        x_end: int,
        y_start: int,
        y_end: int,
        z_start: int,
        z_end: int,
    ) -> Dict[str, np.ndarray]:
        """
        Process a single window on GPU with parallel sub-window support.
        
        Physical Meaning:
            Processes a single spatial window entirely on GPU, with
            optional parallel sub-window processing via CUDA streams
            for large windows.
            
        Args:
            window_cpu (np.ndarray): Window data on CPU.
            window_center (List[float]): Center coordinates relative to window.
            window_idx (int): Current window index.
            total_windows (int): Total number of windows.
            x_start, x_end, y_start, y_end, z_start, z_end (int): Window boundaries.
            
        Returns:
            Dict[str, np.ndarray]: Radial profile for this window.
        """
        # STEP-BY-STEP LOGGING: Track every window operation
        window_size_mb = window_cpu.nbytes / (1024**2)
        self.logger.info(
            f"[RADIAL WINDOW {window_idx+1}/{total_windows}] START: "
            f"({x_start}:{x_end}, {y_start}:{y_end}, {z_start}:{z_end}), "
            f"window size: {window_size_mb:.2f}MB ({window_cpu.nbytes/1e9:.3f}GB)"
        )
        sys.stdout.flush()
        sys.stderr.flush()
        
        # Check GPU memory before processing
        mem_info_before = cp.cuda.runtime.memGetInfo()
        free_mem_before = mem_info_before[0] / 1e9
        total_mem = mem_info_before[1] / 1e9
        used_mem_before = (total_mem - free_mem_before)
        
        # Transfer window to GPU first
        # CRITICAL: Ensure data is actually transferred to GPU
        self.logger.info(
            f"[RADIAL WINDOW {window_idx+1}/{total_windows}] STEP 1: "
            f"Transferring to GPU, GPU memory: {used_mem_before:.2f}GB used / "
            f"{total_mem:.2f}GB total ({used_mem_before/total_mem*100:.1f}% used), "
            f"{free_mem_before:.2f}GB free"
        )
        sys.stdout.flush()
        
        if self.backend is not None:
            window_gpu = self.backend.array(window_cpu)
        else:
            window_gpu = cp.asarray(window_cpu)
        
        # CRITICAL: Synchronize to ensure transfer completes
        cp.cuda.Stream.null.synchronize()
        
        # CRITICAL: Verify window is actually on GPU
        if not isinstance(window_gpu, cp.ndarray):
            raise RuntimeError(
                f"Window not on GPU! Type: {type(window_gpu)}, "
                f"expected cp.ndarray"
            )
        
        # Check GPU memory after transfer
        mem_info_after = cp.cuda.runtime.memGetInfo()
        free_mem_after = mem_info_after[0] / 1e9
        used_mem_after = (total_mem - free_mem_after)
        window_mem_used = used_mem_after - used_mem_before
        
        # Verify GPU memory actually increased
        if window_mem_used < 0.001:  # Less than 1MB - suspicious
            self.logger.warning(
                f"[RADIAL WINDOW {window_idx+1}/{total_windows}] WARNING: "
                f"GPU memory usage very low ({window_mem_used:.6f}GB) after transfer! "
                f"Window size: {window_cpu.nbytes/1e9:.3f}GB. "
                f"Data may not be on GPU!"
            )
        
        self.logger.info(
            f"[RADIAL WINDOW {window_idx+1}/{total_windows}] STEP 2: "
            f"Window on GPU, shape={window_gpu.shape}, type={type(window_gpu).__name__}, "
            f"GPU memory: {used_mem_after:.2f}GB used ({used_mem_after/total_mem*100:.1f}%), "
            f"window used {window_mem_used:.3f}GB, "
            f"window size: {window_cpu.nbytes/1e9:.3f}GB"
        )
        sys.stdout.flush()
        
        # CRITICAL: Check if window is large enough to benefit from parallel sub-window processing
        # For windows > 200MB, split into 3-4 sub-windows and process in parallel via streams
        # Split by temporal dimension (dimension 6) for 7D fields
        use_parallel_subwindows = (
            CUDA_AVAILABLE and 
            window_size_mb > 200 and 
            len(window_gpu.shape) == 7 and
            window_gpu.shape[6] >= 2  # Need at least 2 time slices to split
        )
        
        if use_parallel_subwindows:
            # Calculate optimal number of sub-windows (3-4 streams)
            # Each sub-window should be at least 100MB for GPU efficiency
            min_subwindow_mb = 100
            max_subwindows = max(2, int(window_size_mb / min_subwindow_mb))
            num_subwindows = min(max_subwindows, window_gpu.shape[6], 4)  # Use up to 4 streams
            
            # Only use parallel processing if we get at least 2 sub-windows
            if num_subwindows >= 2:
                subwindow_size_t = (window_gpu.shape[6] + num_subwindows - 1) // num_subwindows
                
                # Create CUDA streams for parallel processing
                streams = [cp.cuda.Stream() for _ in range(num_subwindows)]
                subwindow_results = []
                
                self.logger.info(
                    f"[RADIAL WINDOW {window_idx+1}/{total_windows}] Splitting into {num_subwindows} "
                    f"sub-windows for parallel processing via CUDA streams"
                )
                sys.stdout.flush()
                
                # Process sub-windows in parallel via streams
                for stream_idx, stream in enumerate(streams):
                    t_start = stream_idx * subwindow_size_t
                    t_end = min(t_start + subwindow_size_t, window_gpu.shape[6])
                    
                    if t_start >= window_gpu.shape[6]:
                        break
                    
                    # Extract sub-window (full spatial + phase, slice of time)
                    subwindow_gpu = window_gpu[:, :, :, :, :, :, t_start:t_end]
                    
                    # Process sub-window in stream (parallel)
                    with stream:
                        subwindow_profile = self._compute_cuda_single_block(
                            subwindow_gpu, window_center, stream=stream
                        )
                        # Keep result on GPU, store for later aggregation
                        subwindow_results.append(subwindow_profile)
                
                # Synchronize all streams
                self.logger.info(
                    f"[RADIAL WINDOW {window_idx+1}/{total_windows}] Synchronizing {num_subwindows} streams"
                )
                sys.stdout.flush()
                for stream in streams:
                    stream.synchronize()
                
                # Aggregate sub-window results
                # Combine r and A arrays from all sub-windows
                window_profile = self._aggregate_subwindow_profiles(subwindow_results)
                
                self.logger.info(
                    f"[RADIAL WINDOW {window_idx+1}/{total_windows}] Parallel processing complete: "
                    f"{num_subwindows} sub-windows processed"
                )
                sys.stdout.flush()
            else:
                # Window too small for parallel processing, process normally
                window_profile = self._compute_cuda_single_block(
                    window_gpu, window_center
                )
        else:
            # Window too small or not 7D, process normally
            window_profile = self._compute_cuda_single_block(
                window_gpu, window_center
            )
        
        # Check GPU memory after computation
        mem_info_after_comp = cp.cuda.runtime.memGetInfo()
        used_mem_after_comp = (total_mem - mem_info_after_comp[0] / 1e9)
        
        self.logger.info(
            f"[RADIAL WINDOW {window_idx+1}/{total_windows}] STEP 3: "
            f"Computation complete, GPU memory: {used_mem_after_comp:.2f}GB used "
            f"({used_mem_after_comp/total_mem*100:.1f}%), "
            f"peak during computation: {used_mem_after_comp:.2f}GB"
        )
        sys.stdout.flush()
        
        # CRITICAL: Free GPU memory immediately after processing
        # This prevents memory accumulation that could cause hard reset
        del window_gpu
        del window_cpu  # Also free CPU copy
        
        # Force memory pool cleanup
        cp.get_default_memory_pool().free_all_blocks()
        cp.get_default_pinned_memory_pool().free_all_blocks()
        
        # Synchronize to ensure cleanup completes
        cp.cuda.Stream.null.synchronize()
        
        # Check memory after cleanup
        mem_after = cp.cuda.runtime.memGetInfo()[0] / 1e9
        
        self.logger.info(
            f"[RADIAL WINDOW {window_idx+1}/{total_windows}] STEP 4 COMPLETE: "
            f"Memory freed, free_mem={mem_after:.2f}GB"
        )
        sys.stdout.flush()
        
        return window_profile
    
    def _aggregate_window_profiles(
        self,
        all_r: List[np.ndarray],
        all_A: List[np.ndarray],
        total_windows: int,
        field_shape: Tuple[int, ...],
    ) -> Dict[str, np.ndarray]:
        """
        Aggregate radial profiles from all windows.
        
        Physical Meaning:
            Combines radial profiles A(r) from all processed windows,
            interpolating to a common r grid and averaging.
            
        Args:
            all_r (List[np.ndarray]): List of r arrays from all windows.
            all_A (List[np.ndarray]): List of A arrays from all windows.
            total_windows (int): Total number of windows processed.
            field_shape (Tuple[int, ...]): Original field shape.
            
        Returns:
            Dict[str, np.ndarray]: Aggregated profile with 'r' and 'A' arrays.
        """
        if all_r:
            # Use first window's r bins as reference
            r_ref = all_r[0]
            A_combined = np.zeros_like(r_ref)
            
            for r, A in zip(all_r, all_A):
                # Interpolate A to r_ref if needed
                if len(r) == len(r_ref) and np.allclose(r, r_ref):
                    A_combined += A
                else:
                    # Interpolate
                    from scipy.interpolate import interp1d
                    interp = interp1d(
                        r, A, kind="linear", fill_value=0.0, bounds_error=False
                    )
                    A_combined += interp(r_ref)
            
            # Average
            A_combined /= len(all_A)
            
            self.logger.info(
                f"Window-based processing completed: {total_windows} windows processed"
            )
            return {"r": r_ref, "A": A_combined}
        else:
            # Fallback to CPU if no windows processed
            self.logger.warning(
                f"[RADIAL PROFILE] CPU MODE: No windows processed, falling back to CPU. "
                f"Field shape={field_shape}, total_windows={total_windows}"
            )
            sys.stdout.flush()
            # Return None to signal fallback needed - caller will handle
            return None

