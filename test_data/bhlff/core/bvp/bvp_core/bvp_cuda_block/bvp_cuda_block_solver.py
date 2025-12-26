"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP solver methods for CUDA block processing.

This module implements BVP solving methods for CUDA block processing,
including envelope solving, quench detection, and impedance computation
with optimal GPU memory usage (80%) and fully vectorized operations.

Physical Meaning:
    Provides BVP solving methods for CUDA block processing, enabling
    efficient solution of 7D BVP envelope equation with GPU acceleration
    and optimal memory management.

Example:
    >>> solver = BVPCudaBlockSolver(processor, operations, cpu_fallback)
    >>> envelope = solver.solve_envelope(source, max_iterations, tolerance)
"""

import numpy as np
from typing import Dict, Any

try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None


class BVPCudaBlockSolver:
    """
    BVP solver methods for CUDA block processing.

    Physical Meaning:
        Provides BVP solving methods for CUDA block processing, including
        envelope solving, quench detection, and impedance computation with
        optimal GPU memory usage (80%) and fully vectorized operations.

    Mathematical Foundation:
        Implements BVP solving methods for 7D envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) with GPU acceleration.
    """

    def __init__(
        self,
        processor,
        block_operations,
        cpu_fallback,
        allow_cpu_fallback_for_tests: bool,
    ):
        """
        Initialize BVP solver for CUDA block processing.

        Physical Meaning:
            Sets up BVP solver with processor, operations, and fallback
            for efficient 7D BVP solving with GPU acceleration.

        Args:
            processor: CUDA block processor instance.
            block_operations: Block operations instance.
            cpu_fallback: CPU fallback instance.
            allow_cpu_fallback_for_tests (bool): Whether CPU fallback is allowed.
        """
        self.processor = processor
        self.block_operations = block_operations
        self.cpu_fallback = cpu_fallback
        self.allow_cpu_fallback_for_tests = allow_cpu_fallback_for_tests
        self.logger = processor.logger

    def solve_envelope(
        self,
        source: np.ndarray,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
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
        self.logger.info("Starting CUDA blocked BVP envelope solution (Level C GPU-only)")

        # Level C requires GPU - raise if CUDA unavailable (unless test fallback allowed)
        if not self.processor.cuda_available:
            if self.allow_cpu_fallback_for_tests:
                self.logger.warning(
                    "CUDA not available, using CPU fallback for non-C integration tests only"
                )
                return self.cpu_fallback.solve_envelope_cpu_fallback(
                    source, max_iterations, tolerance
                )
            else:
                raise RuntimeError(
                    "CUDA not available. Level C requires GPU acceleration. "
                    "Please install CuPy and ensure CUDA is properly configured. "
                    "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                    "(matching your CUDA version)."
                )

        # Verify 7D shape for Level C
        if source.ndim != 7:
            raise ValueError(
                f"Expected 7D source field for Level C BVP, got {source.ndim}D. "
                f"Shape: {source.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Compute optimal block tiling for 80% GPU memory usage with 7D optimization
        block_tiling = self.processor._7d_operations.compute_optimal_block_tiling_7d(
            source.shape, memory_fraction=0.8
        )
        self.logger.info(
            f"Using 7D block tiling: {block_tiling} (80% GPU memory, vectorized operations)"
        )

        # Transfer source to GPU with vectorized operation (batch transfer)
        source_gpu = cp.asarray(source, dtype=cp.complex128)

        # Initialize solution on GPU with vectorized zero initialization
        envelope_gpu = cp.zeros(self.processor.domain.shape, dtype=cp.complex128)

        # Iterative solution across blocks on GPU with fully vectorized operations
        for iteration in range(max_iterations):
            if iteration % 10 == 0:
                self.logger.info(f"CUDA BVP iteration {iteration + 1}/{max_iterations}")

            # Process each block on GPU with vectorized operations
            processed_blocks = []
            for block_data, block_info in self.processor.iterate_blocks_cuda():
                # Extract source block on GPU (vectorized slice operation)
                source_block = self.block_operations.extract_source_block_cuda(
                    source_gpu, block_info
                )

                # Solve BVP equation for this block on GPU with 7D Laplacian (fully vectorized)
                block_solution = self.processor._7d_operations.solve_block_bvp_cuda_7d(
                    block_data, source_block, block_info
                )

                processed_blocks.append((block_solution, block_info))

            # Merge blocks on GPU with vectorized operations
            new_envelope_gpu = self.processor.merge_blocks_cuda(processed_blocks)

            # Check convergence on GPU (vectorized norm computation)
            if self.block_operations.check_convergence_cuda(
                envelope_gpu, new_envelope_gpu, tolerance
            ):
                self.logger.info(f"CUDA BVP converged after {iteration + 1} iterations")
                break

            # Vectorized assignment for next iteration
            envelope_gpu = new_envelope_gpu

        # Transfer result back to CPU (batch transfer)
        envelope = cp.asnumpy(envelope_gpu)

        # Cleanup GPU memory (vectorized cleanup)
        del source_gpu, envelope_gpu
        self.processor.cleanup_cuda_memory()

        self.logger.info("CUDA BVP envelope solution completed (Level C GPU-only)")
        return envelope

    def detect_quenches(self, envelope: np.ndarray) -> Dict[str, Any]:
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
        self.logger.info("Starting CUDA blocked quench detection (Level C GPU-only)")

        # Level C requires GPU - raise if CUDA unavailable (unless test fallback allowed)
        if not self.processor.cuda_available:
            if self.allow_cpu_fallback_for_tests:
                self.logger.warning(
                    "CUDA not available, using CPU fallback for non-C integration tests only"
                )
                return self.cpu_fallback.detect_quenches_cpu_fallback(envelope)
            else:
                raise RuntimeError(
                    "CUDA not available. Level C requires GPU acceleration. "
                    "Please install CuPy and ensure CUDA is properly configured. "
                    "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                    "(matching your CUDA version)."
                )

        # Verify 7D shape for Level C
        if envelope.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope field for Level C BVP, got {envelope.ndim}D. "
                f"Shape: {envelope.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Transfer envelope to GPU with vectorized operation (batch transfer)
        envelope_gpu = cp.asarray(envelope, dtype=cp.complex128)

        quench_blocks = []
        total_quenches = 0

        # Process each block for quench detection on GPU with fully vectorized operations
        for block_data, block_info in self.processor.iterate_blocks_cuda():
            # Extract envelope block on GPU (vectorized slice operation)
            envelope_block = self.block_operations.extract_envelope_block_cuda(
                envelope_gpu, block_info
            )

            # Detect quenches in block on GPU with fully vectorized operations
            block_quenches = (
                self.block_operations.detect_block_quenches_cuda_vectorized(
                    envelope_block, block_info
                )
            )

            quench_blocks.append((block_quenches, block_info))
            total_quenches += len(block_quenches)

        # Cleanup GPU memory (vectorized cleanup)
        del envelope_gpu
        self.processor.cleanup_cuda_memory()

        self.logger.info(
            f"CUDA quench detection completed: {total_quenches} quenches found "
            f"(Level C GPU-only, vectorized)"
        )

        return {
            "total_quenches": total_quenches,
            "quench_blocks": quench_blocks,
            "detection_method": "cuda_blocked_7d_bvp_vectorized",
        }

    def compute_impedance(self, envelope: np.ndarray) -> np.ndarray:
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
        self.logger.info("Starting CUDA blocked impedance computation (Level C GPU-only)")

        # Level C requires GPU - raise if CUDA unavailable (unless test fallback allowed)
        if not self.processor.cuda_available:
            if self.allow_cpu_fallback_for_tests:
                self.logger.warning(
                    "CUDA not available, using CPU fallback for non-C integration tests only"
                )
                return self.cpu_fallback.compute_impedance_cpu_fallback(envelope)
            else:
                raise RuntimeError(
                    "CUDA not available. Level C requires GPU acceleration. "
                    "Please install CuPy and ensure CUDA is properly configured. "
                    "Install with: pip install cupy-cuda11x or cupy-cuda12x "
                    "(matching your CUDA version)."
                )

        # Verify 7D shape for Level C
        if envelope.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope field for Level C BVP, got {envelope.ndim}D. "
                f"Shape: {envelope.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Transfer envelope to GPU with vectorized operation (batch transfer)
        envelope_gpu = cp.asarray(envelope, dtype=cp.complex128)

        impedance_blocks = []

        # Process each block for impedance computation on GPU with fully vectorized operations
        for block_data, block_info in self.processor.iterate_blocks_cuda():
            # Extract envelope block on GPU (vectorized slice operation)
            envelope_block = self.block_operations.extract_envelope_block_cuda(
                envelope_gpu, block_info
            )

            # Compute impedance for block on GPU with fully vectorized operations
            block_impedance = (
                self.block_operations.compute_block_impedance_cuda_vectorized(
                    envelope_block, block_info
                )
            )

            impedance_blocks.append((block_impedance, block_info))

        # Merge impedance blocks on GPU with vectorized operations
        impedance_gpu = self.processor.merge_blocks_cuda(impedance_blocks)

        # Transfer result back to CPU (batch transfer)
        impedance = cp.asnumpy(impedance_gpu)

        # Cleanup GPU memory (vectorized cleanup)
        del envelope_gpu, impedance_gpu
        self.processor.cleanup_cuda_memory()

        self.logger.info("CUDA impedance computation completed (Level C GPU-only, vectorized)")
        return impedance

