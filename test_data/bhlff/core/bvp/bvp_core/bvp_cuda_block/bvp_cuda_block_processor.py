"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

CUDA-optimized BVP block processor for 7D domain operations.

This module implements CUDA-accelerated BVP block processing for 7D domains
to handle memory-efficient BVP computations on large 7D space-time grids.

Physical Meaning:
    Provides CUDA-accelerated BVP block processing for 7D phase field computations,
    enabling memory-efficient BVP operations on large 7D space-time domains
    using GPU acceleration for maximum performance.

Example:
    >>> bvp_processor = BVPCUDABlockProcessor(domain, config, block_size=8)
    >>> envelope = bvp_processor.solve_envelope_cuda_blocked(source)
"""

import numpy as np
from typing import Dict, Any, Optional

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None

from ....domain.cuda_block_processor import CUDABlockProcessor
from ....domain.domain import Domain
from ..bvp_operations import BVPCoreOperations
from ..bvp_cuda_block_processor_helpers import BVPCudaBlockProcessorHelpers
from bhlff.utils.cuda_backend_7d_ops import CUDABackend7DOps

from .bvp_cuda_7d_operations import BVPCuda7DOperations
from .bvp_cuda_block_operations import BVPCudaBlockOperations
from .bvp_cuda_cpu_fallback import BVPCudaCPUFallback
from .bvp_cuda_block_solver import BVPCudaBlockSolver


class BVPCUDABlockProcessor(CUDABlockProcessor):
    """
    CUDA-optimized BVP block processor for 7D domain operations.

    Physical Meaning:
        Provides CUDA-accelerated BVP block processing for 7D phase field
        computations, enabling memory-efficient BVP operations on large
        7D space-time domains using GPU acceleration.

    Mathematical Foundation:
        Implements CUDA-accelerated block decomposition of 7D BVP envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) with GPU memory management.
    """

    def __init__(
        self,
        domain: Domain,
        config: Dict[str, Any],
        block_size: int = 8,
        overlap: int = 2,
    ):
        """
        Initialize CUDA BVP block processor.

        Physical Meaning:
            Sets up CUDA-accelerated BVP block processing system for 7D phase field
            computations with GPU memory management and BVP-specific optimizations.

        Args:
            domain (Domain): 7D computational domain.
            config (Dict[str, Any]): BVP configuration parameters.
            block_size (int): Size of each processing block.
            overlap (int): Overlap between adjacent blocks for continuity.
        """
        super().__init__(domain, block_size, overlap)

        self.config = config

        # Initialize BVP operations for CUDA block processing
        self.bvp_operations = BVPCoreOperations(domain, config, None)

        # CUDA-specific BVP parameters
        self._setup_cuda_bvp_parameters()

        # Initialize helper methods
        self.helpers = BVPCudaBlockProcessorHelpers(config)

        # Initialize 7D operations for vectorized 7D Laplacian
        self._7d_ops = CUDABackend7DOps() if self.cuda_available else None

        # Check if CPU fallback is allowed for non-C integration tests
        self.allow_cpu_fallback_for_tests = config.get(
            "allow_cpu_fallback_for_tests", False
        )

        # Initialize modular components
        self._7d_operations = BVPCuda7DOperations(
            domain, config, self._7d_ops, block_size
        )
        self._block_operations = BVPCudaBlockOperations()
        self._cpu_fallback = BVPCudaCPUFallback(
            domain, config, block_size, overlap, self.allow_cpu_fallback_for_tests
        )

        # Initialize BVP solver for CUDA block processing
        self._solver = BVPCudaBlockSolver(
            self,
            self._block_operations,
            self._cpu_fallback,
            self.allow_cpu_fallback_for_tests,
        )

        # For Level C: require CUDA unless explicitly allowed for tests
        if not self.cuda_available and not self.allow_cpu_fallback_for_tests:
            raise RuntimeError(
                "CUDA not available. Level C requires GPU acceleration. "
                "Please install CuPy and ensure CUDA is properly configured. "
                "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                "(matching your CUDA version). "
                "For non-C integration tests only, set allow_cpu_fallback_for_tests=True in config."
            )

        self.logger.info(f"CUDA BVP block processor initialized: {self.cuda_available}")

    def _setup_cuda_bvp_parameters(self) -> None:
        """Setup CUDA-specific BVP parameters."""
        if not self.cuda_available:
            return

        # Extract BVP parameters and convert to CUDA arrays
        env_eq = self.config.get("envelope_equation", {})

        self.kappa_0 = cp.float32(env_eq.get("kappa_0", 1.0))
        self.kappa_2 = cp.float32(env_eq.get("kappa_2", 0.1))
        self.chi_prime = cp.float32(env_eq.get("chi_prime", 1.0))
        self.chi_double_prime_0 = cp.float32(env_eq.get("chi_double_prime_0", 0.1))
        self.k0 = cp.float32(env_eq.get("k0", 1.0))

        # Carrier frequency
        self.carrier_frequency = cp.float32(self.config.get("carrier_frequency", 1e15))

        self.logger.info("CUDA BVP parameters initialized")

    def solve_envelope_cuda_blocked(
        self, source: np.ndarray, max_iterations: int = 100, tolerance: float = 1e-6
    ) -> np.ndarray:
        """
        Solve BVP envelope equation using CUDA block processing.

        Physical Meaning:
            Solves the 7D BVP envelope equation using CUDA-accelerated block processing
            to handle memory-efficient computations on large domains with optimal GPU
            memory usage (80%) and fully vectorized operations.

        Mathematical Foundation:
            Solves ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) using CUDA block decomposition
            with iterative solution across blocks on GPU. Uses 7D Laplacian
            Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for proper 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.
            All operations are vectorized for optimal GPU performance.

        Args:
            source (np.ndarray): Source term s(x,φ,t) with 7D shape.
            max_iterations (int): Maximum number of iterations.
            tolerance (float): Convergence tolerance.

        Returns:
            np.ndarray: Solution envelope a(x,φ,t) with 7D shape.

        Raises:
            RuntimeError: If CUDA is not available (Level C requirement).
            ValueError: If source is not 7D.
        """
        return self._solver.solve_envelope(source, max_iterations, tolerance)

    def detect_quenches_cuda_blocked(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Detect quenches using CUDA block processing.

        Physical Meaning:
            Detects quenches in the 7D phase field using CUDA-accelerated block processing
            to handle memory-efficient quench detection on large domains with optimal GPU
            memory usage (80%) and fully vectorized operations.

        Mathematical Foundation:
            Detects quench events in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ using vectorized
            threshold-based detection with GPU acceleration for optimal performance.

        Args:
            envelope (np.ndarray): Envelope field data with 7D shape.

        Returns:
            Dict[str, Any]: Quench detection results with positions and amplitudes.

        Raises:
            RuntimeError: If CUDA is not available (Level C requirement).
            ValueError: If envelope is not 7D.
        """
        return self._solver.detect_quenches(envelope)

    def compute_impedance_cuda_blocked(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute impedance using CUDA block processing.

        Physical Meaning:
            Computes impedance of the 7D phase field using CUDA-accelerated block processing
            to handle memory-efficient impedance computation on large domains with optimal GPU
            memory usage (80%) and fully vectorized operations.

        Mathematical Foundation:
            Computes impedance Z = |a| exp(iφ) in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            where |a| is amplitude and φ is phase, using vectorized GPU operations
            for optimal performance.

        Args:
            envelope (np.ndarray): Envelope field data with 7D shape.

        Returns:
            np.ndarray: Impedance field with 7D shape.

        Raises:
            RuntimeError: If CUDA is not available (Level C requirement).
            ValueError: If envelope is not 7D.
        """
        return self._solver.compute_impedance(envelope)

    def get_cuda_bvp_info(self) -> Dict[str, Any]:
        """Get CUDA BVP-specific information."""
        cuda_info = self.get_cuda_info()
        memory_usage = self.get_memory_usage_cuda()

        return {
            **cuda_info,
            **memory_usage,
            "bvp_parameters": {
                "kappa_0": float(self.kappa_0) if self.cuda_available else None,
                "kappa_2": float(self.kappa_2) if self.cuda_available else None,
                "chi_prime": float(self.chi_prime) if self.cuda_available else None,
                "chi_double_prime_0": (
                    float(self.chi_double_prime_0) if self.cuda_available else None
                ),
                "k0": float(self.k0) if self.cuda_available else None,
                "carrier_frequency": (
                    float(self.carrier_frequency) if self.cuda_available else None
                ),
            },
            "bvp_operations": "cuda_blocked" if self.cuda_available else "cpu_blocked",
            "gpu_acceleration": self.cuda_available,
        }

