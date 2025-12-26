"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA blocked processing methods mixin for radial profile computation.

This module provides window-based blocked processing methods as a mixin class.
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

# Import window processing mixin
from .radial_profile_cuda_window_processing import RadialProfileCUDAWindowProcessingMixin


class RadialProfileCUDABlockedMixin(RadialProfileCUDAWindowProcessingMixin):
    """Mixin providing blocked CUDA computation methods."""
    
    def _compute_cuda_blocked_from_swap(
        self, field: np.ndarray, center: List[float], shape: tuple
    ) -> Dict[str, np.ndarray]:
        """
        Compute radial profile using window-based processing for maximum GPU utilization.

        Physical Meaning:
            Processes field using window-based approach:
            - Forms windows equal to 80% of GPU memory
            - Processes each window entirely on GPU
            - Aggregates results from all windows
            - Works with memory-mapped arrays transparently
            
        This approach maximizes GPU utilization by processing large chunks
        instead of small blocks, similar to FFT window-based processing.

        Args:
            field (np.ndarray): Field array (may be memory-mapped).
            center (List[float]): Center coordinates.
            shape (tuple): Spatial shape.

        Returns:
            Dict[str, np.ndarray]: Radial profile.
        """
        if not CUDA_AVAILABLE or not self.use_cuda:
            self.logger.warning(
                f"[RADIAL PROFILE] CPU MODE: CUDA not available or disabled in _compute_cuda_with_swap. "
                f"CUDA_AVAILABLE={CUDA_AVAILABLE}, use_cuda={self.use_cuda}"
            )
            sys.stdout.flush()
            from .radial_profile_cpu import RadialProfileComputerCPU
            cpu_computer = RadialProfileComputerCPU(logger=self.logger)
            return cpu_computer._compute_cpu(field, center)

        try:
            from ....utils.cuda_utils import calculate_optimal_window_memory
            from itertools import product
            
            self.logger.info(
                f"Processing field with window-based approach: shape={field.shape}, "
                f"CUDA={CUDA_AVAILABLE}, use_cuda={self.use_cuda}"
            )
            
            # CRITICAL: Use same window calculation as FFT solver for consistency
            # Radial profile needs ~5x memory: meshgrid (3x), distances (1x), amplitude (1x), temp arrays (2x)
            overhead_factor = 5.0
            
            # Calculate maximum window size using centralized utility function (same as FFT solver)
            max_window_elements, actual_usage_gb, actual_usage_pct = calculate_optimal_window_memory(
                gpu_memory_ratio=self.gpu_memory_ratio,
                overhead_factor=overhead_factor,
                logger=self.logger,
            )
            
            self.logger.info(
                f"Radial profile window calculation: max_window={max_window_elements/1e6:.1f}M elements, "
                f"expected usage={actual_usage_gb:.3f}GB ({actual_usage_pct:.1f}% of total GPU memory)"
            )
            sys.stdout.flush()
            
            # Calculate window size per dimension (same logic as FFT solver)
            field_elements = np.prod(field.shape)
            
            # If field fits in window, process as single window
            if field_elements <= max_window_elements:
                self.logger.info(f"Field fits in single window, processing entirely on GPU")
                return self._compute_cuda_single_block(field, center)

            # For 7D fields, calculate window size for spatial dimensions
            # Keep phase/temporal dimensions full (same approach as FFT solver)
            N_x, N_y, N_z = shape
            
            if len(field.shape) == 7:
                # Calculate window size for spatial dimensions
                # Keep phase/temporal dimensions full
                phase_temporal_size = np.prod(field.shape[3:])
                max_spatial_elements = max_window_elements // phase_temporal_size
                
                # Calculate window size per spatial dimension
                spatial_dims = field.shape[:3]
                elements_per_spatial_dim = int(max_spatial_elements ** (1.0 / 3.0))
                
                # Window size: ensure at least 32 per dimension for GPU efficiency (same as FFT solver)
                window_size = tuple(
                    max(32, min(elements_per_spatial_dim, dim))
                    for dim in spatial_dims
                ) + field.shape[3:]  # Keep phase/temporal dimensions full
            else:
                # 3D field: use all dimensions
                elements_per_dim = int(max_window_elements ** (1.0 / 3.0))
                window_size = tuple(
                    max(32, min(elements_per_dim, dim))
                    for dim in field.shape
                )

            window_elements = np.prod(window_size)
            window_size_mb = (window_elements * 16) / (1024**2)  # complex128 = 16 bytes
            
            self.logger.info(
                f"Window size: {window_size} = {window_elements/1e6:.1f}M elements = {window_size_mb:.2f}MB"
            )
            sys.stdout.flush()
            
            # Log actual GPU memory status
            try:
                mem_info = cp.cuda.runtime.memGetInfo()
                free_mem_gb = mem_info[0] / 1e9
                total_mem_gb = mem_info[1] / 1e9
                used_mem_gb = total_mem_gb - free_mem_gb
                self.logger.info(
                    f"GPU memory status: {used_mem_gb:.2f}GB used / {total_mem_gb:.2f}GB total "
                    f"({used_mem_gb/total_mem_gb*100:.1f}% used), "
                    f"{free_mem_gb:.2f}GB free"
                )
            except Exception as e:
                self.logger.warning(f"Failed to get GPU memory status: {e}")

            # Calculate number of windows needed
            num_windows_x = (N_x + window_size[0] - 1) // window_size[0]
            num_windows_y = (N_y + window_size[1] - 1) // window_size[1]
            num_windows_z = (N_z + window_size[2] - 1) // window_size[2]
            total_windows = num_windows_x * num_windows_y * num_windows_z
            
            self.logger.info(
                f"Total windows: {total_windows} ({num_windows_x}x{num_windows_y}x{num_windows_z})"
            )

            # Aggregate radial profiles from all windows
            all_r = []
            all_A = []

            # Process windows: each window is processed entirely on GPU
            # For large windows, can process sub-windows in parallel via CUDA streams
            window_idx = 0
            for wx in range(num_windows_x):
                for wy in range(num_windows_y):
                    for wz in range(num_windows_z):
                        # Calculate window boundaries
                        x_start = wx * window_size[0]
                        x_end = min(x_start + window_size[0], N_x)
                        y_start = wy * window_size[1]
                        y_end = min(y_start + window_size[1], N_y)
                        z_start = wz * window_size[2]
                        z_end = min(z_start + window_size[2], N_z)
                        
                        # Extract window
                        if len(field.shape) == 7:
                            window_slice = field[x_start:x_end, y_start:y_end, z_start:z_end, :, :, :, :]
                        else:
                            window_slice = field[x_start:x_end, y_start:y_end, z_start:z_end]

                        # CRITICAL: Copy to numpy array if memmap (same as FFT solver)
                        # memmap slices are views, need explicit copy for GPU transfer
                        if isinstance(window_slice, np.memmap):
                            self.logger.info(
                                f"[RADIAL WINDOW {window_idx+1}/{total_windows}] Copying memmap slice to numpy array, "
                                f"size: {window_slice.nbytes/1e9:.3f}GB..."
                            )
                            sys.stdout.flush()
                            window_cpu = np.array(window_slice, copy=True)
                            self.logger.info(
                                f"[RADIAL WINDOW {window_idx+1}/{total_windows}] Copy complete, "
                                f"type: {type(window_cpu).__name__}"
                            )
                            sys.stdout.flush()
                        else:
                            window_cpu = window_slice

                        # Adjust center for this window
                        window_center = [
                            center[0] - x_start,
                            center[1] - y_start,
                            center[2] - z_start,
                        ]

                        # Process window entirely on GPU with parallel sub-window processing
                        try:
                            window_profile = self._process_single_window(
                                window_cpu,
                                window_center,
                                window_idx,
                                total_windows,
                                x_start,
                                x_end,
                                y_start,
                                y_end,
                                z_start,
                                z_end,
                            )
                            all_r.append(window_profile["r"])
                            all_A.append(window_profile["A"])
                        except Exception as e:
                            # Fallback to CPU for this window
                            self.logger.warning(
                                f"GPU window processing failed: {e}, using CPU for window"
                            )
                            from .radial_profile_cpu import RadialProfileComputerCPU
                            cpu_computer = RadialProfileComputerCPU(logger=self.logger)
                            window_profile = cpu_computer._compute_cpu(window_cpu, window_center)
                            all_r.append(window_profile["r"])
                            all_A.append(window_profile["A"])

                        window_idx += 1

            # Aggregate profiles from all windows
            aggregated = self._aggregate_window_profiles(
                all_r, all_A, total_windows, field.shape
            )
            if aggregated is not None:
                return aggregated
            else:
                # Fallback to CPU if no windows processed
                from .radial_profile_cpu import RadialProfileComputerCPU
                cpu_computer = RadialProfileComputerCPU(logger=self.logger)
                return cpu_computer._compute_cpu(field, center)

        except Exception as e:
            self.logger.warning(
                f"[RADIAL PROFILE] CPU MODE: GPU window-based processing failed: {e}, falling back to CPU"
            )
            import traceback
            self.logger.debug(traceback.format_exc())
            sys.stdout.flush()
            from .radial_profile_cpu import RadialProfileComputerCPU
            cpu_computer = RadialProfileComputerCPU(logger=self.logger)
            return cpu_computer._compute_cpu(field, center)
    


    def _aggregate_subwindow_profiles(
        self, subwindow_results: List[Dict[str, np.ndarray]]
    ) -> Dict[str, np.ndarray]:
        """
        Aggregate radial profiles from multiple sub-windows processed in parallel.
        
        Physical Meaning:
            Combines radial profiles A(r) from multiple sub-windows that were
            processed in parallel via CUDA streams, ensuring proper averaging
            over all sub-windows.
            
        Args:
            subwindow_results (List[Dict[str, np.ndarray]]): List of profile
                dictionaries from sub-windows, each with 'r' and 'A' arrays.
                
        Returns:
            Dict[str, np.ndarray]: Aggregated profile with 'r' and 'A' arrays.
        """
        if not subwindow_results:
            raise ValueError("No subwindow results to aggregate")
        
        # Use first sub-window's r bins as reference
        r_ref = subwindow_results[0]["r"]
        A_combined = np.zeros_like(r_ref)
        
        # Aggregate all sub-window profiles
        for subwindow_profile in subwindow_results:
            r = subwindow_profile["r"]
            A = subwindow_profile["A"]
            
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
        
        # Average over all sub-windows
        A_combined /= len(subwindow_results)
        
        return {"r": r_ref, "A": A_combined}

