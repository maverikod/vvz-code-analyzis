"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Blocked field processing for electroweak coupling computations.

This module implements processing of BlockedField for electroweak coupling
computations using dynamic 7D block tiling with explicit memory accounting.

Physical Meaning:
    Processes BlockedField in manageable 7D blocks using dynamic tiling
    based on 80% GPU memory, computing currents for each block separately
    with proper 7D indexing and combining results. Strict GPU path only.

Mathematical Foundation:
    - Dynamic block size calculation from 80% GPU memory
    - 7D block tiling: spatial (0,1,2), phase (3,4,5), temporal (6)
    - Explicit memory accounting prevents OOM errors
    - Vectorized GPU operations for all computations

Example:
    >>> from bhlff.core.bvp.phase_vector.electroweak_block_processing import ElectroweakBlockProcessing
    >>> block_processor = ElectroweakBlockProcessing(block_tiling, block_sizing, gpu_compute)
    >>> currents = block_processor.compute_electroweak_currents_blocked(envelope, phase_components, domain)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.domain import Domain
from bhlff.core.bvp.phase_vector.block_tiling import ElectroweakBlockTiling
from bhlff.core.bvp.phase_vector.electroweak_block_sizing import ElectroweakBlockSizing
from bhlff.core.bvp.phase_vector.electroweak_gpu_computation import ElectroweakGPUComputation

# CUDA optimization - GPU path when available
try:
    import cupy as cp

    CUDA_AVAILABLE = True
    logging.info("CUDA support enabled with CuPy")
except ImportError:
    CUDA_AVAILABLE = False
    cp = None  # type: ignore
    logging.warning(
        "CUDA not available for electroweak coupling computation. "
        "Some features may be limited. Install cupy to enable GPU acceleration."
    )


