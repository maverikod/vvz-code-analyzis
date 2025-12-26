"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic source generation methods for BVP source generators.

This module provides basic source generation methods as a mixin class.
"""

import numpy as np
from typing import Callable, Optional, Tuple

from ...arrays import FieldArray
from ..blocked_field_generator import BlockedFieldGenerator
from ...domain.optimal_block_size_calculator import (
    OptimalBlockSizeCalculator,
    get_default_block_calculator,
)
from bhlff.utils.cuda_backend import CUDABackend

try:
    import cupy as cp
    CUDA_AVAILABLE = True
except Exception:
    CUDA_AVAILABLE = False
    cp = None


class BVPSourceGeneratorsBasicMixin:
    """Mixin providing basic source generation methods."""
    
    _block_size_calculator: Optional[OptimalBlockSizeCalculator] = None

    def generate_gaussian_source(self) -> 'FieldArray':
        """
        Generate Gaussian source.
        
        Physical Meaning:
            Creates a Gaussian source distribution centered at a specified
            location with given width and amplitude.
        """
        self._ensure_cuda()

        amplitude = self.config.get("gaussian_amplitude", 1.0)
        center = self.config.get("gaussian_center", [0.5, 0.5, 0.5])
        width = self.config.get("gaussian_width", 0.1)

        swap_threshold = self.config.get("swap_threshold_gb")

        def gaussian_block(domain, slice_config, runtime_config):
            start = tuple(slice_config["start"])
            shape = tuple(slice_config["shape"])
            xp = cp
            x, y, z = self._create_spatial_axes(start, shape, xp, normalized=True)
            X, Y, Z = xp.meshgrid(x, y, z, indexing="ij")
            dx = X - center[0]
            dy = Y - center[1]
            dz = Z - center[2]
            r_squared = dx**2 + dy**2 + dz**2
            spatial_block = amplitude * self._step_resonator_source(r_squared, width, xp=xp)
            return self._expand_spatial_block(spatial_block, shape, xp)

        return self._materialize_field_array(gaussian_block, swap_threshold_gb=swap_threshold)
    
    def generate_point_source(self) -> 'FieldArray':
        """
        Generate point source.
        
        Physical Meaning:
            Creates a point source at a specified location with given
            amplitude, representing a localized excitation. Uses block-aware
            generation to handle large 7D fields efficiently.
        """
        self._ensure_cuda()

        # Get point source parameters
        amplitude = self.config.get("point_amplitude", 1.0)
        location = self.config.get("point_location", [0.5, 0.5, 0.5])

        # Find closest grid points to source location
        grid_size = getattr(self.domain, "N", self.domain.shape[0])
        i = int(location[0] * (grid_size - 1))
        j = int(location[1] * (grid_size - 1))
        k = int(location[2] * (grid_size - 1))

        swap_threshold = self.config.get("swap_threshold_gb")

        def point_source_block(domain, slice_config, runtime_config):
            start = tuple(slice_config["start"])
            shape = tuple(slice_config["shape"])
            xp = cp
            
            # Create zero block
            spatial_block = xp.zeros(shape[:3], dtype=xp.complex128)
            
            # Check if point source location is within this block
            block_start_x, block_start_y, block_start_z = start[:3]
            block_end_x = block_start_x + shape[0]
            block_end_y = block_start_y + shape[1]
            block_end_z = block_start_z + shape[2]
            
            if (block_start_x <= i < block_end_x and
                block_start_y <= j < block_end_y and
                block_start_z <= k < block_end_z):
                # Point source is in this block
                local_i = i - block_start_x
                local_j = j - block_start_y
                local_k = k - block_start_z
                spatial_block[local_i, local_j, local_k] = amplitude
            
            return self._expand_spatial_block(spatial_block, shape, xp)

        return self._materialize_field_array(point_source_block, swap_threshold_gb=swap_threshold)
    
    def generate_distributed_source(self) -> 'FieldArray':
        """
        Generate distributed source.
        
        Physical Meaning:
            Creates a distributed source with specified spatial distribution
            and amplitude profile. Uses block-aware generation to handle large
            7D fields efficiently.
        """
        self._ensure_cuda()

        amplitude = self.config.get("distributed_amplitude", 1.0)
        distribution_type = self.config.get("distribution_type", "sine")

        swap_threshold = self.config.get("swap_threshold_gb")

        def distributed_block(domain, slice_config, runtime_config):
            start = tuple(slice_config["start"])
            shape = tuple(slice_config["shape"])
            xp = cp
            x, y, z = self._create_spatial_axes(start, shape, xp, normalized=True)
            X, Y, Z = xp.meshgrid(x, y, z, indexing="ij")

            if distribution_type == "sine":
                kx = self.config.get("sine_kx", 2 * np.pi)
                ky = self.config.get("sine_ky", 2 * np.pi)
                kz = self.config.get("sine_kz", 2 * np.pi)
                spatial_block = amplitude * (xp.sin(kx * X) * xp.sin(ky * Y) * xp.sin(kz * Z))
            elif distribution_type == "cosine":
                kx = self.config.get("cosine_kx", 2 * np.pi)
                ky = self.config.get("cosine_ky", 2 * np.pi)
                kz = self.config.get("cosine_kz", 2 * np.pi)
                spatial_block = amplitude * (xp.cos(kx * X) * xp.cos(ky * Y) * xp.cos(kz * Z))
            elif distribution_type == "polynomial":
                order = self.config.get("polynomial_order", 2)
                spatial_block = amplitude * (X**order + Y**order + Z**order)
            else:
                spatial_block = amplitude * xp.ones_like(X)

            return self._expand_spatial_block(spatial_block, shape, xp)

        return self._materialize_field_array(distributed_block, swap_threshold_gb=swap_threshold)
    
    def generate_plane_wave_source(self) -> 'FieldArray':
        """
        Generate plane wave source.
        
        Physical Meaning:
            Creates a plane wave source with specified wave vector (mode)
            and amplitude, representing a monochromatic excitation.
            For 7D domains, generates 7D field directly matching domain shape.
            
        Mathematical Foundation:
            Plane wave has the form:
            s(x) = A * exp(i * k · x)
            where k is the wave vector and A is the amplitude.
            For 7D: s(x,φ,t) = A * exp(i * k · x) (constant across phase/time).
            
        Returns:
            FieldArray: Plane wave source field with shape matching domain.shape.
        """
        self._ensure_cuda()

        amplitude = self.config.get("plane_wave_amplitude", 1.0)
        mode = self.config.get("plane_wave_mode", [1, 0, 0])  # Default mode (1,0,0)
        
        # Convert mode to tuple if needed
        if isinstance(mode, (list, np.ndarray)):
            mode = tuple(int(m) for m in mode)
        
        grid_size = getattr(self.domain, "N", self.domain.shape[0])

        swap_threshold = self.config.get("swap_threshold_gb")

        def plane_wave_block(domain, slice_config, runtime_config):
            start = tuple(slice_config["start"])
            shape = tuple(slice_config["shape"])
            xp = cp
            indices = self._create_spatial_axes(start, shape, xp, normalized=False)
            grid = xp.meshgrid(*indices, indexing="ij")
            phase = xp.zeros(shape[:3], dtype=xp.float64)
            for m_i, g_i in zip(mode, grid):
                phase += (2.0 * xp.pi * m_i * g_i) / max(1, grid_size)
            spatial_block = amplitude * xp.exp(1j * phase)
            return self._expand_spatial_block(spatial_block, shape, xp)

        return self._materialize_field_array(plane_wave_block, swap_threshold_gb=swap_threshold)

    # ------------------------------------------------------------------ #
    # Helper methods for block-aware generation                          #
    # ------------------------------------------------------------------ #

    def _ensure_cuda(self) -> None:
        """
        Ensure CUDA is available for source generation.
        
        Physical Meaning:
            Enforces CUDA requirement for source generation operations,
            ensuring GPU acceleration is available before proceeding.
            
        Raises:
            RuntimeError: If CUDA is not available.
        """
        if not self.use_cuda or not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for source generation. CPU fallback is not supported."
            )
        # Use shared require_cuda() helper for consistent error messages
        CUDABackend.require_cuda()

    def _materialize_field_array(
        self,
        block_fn: Callable,
        dtype: np.dtype = np.complex128,
        swap_threshold_gb: Optional[float] = None,
    ) -> FieldArray:
        """
        Materialize FieldArray from block generator with swap support.
        
        Physical Meaning:
            Creates FieldArray by streaming blocks from generator, automatically
            using swap for large fields exceeding threshold. Logs block sizes
            and swap usage for diagnostics.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        block_size = self._get_block_size(dtype)
        logger.info(
            f"Materializing FieldArray: domain_shape={self.domain.shape}, "
            f"block_size={block_size}, swap_threshold_gb={swap_threshold_gb}"
        )
        
        generator = BlockedFieldGenerator(
            domain=self.domain,
            field_generator=block_fn,
            block_size=tuple(block_size),
            config=self.config,
            use_cuda=True,
        )
        field = FieldArray.from_block_generator(
            block_generator=generator,
            dtype=dtype,
            swap_threshold_gb=swap_threshold_gb,
        )
        
        logger.info(
            f"FieldArray materialized: shape={field.shape}, "
            f"is_swapped={field.is_swapped}, size_mb={field.nbytes/(1024**2):.2f}MB"
        )
        
        return field

    def _get_block_size(self, dtype: np.dtype) -> Tuple[int, ...]:
        """
        Get optimal block size for 7D domain using unified calculator.
        
        Physical Meaning:
            Calculates optimal block size per dimension for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring 80% GPU memory usage while
            preserving 7D geometric structure.
            
        Args:
            dtype (np.dtype): Data type for memory calculation.
            
        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple).
        """
        if self._block_size_calculator is None:
            # Use default calculator with 80% GPU memory ratio
            self._block_size_calculator = get_default_block_calculator(gpu_memory_ratio=0.8)
        return self._block_size_calculator.calculate_for_7d(
            domain_shape=tuple(self.domain.shape),
            dtype=dtype,
        )

    def _create_spatial_axes(
        self,
        start: Tuple[int, ...],
        shape: Tuple[int, ...],
        xp,
        *,
        normalized: bool,
    ):
        axes = []
        grid_size = getattr(self.domain, "N", shape[0])
        denom = max(1, grid_size - 1)
        for axis in range(min(3, len(shape))):
            axis_start = start[axis]
            axis_len = shape[axis]
            values = xp.arange(axis_start, axis_start + axis_len, dtype=xp.float64)
            if normalized:
                values = values / denom
            axes.append(values)
        return axes

    def _expand_spatial_block(self, spatial_block, block_shape, xp):
        spatial_shape = block_shape[: spatial_block.ndim]
        target_shape = block_shape
        if len(target_shape) <= spatial_block.ndim:
            return spatial_block.astype(xp.complex128)

        reshape_dims = spatial_shape + (1,) * (len(target_shape) - spatial_block.ndim)
        expanded = spatial_block.reshape(reshape_dims)
        broadcast_shape = (1, 1, 1) + tuple(target_shape[3:])
        ones = xp.ones(broadcast_shape, dtype=spatial_block.dtype)
        result = (expanded * ones).astype(xp.complex128)
        return result

