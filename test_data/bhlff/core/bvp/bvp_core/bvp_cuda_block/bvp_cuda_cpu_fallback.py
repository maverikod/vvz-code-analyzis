"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CPU fallback methods for BVP CUDA block processing.

This module implements CPU fallback methods for non-C integration tests
when CUDA is not available. Level C production code requires GPU.

Physical Meaning:
    Provides CPU fallback for non-C integration tests when explicitly
    enabled via config. Level C production code must use GPU.

Note:
    These methods are only for non-C integration tests. Level C requires GPU.
    All methods enforce GPU-only execution for Level C production code paths.
"""

import numpy as np
import logging
from typing import Dict, Any

from ...domain import Domain


class BVPCudaCPUFallback:
    """
    CPU fallback methods for BVP CUDA block processing.

    Physical Meaning:
        Provides CPU fallback for non-C integration tests when explicitly
        enabled via config. Level C production code must use GPU.
        All methods enforce GPU-only execution for Level C production code paths
        by raising RuntimeError if allow_cpu_fallback_for_tests is not True.
    """

    def __init__(
        self,
        domain: Domain,
        config: dict,
        block_size: int,
        overlap: int,
        allow_cpu_fallback_for_tests: bool = False,
    ):
        """
        Initialize CPU fallback methods.

        Physical Meaning:
            Sets up CPU fallback system with explicit check for test-only usage.
            Level C production code paths will raise RuntimeError if CUDA is not
            available, enforcing GPU-only execution.

        Args:
            domain (Domain): 7D computational domain.
            config (dict): BVP configuration parameters.
            block_size (int): Size of each processing block.
            overlap (int): Overlap between adjacent blocks.
            allow_cpu_fallback_for_tests (bool): Whether CPU fallback is allowed
                for non-C integration tests only. Default: False (GPU-only for Level C).
        """
        self.domain = domain
        self.config = config
        self.block_size = block_size
        self.overlap = overlap
        self.allow_cpu_fallback_for_tests = allow_cpu_fallback_for_tests
        self.logger = logging.getLogger(__name__)

    def solve_envelope_cpu_fallback(
        self, source: np.ndarray, max_iterations: int, tolerance: float
    ) -> np.ndarray:
        """
        Fallback to CPU processing for non-C integration tests only.

        Physical Meaning:
            Provides CPU fallback for non-C integration tests when explicitly
            enabled via config. Level C production code must use GPU.
            This method enforces GPU-only execution for Level C by raising
            RuntimeError if allow_cpu_fallback_for_tests is not True.

        Mathematical Foundation:
            Solves 7D BVP envelope equation ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
            using CPU fallback with 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for
            7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Args:
            source (np.ndarray): Source term s(x,φ,t) with 7D shape.
            max_iterations (int): Maximum number of iterations.
            tolerance (float): Convergence tolerance.

        Returns:
            np.ndarray: Solution envelope a(x,φ,t) with 7D shape.

        Raises:
            RuntimeError: If allow_cpu_fallback_for_tests is False (Level C
                production code requires GPU-only execution).
            ValueError: If source is not 7D.

        Note:
            This method is only for non-C integration tests. Level C requires GPU.
        """
        # Level C production code requires GPU - enforce GPU-only execution
        if not self.allow_cpu_fallback_for_tests:
            raise RuntimeError(
                "CPU fallback is disabled for Level C production code. "
                "Level C requires GPU acceleration with CUDA. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). "
                "For non-C integration tests only, set allow_cpu_fallback_for_tests=True in config."
            )

        # Verify 7D shape for Level C
        if source.ndim != 7:
            raise ValueError(
                f"Expected 7D source field for Level C BVP, got {source.ndim}D. "
                f"Shape: {source.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        self.logger.warning(
            "Using CPU fallback for non-C integration tests only. "
            "Level C production code requires GPU acceleration."
        )

        from ..bvp_block_processor import BVPBlockProcessor

        cpu_processor = BVPBlockProcessor(
            self.domain, self.config, self.block_size, self.overlap
        )
        return cpu_processor.solve_envelope_blocked(source, max_iterations, tolerance)

    def detect_quenches_cpu_fallback(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Fallback to CPU quench detection for non-C integration tests only.

        Physical Meaning:
            Provides CPU fallback for non-C integration tests when explicitly
            enabled via config. Level C production code must use GPU.
            This method enforces GPU-only execution for Level C by raising
            RuntimeError if allow_cpu_fallback_for_tests is not True.

        Mathematical Foundation:
            Detects quench events in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ using
            threshold-based detection with CPU fallback for non-C integration tests.

        Args:
            envelope (np.ndarray): Envelope field data with 7D shape.

        Returns:
            Dict[str, Any]: Quench detection results with positions and amplitudes.

        Raises:
            RuntimeError: If allow_cpu_fallback_for_tests is False (Level C
                production code requires GPU-only execution).
            ValueError: If envelope is not 7D.

        Note:
            This method is only for non-C integration tests. Level C requires GPU.
        """
        # Level C production code requires GPU - enforce GPU-only execution
        if not self.allow_cpu_fallback_for_tests:
            raise RuntimeError(
                "CPU fallback is disabled for Level C production code. "
                "Level C requires GPU acceleration with CUDA. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). "
                "For non-C integration tests only, set allow_cpu_fallback_for_tests=True in config."
            )

        # Verify 7D shape for Level C
        if envelope.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope field for Level C BVP, got {envelope.ndim}D. "
                f"Shape: {envelope.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        self.logger.warning(
            "Using CPU fallback for non-C integration tests only. "
            "Level C production code requires GPU acceleration."
        )

        from ..bvp_block_processor import BVPBlockProcessor

        cpu_processor = BVPBlockProcessor(
            self.domain, self.config, self.block_size, self.overlap
        )
        return cpu_processor.detect_quenches_blocked(envelope)

    def compute_impedance_cpu_fallback(self, envelope: np.ndarray) -> np.ndarray:
        """
        Fallback to CPU impedance computation for non-C integration tests only.

        Physical Meaning:
            Provides CPU fallback for non-C integration tests when explicitly
            enabled via config. Level C production code must use GPU.
            This method enforces GPU-only execution for Level C by raising
            RuntimeError if allow_cpu_fallback_for_tests is not True.

        Mathematical Foundation:
            Computes impedance Z = |a| exp(iφ) in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            where |a| is amplitude and φ is phase, using CPU fallback for
            non-C integration tests.

        Args:
            envelope (np.ndarray): Envelope field data with 7D shape.

        Returns:
            np.ndarray: Impedance field with 7D shape.

        Raises:
            RuntimeError: If allow_cpu_fallback_for_tests is False (Level C
                production code requires GPU-only execution).
            ValueError: If envelope is not 7D.

        Note:
            This method is only for non-C integration tests. Level C requires GPU.
        """
        # Level C production code requires GPU - enforce GPU-only execution
        if not self.allow_cpu_fallback_for_tests:
            raise RuntimeError(
                "CPU fallback is disabled for Level C production code. "
                "Level C requires GPU acceleration with CUDA. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). "
                "For non-C integration tests only, set allow_cpu_fallback_for_tests=True in config."
            )

        # Verify 7D shape for Level C
        if envelope.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope field for Level C BVP, got {envelope.ndim}D. "
                f"Shape: {envelope.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        self.logger.warning(
            "Using CPU fallback for non-C integration tests only. "
            "Level C production code requires GPU acceleration."
        )

        from ..bvp_block_processor import BVPBlockProcessor

        cpu_processor = BVPBlockProcessor(
            self.domain, self.config, self.block_size, self.overlap
        )
        return cpu_processor.compute_impedance_blocked(envelope)

