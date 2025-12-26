"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Electroweak coupling implementation for U(1)³ phase vector structure.

This module implements electroweak coupling coefficients and current
calculations for the U(1)³ phase vector structure in the BVP framework.

Physical Meaning:
    Implements electromagnetic and weak interaction currents that are
    generated as functionals of the BVP envelope through the U(1)³
    phase structure with proper Weinberg mixing.

Mathematical Foundation:
    Computes electroweak currents:
    - J_EM = g_EM * |A|² * ∇Θ_EM
    - J_weak = g_weak * |A|⁴ * ∇Θ_weak
    where Θ_EM and Θ_weak are combinations of Θ_a components.

Example:
    >>> coupling = ElectroweakCoupling(config)
    >>> currents = coupling.compute_currents(envelope, phase_components)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.domain import Domain
from bhlff.core.bvp.phase_vector.block_tiling import ElectroweakBlockTiling
from bhlff.core.bvp.phase_vector.block_processor import ElectroweakBlockProcessor
from bhlff.core.bvp.phase_vector.electroweak_block_sizing import ElectroweakBlockSizing
from bhlff.core.bvp.phase_vector.electroweak_gpu_computation import ElectroweakGPUComputation
from bhlff.core.bvp.phase_vector.electroweak_block_processing import ElectroweakBlockProcessing

# CUDA optimization - strict GPU path only
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


