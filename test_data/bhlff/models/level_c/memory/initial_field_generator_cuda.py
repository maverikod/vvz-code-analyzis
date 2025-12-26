"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized initial field generator for memory evolution.

This module implements initial field generation with CUDA acceleration
and block-based processing for 7D phase field theory.

Physical Meaning:
    Generates initial field configurations for memory evolution analysis
    using block-based processing with CUDA acceleration when field size
    exceeds memory limits. Extracts 3D spatial field from 7D BlockedField
    by averaging over phase and temporal dimensions (indices 3,4,5,6) using
    vectorized operations. Preserves 7D-to-3D semantics with proper broadcasting.

Theoretical Background:
    For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
    - Field: a(x, y, z, φ₁, φ₂, φ₃, t)
    - 3D extraction: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
    - Block processing: processes blocks preserving 7D structure using generator
    - CUDA acceleration: uses 80% GPU memory limit with vectorized operations
    - Block iteration: uses generator with max_blocks limit for memory safety

Example:
    >>> generator = InitialFieldGeneratorCUDA(spatial_extractor)
    >>> field = generator.create_initial_field(domain)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


class InitialFieldGeneratorCUDA:
    """
    CUDA-optimized initial field generator with block processing.

    Physical Meaning:
        Generates initial field configurations using block-based processing
        with CUDA acceleration, preserving 7D structure and optimizing
        GPU memory usage to 80% limit.

    Mathematical Foundation:
        For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
        - Generates 7D field blocks with random perturbations
        - Extracts 3D spatial field by averaging over phase/temporal dimensions
        - Uses vectorized CUDA operations for optimal performance
        - Respects 80% GPU memory limit with adaptive block sizing
    """

    def __init__(self, spatial_extractor: Any):
        """
        Initialize CUDA-optimized initial field generator.

        Args:
            spatial_extractor: Spatial field extractor instance.
        """
        self.spatial_extractor = spatial_extractor
        self.logger = logging.getLogger(__name__)
        self.cuda_available = CUDA_AVAILABLE

    def create_initial_field(self, domain: Dict[str, Any]) -> np.ndarray:
        """
        Create initial field configuration with CUDA optimization.

        Physical Meaning:
            Creates an initial field configuration for memory evolution analysis
            using block-based processing with CUDA acceleration when field size
            exceeds memory limits.

        Mathematical Foundation:
            For 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ:
            - Field: a(x, y, z, φ₁, φ₂, φ₃, t)
            - 3D extraction: a_3d(x, y, z) = ⟨|a(x, y, z, φ₁, φ₂, φ₃, t)|⟩_{φ₁,φ₂,φ₃,t}
            - Block processing: processes blocks preserving 7D structure using generator
            - CUDA acceleration: uses 80% GPU memory limit with vectorized operations

        Args:
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            np.ndarray: Initial 3D field configuration (N, N, N).
        """
        N = domain.get("N", 64)
        L = domain.get("L", 1.0)

        # Use BlockedFieldGenerator for large fields
        if N**3 > 64**3:  # Threshold for block processing
            return self._create_blocked_field(domain, N, L)

        # Create coordinate arrays for small fields (fallback)
        return self._create_small_field(N, L)

    def _create_blocked_field(
        self, domain: Dict[str, Any], N: int, L: float
    ) -> np.ndarray:
        """
        Create blocked field with CUDA acceleration.

        Physical Meaning:
            Creates 7D blocked field using BlockedFieldGenerator with
            CUDA acceleration, preserving 7D structure and optimizing
            GPU memory usage.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            N (int): Domain size.
            L (float): Domain length.

        Returns:
            np.ndarray: 3D spatial field (N, N, N).
        """
        from bhlff.core.sources.blocked_field_generator import (
            BlockedFieldGenerator,
            BlockedField,
        )
        from bhlff.core.domain import Domain as DomainClass

        # Create 7D domain object (required by Domain class)
        # Level C works with 3D spatial fields, but Domain requires 7D
        domain_obj = DomainClass(L=L, N=N, N_phi=4, N_t=8, T=1.0, dimensions=7)

        # Create field generator function with CUDA support
        field_generator = self._create_field_generator_function()

        # Use BlockedFieldGenerator with CUDA support
        generator = BlockedFieldGenerator(
            domain_obj, field_generator, use_cuda=self.cuda_available
        )
        blocked_field = generator.get_field()

        # Process blocked field using generator with max_blocks limit
        if isinstance(blocked_field, BlockedField):
            from .blocked_field_processor_cuda import BlockedFieldProcessorCUDA

            processor = BlockedFieldProcessorCUDA(self.spatial_extractor)
            return processor.process_blocked_field_blocks(
                blocked_field, generator, N, self.cuda_available
            )
        else:
            # Fallback: if not BlockedField, try direct extraction
            if hasattr(blocked_field, "shape") and len(blocked_field.shape) == 7:
                return self.spatial_extractor.extract_spatial_from_7d_block(
                    blocked_field, self.cuda_available
                )
            else:
                # If already 3D or different shape, use absolute value
                return (
                    np.abs(blocked_field)
                    if isinstance(blocked_field, np.ndarray)
                    else np.array(blocked_field)
                )

    def _create_field_generator_function(self) -> Any:
        """
        Create field generator function with CUDA support.

        Physical Meaning:
            Creates a function that generates 7D field blocks with
            random perturbations using CUDA if available.

        Returns:
            Callable: Field generator function.
        """

        def field_generator(
            domain: Any,
            slice_config: Dict[str, Any],
            config: Dict[str, Any],
        ) -> np.ndarray:
            """
            Generate initial field block with random perturbations.

            Physical Meaning:
                Generates 7D field block with random perturbations for
                initial field configuration. Uses CUDA if available with
                vectorized operations respecting 80% GPU memory limit.

            Args:
                domain: 7D domain object.
                slice_config (Dict[str, Any]): Slice configuration.
                config (Dict[str, Any]): Generator configuration.

            Returns:
                np.ndarray: 7D field block.
            """
            block_shape = slice_config["shape"]
            use_cuda = slice_config.get("use_cuda", False) and self.cuda_available

            if use_cuda and self.cuda_available:
                # Generate on GPU using vectorized operations
                field_block = cp.random.rand(*block_shape) + 1j * cp.random.rand(
                    *block_shape
                )
                field_block *= 0.1  # Small amplitude
                # Convert to CPU for consistency
                return cp.asnumpy(field_block)
            else:
                # Generate on CPU using vectorized operations
                field_block = np.random.rand(*block_shape) + 1j * np.random.rand(
                    *block_shape
                )
                field_block *= 0.1  # Small amplitude
                return field_block

        return field_generator

    def _create_small_field(self, N: int, L: float) -> np.ndarray:
        """
        Create small field without block processing.

        Physical Meaning:
            Creates initial field for small domains without block processing,
            using direct vectorized operations.

        Args:
            N (int): Domain size.
            L (float): Domain length.

        Returns:
            np.ndarray: Initial 3D field (N, N, N).
        """
        # Create coordinate arrays for small fields (fallback)
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create initial field with random perturbations using vectorized operations
        field = np.random.rand(N, N, N) + 1j * np.random.rand(N, N, N)
        field *= 0.1  # Small amplitude

        return field