class ElectroweakBlockProcessing:
    """
    Blocked field processing for electroweak coupling computations.

    Physical Meaning:
        Processes BlockedField in manageable 7D blocks using dynamic tiling
        based on 80% GPU memory, computing currents for each block separately
        with proper 7D indexing and combining results. Strict GPU path only.

    Mathematical Foundation:
        - Dynamic block size calculation from 80% GPU memory
        - 7D block tiling: spatial (0,1,2), phase (3,4,5), temporal (6)
        - Explicit memory accounting prevents OOM errors
        - Vectorized GPU operations for all computations

    Attributes:
        block_tiling (ElectroweakBlockTiling): Block tiling calculator.
        block_sizing (ElectroweakBlockSizing): Block sizing calculator.
        gpu_compute (ElectroweakGPUComputation): GPU computation module.
        logger (logging.Logger): Logger instance.
    """

    def __init__(
        self,
        block_tiling: ElectroweakBlockTiling,
        block_sizing: ElectroweakBlockSizing,
        gpu_compute: ElectroweakGPUComputation,
    ) -> None:
        """
        Initialize block processing module.

        Physical Meaning:
            Sets up the block processing module with required dependencies
            for processing BlockedField with 7D block tiling.

        Args:
            block_tiling (ElectroweakBlockTiling): Block tiling calculator.
            block_sizing (ElectroweakBlockSizing): Block sizing calculator.
            gpu_compute (ElectroweakGPUComputation): GPU computation module.
        """
        self.block_tiling = block_tiling
        self.block_sizing = block_sizing
        self.gpu_compute = gpu_compute
        self.logger = logging.getLogger(__name__)

        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

    def compute_electroweak_currents_blocked(
        self, envelope, phase_components: List, domain: Domain
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents for BlockedField using dynamic 7D block tiling.

        Physical Meaning:
            Processes BlockedField in manageable 7D blocks using dynamic tiling
            based on 80% GPU memory, computing currents for each block separately
            with proper 7D indexing and combining results. Strict GPU path only.

        Mathematical Foundation:
            - Dynamic block size calculation from 80% GPU memory
            - 7D block tiling: spatial (0,1,2), phase (3,4,5), temporal (6)
            - Explicit memory accounting prevents OOM errors
            - Vectorized GPU operations for all computations

        Args:
            envelope: BVP envelope (BlockedField or np.ndarray).
            phase_components (List): Phase components (may include BlockedField).
            domain (Domain): Computational domain with 7D shape.

        Returns:
            Dict[str, np.ndarray]: Electroweak currents combined from all blocks.

        Raises:
            RuntimeError: If CUDA is not available.
            ValueError: If fields are not 7D.
        """
        from bhlff.core.sources.blocked_field_generator import BlockedField

        # Strict GPU path - no CPU fallback
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute electroweak currents")

        # Get field shape for tiling calculation
        if isinstance(envelope, BlockedField):
            field_shape = envelope.shape
            generator = envelope.generator
        else:
            first_blocked = next(
                (theta_a for theta_a in phase_components if isinstance(theta_a, BlockedField)),
                None
            )
            if first_blocked is None:
                field_shape = envelope.shape
                generator = None
            else:
                field_shape = first_blocked.shape
                generator = first_blocked.generator

        # Verify 7D structure
        if len(field_shape) != 7:
            raise ValueError(
                f"Expected 7D field shape for blocked processing, "
                f"got {len(field_shape)}D. Shape: {field_shape}"
            )

        # Calculate optimal 7D block tiling from GPU memory (80% limit)
        optimal_7d_tiling = self.block_sizing.compute_optimal_block_size_from_gpu_memory(field_shape)

        # Accumulate results from all blocks with 7D indexing
        result_blocks = {"em_current": [], "weak_current": [], "mixed_current": []}
        block_metadata_list = []

        # Get GPU memory info for dynamic block size adjustment
        available_memory = self.block_tiling.get_available_gpu_memory()

        # Iterate over all blocks with 7D indexing
        if generator is not None:
            for block_data, block_meta in generator.iterate_blocks(max_blocks=10000):
                block_indices_7d = block_meta["block_indices"]
                block_shape = block_meta["block_shape"]

                # Verify 7D structure
                if len(block_indices_7d) != 7 or len(block_shape) != 7:
                    raise ValueError(
                        f"Expected 7D block indices and shape, "
                        f"got {len(block_indices_7d)}D indices, {len(block_shape)}D shape"
                    )

                # Calculate memory requirement for this 7D block with explicit accounting
                # Account for: envelope (1x) + max phase (9x: base + 7 gradients + squares) + results (3x) = 13x
                required_memory = self.block_tiling.calculate_memory_requirement_7d(block_shape, overhead_factor=13.0)

                # Adjust block size dynamically if needed to fit in 80% GPU memory
                safe_shape = block_shape
                if required_memory > available_memory:
                    # Try optimal tiling first
                    safe_shape = tuple(
                        min(optimal_7d_tiling[i], block_shape[i]) for i in range(7)
                    )
                    required_memory = self.block_tiling.calculate_memory_requirement_7d(safe_shape, overhead_factor=13.0)

                    if required_memory > available_memory:
                        # Emergency reduction: compute minimal safe size with enhanced overhead
                        # Enhanced overhead: 13x for envelope + phase gradients + results
                        bytes_per_element = 16  # complex128
                        enhanced_overhead = 13.0
                        max_elements = available_memory // (bytes_per_element * enhanced_overhead)
                        if max_elements > 0:
                            elements_per_dim = int(max_elements ** (1 / 7))
                            emergency_size = max(2, elements_per_dim)
                            safe_shape = tuple(min(emergency_size, s) for s in block_shape)
                        else:
                            raise RuntimeError(
                                f"GPU memory insufficient for block {block_indices_7d}: "
                                f"required {required_memory/1e9:.2f}GB, "
                                f"available {available_memory/1e9:.2f}GB"
                            )

                        self.logger.warning(
                            f"Block {block_indices_7d} shape {block_shape} requires "
                            f"{required_memory/1e9:.2f}GB, reducing to {safe_shape}"
                        )

                    # Extract reduced block with 7D slicing
                    slice_7d = tuple(slice(0, safe_shape[i]) for i in range(7))
                    envelope_block = (
                        envelope.generator.get_block_by_indices(block_indices_7d)[slice_7d]
                        if isinstance(envelope, BlockedField)
                        else envelope[tuple(
                            slice(
                                block_indices_7d[i] * generator.block_size[i],
                                min(
                                    block_indices_7d[i] * generator.block_size[i] + safe_shape[i],
                                    (block_indices_7d[i] + 1) * generator.block_size[i],
                                    envelope.shape[i]
                                )
                            )
                            for i in range(7)
                        )]
                    )

                    phase_blocks = []
                    for theta_a in phase_components:
                        if isinstance(theta_a, BlockedField):
                            phase_block = theta_a.generator.get_block_by_indices(block_indices_7d)[slice_7d]
                        else:
                            phase_block = theta_a[tuple(
                                slice(
                                    block_indices_7d[i] * generator.block_size[i],
                                    min(
                                        block_indices_7d[i] * generator.block_size[i] + safe_shape[i],
                                        (block_indices_7d[i] + 1) * generator.block_size[i],
                                        theta_a.shape[i]
                                    )
                                )
                                for i in range(7)
                            )]
                        phase_blocks.append(phase_block)
                else:
                    # Block fits, extract normally with 7D indexing
                    envelope_block = (
                        envelope.generator.get_block_by_indices(block_indices_7d)
                        if isinstance(envelope, BlockedField)
                        else envelope[tuple(
                            slice(
                                block_indices_7d[i] * generator.block_size[i],
                                min(
                                    (block_indices_7d[i] + 1) * generator.block_size[i],
                                    envelope.shape[i]
                                )
                            )
                            for i in range(7)
                        )]
                    )

                    phase_blocks = []
                    for theta_a in phase_components:
                        if isinstance(theta_a, BlockedField):
                            phase_block = theta_a.generator.get_block_by_indices(block_indices_7d)
                        else:
                            phase_block = theta_a[tuple(
                                slice(
                                    block_indices_7d[i] * generator.block_size[i],
                                    min(
                                        (block_indices_7d[i] + 1) * generator.block_size[i],
                                        theta_a.shape[i]
                                    )
                                )
                                for i in range(7)
                            )]
                        phase_blocks.append(phase_block)
                    safe_shape = envelope_block.shape

                # Verify 7D structure before processing
                if envelope_block.ndim != 7:
                    raise ValueError(
                        f"Expected 7D envelope block, got {envelope_block.ndim}D. "
                        f"Shape: {envelope_block.shape}"
                    )

                for i, pb in enumerate(phase_blocks):
                    if pb.ndim != 7:
                        raise ValueError(
                            f"Expected 7D phase block {i}, got {pb.ndim}D. Shape: {pb.shape}"
                        )

                # Compute currents for this 7D block using strict GPU path
                block_currents = self.gpu_compute.compute_block_currents_gpu(
                    envelope_block, phase_blocks, safe_shape
                )

                # Store block results with 7D metadata for later combination
                result_blocks["em_current"].append((block_currents["em_current"], block_indices_7d))
                result_blocks["weak_current"].append((block_currents["weak_current"], block_indices_7d))
                result_blocks["mixed_current"].append((block_currents["mixed_current"], block_indices_7d))
                block_metadata_list.append(block_meta)
        else:
            raise NotImplementedError(
                "Manual 7D block iteration not implemented. "
                "Use BlockedField for proper 7D block processing."
            )

        # Combine all block results into full 7D arrays
        full_shape = domain.shape
        if len(full_shape) != 7:
            raise ValueError(
                f"Expected 7D domain shape, got {len(full_shape)}D. Shape: {full_shape}"
            )

        em_current = np.zeros(full_shape, dtype=np.complex128)
        weak_current = np.zeros(full_shape, dtype=np.complex128)
        mixed_current = np.zeros(full_shape, dtype=np.complex128)

        # Place each block result in correct position with 7D indexing
        for i, block_meta in enumerate(block_metadata_list):
            block_indices_7d = block_meta["block_indices"]
            block_shape = result_blocks["em_current"][i][0].shape

            # Calculate 7D slice for this block in full array
            slice_7d = tuple(
                slice(
                    block_indices_7d[j] * generator.block_size[j],
                    block_indices_7d[j] * generator.block_size[j] + block_shape[j]
                )
                for j in range(7)
            )

            em_block = result_blocks["em_current"][i][0]
            weak_block = result_blocks["weak_current"][i][0]
            mixed_block = result_blocks["mixed_current"][i][0]

            em_current[slice_7d] = em_block
            weak_current[slice_7d] = weak_block
            mixed_current[slice_7d] = mixed_block

        return {
            "em_current": em_current,
            "weak_current": weak_current,
            "mixed_current": mixed_current,
        }