class ElectroweakCoupling:
    """
    Electroweak coupling for U(1)³ phase vector structure (facade).

    Physical Meaning:
        Implements electromagnetic and weak interaction currents
        that are generated as functionals of the BVP envelope
        through the U(1)³ phase structure.

    Mathematical Foundation:
        Computes electroweak currents with proper Weinberg mixing
        and gauge coupling coefficients.

    Attributes:
        config (Dict[str, Any]): Electroweak coupling configuration.
        electroweak_coefficients (Dict[str, float]): Coupling coefficients.
        block_tiling (ElectroweakBlockTiling): Block tiling calculator.
        block_processor (ElectroweakBlockProcessor): Block processor.
        block_sizing (ElectroweakBlockSizing): Block sizing calculator.
        gpu_compute (ElectroweakGPUComputation): GPU computation module.
        block_processing (ElectroweakBlockProcessing): Block processing module.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize electroweak coupling.

        Physical Meaning:
            Sets up the coefficients for electroweak currents
            that are generated as functionals of the envelope.

        Args:
            config (Dict[str, Any]): Electroweak configuration including:
                - em_coupling: Electromagnetic coupling strength
                - weak_coupling: Weak interaction coupling strength
                - mixing_angle: Weinberg mixing angle
                - gauge_coupling: Gauge coupling strength
        """
        self.config = config

        # CUDA optimization setup - strict GPU path only
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

        self.cuda_available = CUDA_AVAILABLE
        self.use_cuda = True  # Strict GPU path - no CPU fallback
        self.logger = logging.getLogger(__name__)

        try:
            mem_info = cp.cuda.runtime.memGetInfo()
            free_memory_gb = mem_info[0] / (1024**3)
            self.logger.info(
                f"ElectroweakCoupling: CUDA optimization enabled "
                f"({free_memory_gb:.2f} GB free)"
            )
        except Exception as e:
            self.logger.error(f"Could not check CUDA memory: {e}")
            raise RuntimeError(f"CUDA memory check failed: {e}") from e

        self._setup_electroweak_coefficients()

        # Initialize helper classes
        self.block_tiling = ElectroweakBlockTiling()
        self.block_processor = ElectroweakBlockProcessor(self.electroweak_coefficients)

        # Initialize specialized modules
        self.block_sizing = ElectroweakBlockSizing(self.block_tiling)
        self.gpu_compute = ElectroweakGPUComputation(self.electroweak_coefficients)
        self.block_processing = ElectroweakBlockProcessing(
            self.block_tiling, self.block_sizing, self.gpu_compute
        )

    def _setup_electroweak_coefficients(self) -> None:
        """
        Setup electroweak coupling coefficients.

        Physical Meaning:
            Initializes the coefficients for electroweak currents
            that are generated as functionals of the envelope.
        """
        electroweak_config = self.config.get("electroweak", {})

        self.electroweak_coefficients = {
            "em_coupling": electroweak_config.get("em_coupling", 1.0),
            "weak_coupling": electroweak_config.get("weak_coupling", 0.1),
            "mixing_angle": electroweak_config.get(
                "mixing_angle", 0.23
            ),  # Weinberg angle
            "gauge_coupling": electroweak_config.get("gauge_coupling", 0.65),
        }

        # Update modules with coefficients if they exist
        if hasattr(self, "block_processor"):
            self.block_processor.electroweak_coefficients = self.electroweak_coefficients
        if hasattr(self, "gpu_compute"):
            self.gpu_compute.electroweak_coefficients = self.electroweak_coefficients

    def compute_electroweak_currents(
        self, envelope, phase_components: List, domain: Domain
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents as functionals of the envelope.

        Physical Meaning:
            Computes electromagnetic and weak currents that are
            generated as functionals of the BVP envelope through
            the U(1)³ phase structure using strict GPU path with
            dynamic 7D block tiling based on 80% free VRAM.

        Mathematical Foundation:
            J_EM = g_EM * |A|² * ∇Θ_EM
            J_weak = g_weak * |A|⁴ * ∇Θ_weak
            where Θ_EM and Θ_weak are combinations of Θ_a components.
            All gradients computed in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Args:
            envelope: BVP envelope |A| (np.ndarray or BlockedField).
            phase_components (List): Three U(1) phase components (may be BlockedField).
            domain (Domain): Computational domain with 7D shape.

        Returns:
            Dict[str, np.ndarray]: Electroweak currents including:
                - em_current: Electromagnetic current
                - weak_current: Weak interaction current
                - mixed_current: Mixed electroweak current

        Raises:
            RuntimeError: If CUDA is not available or memory insufficient.
            ValueError: If fields are not 7D.
        """
        # Strict GPU path - no CPU fallback
        if not CUDA_AVAILABLE:
            raise RuntimeError(
                "CUDA is required for electroweak coupling computation. "
                "Install cupy to enable GPU acceleration."
            )

        # Handle BlockedField - process block by block with dynamic 7D tiling
        from bhlff.core.sources.blocked_field_generator import BlockedField

        has_blocked = (
            isinstance(envelope, BlockedField) or
            any(isinstance(theta_a, BlockedField) for theta_a in phase_components)
        )

        if has_blocked:
            # Process BlockedField with dynamic 7D block tiling and explicit memory accounting
            return self._compute_electroweak_currents_blocked(
                envelope, phase_components, domain
            )

        # For regular numpy arrays - verify 7D structure and process with strict GPU path
        envelope_shape = envelope.shape
        if len(envelope_shape) != 7:
            raise ValueError(
                f"Expected 7D envelope for electroweak coupling, "
                f"got {len(envelope_shape)}D. Shape: {envelope_shape}"
            )

        for i, theta_a in enumerate(phase_components):
            if len(theta_a.shape) != 7:
                raise ValueError(
                    f"Expected 7D phase component {i} for electroweak coupling, "
                    f"got {len(theta_a.shape)}D. Shape: {theta_a.shape}"
                )

        # Calculate memory requirement with explicit 7D accounting
        # Account for all intermediate arrays: envelope + 3 phase components (sequential)
        # + 7 gradients per phase (7D) + gradient squares + currents (3 types)
        envelope_memory = self.block_tiling.calculate_memory_requirement_7d(envelope_shape)
        
        # For each phase component: base + 7 gradients (one per axis) + gradient squares
        # Memory per phase: base + 7 * base (gradients) + base (squares) = 9x base
        bytes_per_element = 16  # complex128
        max_phase_memory = 0
        for theta_a in phase_components:
            phase_elements = np.prod(theta_a.shape)
            # Base phase + 7 gradients (7D) + gradient squares + gradient magnitude
            phase_memory = phase_elements * bytes_per_element * 9  # 9x overhead
            max_phase_memory = max(max_phase_memory, phase_memory)
        
        # Result currents: 3 types (em, weak, mixed) = 3x envelope
        envelope_elements = np.prod(envelope_shape)
        result_memory = envelope_elements * bytes_per_element * 3
        
        # Total memory: envelope + max phase (with all gradients) + results
        # Phases processed sequentially, so only max needed, not sum
        total_memory_needed = envelope_memory + max_phase_memory + result_memory

        available_mem = self.block_tiling.get_available_gpu_memory()

        if total_memory_needed > available_mem:
            # Calculate optimal 7D block tiling from GPU memory (80% limit)
            optimal_tiling = self._compute_optimal_block_size_from_gpu_memory(envelope_shape)
            raise RuntimeError(
                f"Arrays too large for GPU memory. Use BlockedField instead.\n"
                f"  Required: {total_memory_needed/1e9:.2f} GB\n"
                f"  Available: {available_mem/1e9:.2f} GB (80% of free VRAM)\n"
                f"  Suggested 7D block tiling: {optimal_tiling}"
            )

        self.logger.info(
            f"Memory check passed: {total_memory_needed/1e9:.2f}GB required, "
            f"{available_mem/1e9:.2f}GB available ({total_memory_needed/available_mem*100:.1f}% usage)"
        )

        # Process directly on GPU with strict GPU path and vectorized 7D operations
        return self._compute_block_currents_gpu(
            envelope, phase_components, envelope_shape
        )

    def _compute_electroweak_currents_blocked(
        self, envelope, phase_components: List, domain: Domain
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents for BlockedField using dynamic 7D block tiling.

        Processes BlockedField in manageable 7D blocks using dynamic tiling based on
        80% GPU memory with explicit memory accounting. All operations preserve 7D
        structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with vectorized GPU operations.

        Args:
            envelope: BVP envelope (BlockedField or np.ndarray).
            phase_components (List): Phase components (may include BlockedField).
            domain (Domain): Computational domain with 7D shape.

        Returns:
            Dict[str, np.ndarray]: Electroweak currents combined from all blocks.
        """
        # Strict GPU path - no CPU fallback
        if not CUDA_AVAILABLE:
            raise RuntimeError("CUDA not available - cannot compute electroweak currents")

        # Use specialized block processing module with dynamic 7D tiling
        return self.block_processing.compute_electroweak_currents_blocked(
            envelope, phase_components, domain
        )

    def _compute_block_currents_gpu(
        self,
        envelope_block: np.ndarray,
        phase_blocks: List[np.ndarray],
        block_shape: Tuple[int, ...],
    ) -> Dict[str, np.ndarray]:
        """
        Compute electroweak currents for a 7D block on GPU with vectorization.

        Computes electroweak currents for a single 7D block using strict GPU path
        with vectorized operations. All operations preserve 7D structure M₇ =
        ℝ³ₓ × 𝕋³_φ × ℝₜ with explicit memory management.

        Args:
            envelope_block: Envelope block (7D numpy array, will be transferred to GPU).
            phase_blocks: Phase component blocks (list of 7D numpy arrays).
            block_shape: Shape of the 7D block.

        Returns:
            Dict[str, np.ndarray]: Currents for this 7D block (CPU arrays).
        """
        # Strict GPU path - use specialized GPU computation module
        return self.gpu_compute.compute_block_currents_gpu(
            envelope_block, phase_blocks, block_shape
        )

    def _compute_optimal_block_size_from_gpu_memory(
        self, field_shape: Tuple[int, ...], overhead_factor: float = 10.0
    ) -> Tuple[int, ...]:
        """
        Compute optimal 7D block size from GPU memory with explicit accounting.

        Calculates optimal block size per dimension for 7D space-time M₇ =
        ℝ³ₓ × 𝕋³_φ × ℝₜ based on 80% of free GPU memory. Accounts for all
        intermediate arrays: envelope (1x) + max phase (9x) + results (3x) = 13x.

        Args:
            field_shape (Tuple[int, ...]): Shape of 7D field array (must be 7D).
            overhead_factor (float): Memory overhead factor (default: 10.0).
                Note: Actual overhead is ~13x due to 7D gradients.

        Returns:
            Tuple[int, ...]: Optimal block size per dimension (7-tuple).
        """
        # Enhanced overhead factor accounting for 7D gradients:
        # envelope (1x) + max phase with 7 gradients (9x: base + 7 gradients + squares) + results (3x) = 13x
        # Use maximum of provided overhead and computed overhead
        enhanced_overhead = max(overhead_factor, 13.0)
        
        # Use specialized block sizing module with 80% GPU memory limit and enhanced overhead
        return self.block_sizing.compute_optimal_block_size_from_gpu_memory(
            field_shape, enhanced_overhead
        )

    def get_electroweak_coefficients(self) -> Dict[str, float]:
        """Get electroweak coupling coefficients."""
        return self.electroweak_coefficients.copy()

    def set_electroweak_coefficients(self, coefficients: Dict[str, float]) -> None:
        """
        Set electroweak coupling coefficients.

        Args:
            coefficients (Dict[str, float]): New coupling coefficients.
        """
        self.electroweak_coefficients.update(coefficients)
        self.block_processor.electroweak_coefficients = self.electroweak_coefficients
        self.gpu_compute.electroweak_coefficients = self.electroweak_coefficients

    def get_weinberg_angle(self) -> float:
        """Get the Weinberg mixing angle."""
        return self.electroweak_coefficients["mixing_angle"]

    def set_weinberg_angle(self, angle: float) -> None:
        """
        Set the Weinberg mixing angle.

        Args:
            angle (float): New Weinberg mixing angle.
        """
        self.electroweak_coefficients["mixing_angle"] = angle
        self.block_processor.electroweak_coefficients = self.electroweak_coefficients
        self.gpu_compute.electroweak_coefficients = self.electroweak_coefficients

    def __repr__(self) -> str:
        """String representation of electroweak coupling."""
        cuda_status = "CUDA" if self.use_cuda else "CPU"
        return (
            f"ElectroweakCoupling("
            f"em_coupling={self.electroweak_coefficients['em_coupling']:.3f}, "
            f"weak_coupling={self.electroweak_coefficients['weak_coupling']:.3f}, "
            f"mixing_angle={self.electroweak_coefficients['mixing_angle']:.3f}, "
            f"compute={cuda_status})"
        )
