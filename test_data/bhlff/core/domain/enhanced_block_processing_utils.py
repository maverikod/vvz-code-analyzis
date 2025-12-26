"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Utility methods for enhanced block processor.

This module implements utility methods for block size calculation, memory checking,
and CUDA availability verification for 7D BVP computations.
"""

import numpy as np
import logging
import psutil
from typing import Tuple

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from .domain import Domain
from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps
from .enhanced_block_processing import ProcessingConfig
from .optimal_block_size_calculator import OptimalBlockSizeCalculator
from bhlff.utils.gpu_memory_monitor import GPUMemoryMonitor
from bhlff.utils.cpu_memory_monitor import CPUMemoryMonitor


class EnhancedBlockProcessorUtils:
    """
    Utility methods for enhanced block processor.

    Physical Meaning:
        Provides utility methods for block size calculation, memory checking,
        and CUDA availability verification for 7D BVP computations with
        80% GPU memory usage optimization.

    Mathematical Foundation:
        Implements 7D block tiling optimization:
        - 7D block tiling: optimized for 80% GPU memory usage
        - Memory requirement estimation for 7D operations
        - CUDA availability verification
    """

    def __init__(
        self,
        domain: Domain,
        config: ProcessingConfig,
        cuda_available: bool,
        logger: logging.Logger,
    ):
        """
        Initialize utility methods.

        Args:
            domain (Domain): 7D computational domain.
            config (ProcessingConfig): Processing configuration.
            cuda_available (bool): Whether CUDA is available.
            logger (logging.Logger): Logger instance.
        """
        self.domain = domain
        self.config = config
        self.cuda_available = cuda_available
        self.logger = logger

        # Initialize 7D operations support
        self._7d_ops = None
        if self.cuda_available and CUDA_AVAILABLE:
            self._7d_ops = CUDABackend7DOps()
        
        # Initialize unified block size calculator
        self._block_size_calculator = OptimalBlockSizeCalculator(
            gpu_memory_ratio=0.8  # Use 80% GPU memory (project requirement)
        )
        
        # Initialize memory monitors
        self._gpu_memory_monitor = GPUMemoryMonitor(
            warning_threshold=0.75,
            critical_threshold=0.9,
        ) if cuda_available and CUDA_AVAILABLE else None
        
        self._cpu_memory_monitor = CPUMemoryMonitor(
            warning_threshold=0.75,
            critical_threshold=0.9,
        )

    def calculate_optimal_block_size(self) -> int:
        """
        Calculate optimal block size based on available memory and domain size.

        Physical Meaning:
            Calculates optimal block size to maximize processing efficiency
            while staying within memory constraints. Uses unified
            OptimalBlockSizeCalculator for consistent 80% GPU memory usage.

        Mathematical Foundation:
            For 7D domain with shape (N₀, N₁, N₂, N₃, N₄, N₅, N₆):
            - GPU: uses 80% of free GPU memory with 7D block tiling
            - CPU: uses configurable fraction of system memory

        Returns:
            int: Optimal block size.
        """
        # Use unified block size calculator
        try:
            block_tiling = self._block_size_calculator.calculate_for_7d(
                domain_shape=self.domain.shape,
                dtype=np.complex128,
                overhead_factor=10.0,  # Higher overhead for complex operations
            )
            # Use minimum block size from tiling (all dimensions should be similar)
            optimal_size = min(block_tiling)
            
            # Apply config constraints
            optimal_size = min(optimal_size, self.config.max_block_size)
            optimal_size = max(optimal_size, self.config.min_block_size)
            
            # Ensure it's reasonable for the domain
            for dim_size in self.domain.shape:
                optimal_size = min(optimal_size, dim_size)
            
            self.logger.info(
                f"Optimal 7D block tiling: {block_tiling}, "
                f"using block_size={optimal_size} (80% GPU memory via unified calculator)"
            )
            return optimal_size
        except Exception as e:
            self.logger.warning(
                f"Failed to compute optimal block size with unified calculator: {e}, "
                f"falling back to legacy calculation"
            )
            # Fallback to legacy calculation
            return self._calculate_optimal_block_size_legacy()
    
    def _calculate_optimal_block_size_legacy(self) -> int:
        """
        Legacy block size calculation (fallback).
        
        Physical Meaning:
            Legacy calculation method used as fallback when unified
            calculator fails.
            
        Returns:
            int: Optimal block size.
        """
        # CPU fallback: use system memory
        available_memory = psutil.virtual_memory().available / (1024**3)  # GB
        usable_memory = available_memory * self.config.max_memory_usage

        # Calculate domain size
        domain_size = np.prod(self.domain.shape)
        element_size = 16  # complex128 = 16 bytes

        # Calculate maximum block size that fits in memory
        max_block_size = int(
            (usable_memory * 1024**3 / (element_size * 8))
            ** (1.0 / len(self.domain.shape))
        )

        # Apply constraints
        optimal_size = min(max_block_size, self.config.max_block_size)
        optimal_size = max(optimal_size, self.config.min_block_size)

        # Ensure it's reasonable for the domain
        for dim_size in self.domain.shape:
            optimal_size = min(optimal_size, dim_size)

        self.logger.info(
            f"Optimal block size (legacy): {optimal_size} "
            f"(available memory: {available_memory:.2f} GB)"
        )

        return optimal_size

    @staticmethod
    def check_cuda_availability() -> bool:
        """
        Check if CUDA is available.

        Physical Meaning:
            Verifies CUDA availability by checking GPU device access.

        Returns:
            bool: True if CUDA is available, False otherwise.
        """
        if not CUDA_AVAILABLE or cp is None:
            return False

        try:
            cp.cuda.Device(0).compute_capability
            return True
        except Exception:
            return False

    def check_memory_requirements(
        self, field: np.ndarray, level_c_context: bool = False
    ) -> bool:
        """
        Check if there's enough memory for processing.

        Physical Meaning:
            Verifies that available memory is sufficient for processing
            the 7D field with the current block configuration.
            For Level C contexts, checks GPU memory instead of CPU memory
            with 80% usage rule.

        Mathematical Foundation:
            For 7D operations:
            - GPU memory: 80% of free GPU memory (project requirement)
            - CPU memory: configurable fraction of system memory
            - Memory overhead: ~5x for 7D GPU operations, ~3x for CPU

        Args:
            field (np.ndarray): Field to check memory for.
            level_c_context (bool): If True, checks GPU memory instead of CPU.

        Returns:
            bool: True if sufficient memory is available.

        Raises:
            RuntimeError: If Level C context requires GPU memory check but it fails.
        """
        # For Level C, check GPU memory (80% usage rule)
        if level_c_context and self.cuda_available and CUDA_AVAILABLE:
            if self._gpu_memory_monitor is None:
                raise RuntimeError("GPU memory monitor not initialized for Level C context")
            
            try:
                # Use GPUMemoryMonitor for consistent memory checking
                gpu_mem_info = self._gpu_memory_monitor.check_memory()
                
                # Estimate memory requirements for 7D field processing
                field_memory = field.nbytes / (1024**3)  # GB
                # For 7D operations, need ~5x memory overhead (FFT, Laplacian, etc.)
                processing_memory = field_memory * 5
                # Use 80% of free GPU memory (project requirement)
                available_memory_gpu = (gpu_mem_info["free"] / (1024**3)) * 0.8

                sufficient = available_memory_gpu >= processing_memory

                if not sufficient:
                    self.logger.warning(
                        f"Insufficient GPU memory for Level C: "
                        f"required={processing_memory:.2f} GB, "
                        f"available={available_memory_gpu:.2f} GB "
                        f"(80% of {gpu_mem_info['free'] / (1024**3):.2f} GB free, "
                        f"total={gpu_mem_info['total'] / (1024**3):.2f} GB, "
                        f"usage={gpu_mem_info['usage_ratio']:.1%})"
                    )

                return sufficient
            except MemoryError as e:
                # GPUMemoryMonitor raised MemoryError for critical usage
                self.logger.error(f"GPU memory critical: {e}")
                raise RuntimeError(
                    f"Level C requires GPU memory but it's critical: {e}"
                ) from e
            except Exception as e:
                self.logger.error(f"Failed to check GPU memory: {e}")
                # For Level C, if GPU memory check fails, it's an error
                if level_c_context:
                    raise RuntimeError(
                        f"Level C requires GPU memory check but it failed: {e}"
                    ) from e
                return False

        # For non-Level C, check CPU memory using CPUMemoryMonitor
        field_memory_bytes = field.nbytes
        processing_memory_bytes = field_memory_bytes * 3  # 3x for processing overhead
        required_memory_bytes = int(processing_memory_bytes / self.config.max_memory_usage)
        
        try:
            cpu_mem_info = self._cpu_memory_monitor.check_memory(required_bytes=required_memory_bytes)
            sufficient = cpu_mem_info.get("sufficient", True)
            
            if not sufficient:
                self.logger.warning(
                    f"Insufficient CPU memory: required={required_memory_bytes / (1024**3):.2f} GB, "
                    f"available={cpu_mem_info.get('available_limit', 0) / (1024**3):.2f} GB "
                    f"(usage={cpu_mem_info['usage_ratio']:.1%})"
                )
            
            return sufficient
        except MemoryError as e:
            # CPUMemoryMonitor raised MemoryError for insufficient memory
            self.logger.error(f"CPU memory insufficient: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to check CPU memory: {e}")
            return False

