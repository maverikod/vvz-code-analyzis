"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized BVP processor for 7D domain operations.

This module implements fully vectorized BVP processing for 7D domains
to handle memory-efficient BVP computations on large 7D space-time grids.

Physical Meaning:
    Provides vectorized BVP processing for 7D phase field computations,
    enabling memory-efficient BVP operations on large 7D space-time domains
    using vectorized operations for maximum performance.

Example:
    >>> bvp_processor = BVPVectorizedProcessor(domain, config, block_size=8)
    >>> envelope = bvp_processor.solve_envelope_vectorized(source)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List
import logging

try:
    import cupy as cp
    import cupyx.scipy.ndimage as cp_ndimage
    import cupyx.scipy.sparse as cp_sparse

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = None
    cp_ndimage = None
    cp_sparse = None

from ...domain.vectorized_block_processor import VectorizedBlockProcessor
from ...domain.block_processor import BlockInfo
from ...domain import Domain
from .bvp_operations import BVPCoreOperations
from .bvp_vectorized_processor_helpers import BVPVectorizedProcessorHelpers


class BVPVectorizedProcessor(VectorizedBlockProcessor):
    """
    Vectorized BVP processor for 7D domain operations.

    Physical Meaning:
        Provides vectorized BVP processing for 7D phase field
        computations, enabling memory-efficient BVP operations on large
        7D space-time domains using vectorized operations.

    Mathematical Foundation:
        Implements vectorized BVP envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) with vectorized operations.
    """

    def __init__(
        self,
        domain: Domain,
        config: Dict[str, Any],
        block_size: int = 8,
        overlap: int = 2,
        use_cuda: bool = True,
    ):
        """
        Initialize vectorized BVP processor.

        Physical Meaning:
            Sets up vectorized BVP processing system for 7D phase field
            computations with CUDA acceleration if available.

        Args:
            domain (Domain): 7D computational domain.
            config (Dict[str, Any]): BVP configuration parameters.
            block_size (int): Size of each processing block.
            overlap (int): Overlap between adjacent blocks for continuity.
            use_cuda (bool): Whether to use CUDA acceleration if available.
        """
        super().__init__(domain, block_size, overlap, use_cuda)

        self.config = config

        # Initialize BVP operations for vectorized processing
        self.bvp_operations = BVPCoreOperations(domain, config, None)

        # Vectorized BVP parameters
        self._setup_vectorized_bvp_parameters()

        # Initialize helper methods
        self.helpers = BVPVectorizedProcessorHelpers(config)

        self.logger.info(f"Vectorized BVP processor initialized: CUDA={self.use_cuda}")

    def _setup_vectorized_bvp_parameters(self) -> None:
        """Setup vectorized BVP parameters."""
        # Extract BVP parameters
        env_eq = self.config.get("envelope_equation", {})

        self.kappa_0 = env_eq.get("kappa_0", 1.0)
        self.kappa_2 = env_eq.get("kappa_2", 0.1)
        self.chi_prime = env_eq.get("chi_prime", 1.0)
        self.chi_double_prime_0 = env_eq.get("chi_double_prime_0", 0.1)
        self.k0 = env_eq.get("k0", 1.0)

        # Carrier frequency
        self.carrier_frequency = self.config.get("carrier_frequency", 1e15)

        # Convert to appropriate array type
        if self.use_cuda:
            self.kappa_0 = cp.float32(self.kappa_0)
            self.kappa_2 = cp.float32(self.kappa_2)
            self.chi_prime = cp.float32(self.chi_prime)
            self.chi_double_prime_0 = cp.float32(self.chi_double_prime_0)
            self.k0 = cp.float32(self.k0)
            self.carrier_frequency = cp.float32(self.carrier_frequency)

        self.logger.info("Vectorized BVP parameters initialized")

    def solve_envelope_vectorized(
        self,
        source: np.ndarray,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
        batch_size: int = 8,
    ) -> np.ndarray:
        """
        Solve BVP envelope equation using vectorized processing.

        Physical Meaning:
            Solves the 7D BVP envelope equation using vectorized processing
            to handle memory-efficient computations on large domains.

        Mathematical Foundation:
            Solves ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t) using vectorized
            block decomposition with iterative solution across blocks.

        Args:
            source (np.ndarray): Source term s(x,φ,t).
            max_iterations (int): Maximum number of iterations.
            tolerance (float): Convergence tolerance.
            batch_size (int): Number of blocks to process in parallel.

        Returns:
            np.ndarray: Solution envelope a(x,φ,t).
        """
        self.logger.info("Starting vectorized BVP envelope solution")

        if self.use_cuda:
            return self._solve_envelope_cuda_vectorized(
                source, max_iterations, tolerance, batch_size
            )
        else:
            return self._solve_envelope_cpu_vectorized(
                source, max_iterations, tolerance, batch_size
            )

    def _solve_envelope_cuda_vectorized(
        self, source: np.ndarray, max_iterations: int, tolerance: float, batch_size: int
    ) -> np.ndarray:
        """Solve envelope using CUDA vectorized processing."""
        # Transfer source to GPU
        source_gpu = cp.asarray(source)

        # Initialize solution on GPU
        envelope_gpu = cp.zeros(self.domain.shape, dtype=cp.complex128)

        # Iterative solution with vectorized processing
        for iteration in range(max_iterations):
            self.logger.info(
                f"Vectorized BVP iteration {iteration + 1}/{max_iterations}"
            )

            # Process all blocks vectorized on GPU
            processed_blocks = []
            for block_data, block_info in self.iterate_blocks():
                # Extract source block on GPU
                source_block = self._extract_source_block_vectorized(
                    source_gpu, block_info
                )

                # Solve BVP equation for this block on GPU
                block_solution = self._solve_block_bvp_vectorized(
                    block_data, source_block, block_info
                )

                processed_blocks.append((block_solution, block_info))

            # Process blocks in batches vectorized
            batch_processed = self._process_batch_cuda_vectorized(
                processed_blocks, "bvp_solve", batch_size
            )

            # Merge blocks on GPU
            new_envelope_gpu = self.merge_blocks_cuda(batch_processed)

            # Check convergence on GPU
            if self._check_convergence_vectorized(
                envelope_gpu, new_envelope_gpu, tolerance
            ):
                self.logger.info(
                    f"Vectorized BVP converged after {iteration + 1} iterations"
                )
                break

            envelope_gpu = new_envelope_gpu

        # Transfer result back to CPU
        envelope = cp.asnumpy(envelope_gpu)

        # Cleanup GPU memory
        del source_gpu, envelope_gpu
        cp.get_default_memory_pool().free_all_blocks()

        self.logger.info("Vectorized BVP envelope solution completed")
        return envelope

    def _solve_envelope_cpu_vectorized(
        self, source: np.ndarray, max_iterations: int, tolerance: float, batch_size: int
    ) -> np.ndarray:
        """Solve envelope using CPU vectorized processing."""
        # Initialize solution
        envelope = np.zeros(self.domain.shape, dtype=np.complex128)

        # Iterative solution with vectorized processing
        for iteration in range(max_iterations):
            self.logger.info(
                f"Vectorized BVP iteration {iteration + 1}/{max_iterations}"
            )

            # Process all blocks vectorized on CPU
            processed_blocks = []
            for block_data, block_info in self.iterate_blocks():
                # Extract source block
                source_block = self._extract_source_block_vectorized(source, block_info)

                # Solve BVP equation for this block
                block_solution = self._solve_block_bvp_vectorized(
                    block_data, source_block, block_info
                )

                processed_blocks.append((block_solution, block_info))

            # Process blocks in batches vectorized
            batch_processed = self._process_batch_cpu_vectorized(
                processed_blocks, "bvp_solve", batch_size
            )

            # Merge blocks
            new_envelope = self.merge_blocks(batch_processed)

            # Check convergence
            if self._check_convergence_vectorized(envelope, new_envelope, tolerance):
                self.logger.info(
                    f"Vectorized BVP converged after {iteration + 1} iterations"
                )
                break

            envelope = new_envelope

        self.logger.info("Vectorized BVP envelope solution completed")
        return envelope

    def _extract_source_block_vectorized(
        self, source: np.ndarray, block_info
    ) -> np.ndarray:
        """Extract source block for given block info."""
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        return source[slices]

    def _solve_block_bvp_vectorized(
        self, current_block: np.ndarray, source_block: np.ndarray, block_info
    ) -> np.ndarray:
        """
        Solve BVP equation for a single block using vectorized operations.

        Physical Meaning:
            Solves the BVP envelope equation for a single block
            using vectorized operations for maximum performance.

        Args:
            current_block (np.ndarray): Current solution block.
            source_block (np.ndarray): Source term block.
            block_info: Block information.

        Returns:
            np.ndarray: Solution block.
        """
        # Apply vectorized BVP operations to block
        # Full BVP solver implementation with proper boundary conditions
        # according to 7D BVP theory principles

        # Compute stiffness matrix for block vectorized
        stiffness_block = self._compute_block_stiffness_vectorized(
            current_block, block_info
        )

        # Compute susceptibility for block vectorized
        susceptibility_block = self._compute_block_susceptibility_vectorized(
            current_block, block_info
        )

        # Solve linear system for block vectorized
        lhs = stiffness_block + susceptibility_block
        rhs = source_block

        # Solve using vectorized method
        if self.use_cuda:
            if cp.linalg.det(lhs) != 0:
                solution_block = cp.linalg.solve(lhs, rhs)
            else:
                solution_block = self._solve_block_iterative_vectorized(
                    lhs, rhs, current_block
                )
        else:
            if np.linalg.det(lhs) != 0:
                solution_block = np.linalg.solve(lhs, rhs)
            else:
                solution_block = self._solve_block_iterative_vectorized(
                    lhs, rhs, current_block
                )

        return solution_block

    def _compute_block_stiffness_vectorized(
        self, block_data: np.ndarray, block_info
    ) -> np.ndarray:
        """Compute stiffness matrix for block using vectorized operations."""
        # Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|² vectorized
        amplitude_squared = np.abs(block_data) ** 2
        stiffness = self.kappa_0 + self.kappa_2 * amplitude_squared

        # Create full stiffness matrix vectorized according to 7D BVP theory
        stiffness_matrix = self.helpers.compute_full_stiffness_matrix_vectorized(
            block_data, block_info, stiffness
        )

        return stiffness_matrix.reshape(block_data.shape + block_data.shape)

    def _compute_block_susceptibility_vectorized(
        self, block_data: np.ndarray, block_info
    ) -> np.ndarray:
        """Compute susceptibility for block using vectorized operations."""
        # Compute susceptibility χ(|a|) = χ' + iχ''(|a|) vectorized
        amplitude = np.abs(block_data)
        susceptibility = self.chi_prime + 1j * self.chi_double_prime_0 * amplitude

        # Create full susceptibility matrix vectorized according to 7D BVP theory
        susceptibility_matrix = (
            self.helpers.compute_full_susceptibility_matrix_vectorized(
                block_data, block_info, susceptibility
            )
        )

        return susceptibility_matrix.reshape(block_data.shape + block_data.shape)

    def _solve_block_iterative_vectorized(
        self, lhs: np.ndarray, rhs: np.ndarray, initial_guess: np.ndarray
    ) -> np.ndarray:
        """Solve block using vectorized iterative method."""
        # Vectorized iterative solver (Gauss-Seidel)
        solution = initial_guess.copy()

        for _ in range(10):  # Maximum iterations
            old_solution = solution.copy()

            # Update solution vectorized
            if self.use_cuda:
                for i in range(solution.size):
                    if lhs[i, i] != 0:
                        solution.flat[i] = (
                            rhs.flat[i] - cp.dot(lhs[i, :], solution.flat)
                        ) / lhs[i, i]

                # Check convergence vectorized
                if cp.allclose(solution, old_solution, rtol=1e-6):
                    break
            else:
                for i in range(solution.size):
                    if lhs[i, i] != 0:
                        solution.flat[i] = (
                            rhs.flat[i] - np.dot(lhs[i, :], solution.flat)
                        ) / lhs[i, i]

                # Check convergence vectorized
                if np.allclose(solution, old_solution, rtol=1e-6):
                    break

        return solution

    def _check_convergence_vectorized(
        self, old_solution: np.ndarray, new_solution: np.ndarray, tolerance: float
    ) -> bool:
        """Check convergence of iterative solution using vectorized operations."""
        if old_solution.size == 0:
            return False

        if self.use_cuda:
            relative_error = cp.linalg.norm(
                new_solution - old_solution
            ) / cp.linalg.norm(old_solution)
        else:
            relative_error = np.linalg.norm(
                new_solution - old_solution
            ) / np.linalg.norm(old_solution)

        return relative_error < tolerance

    def detect_quenches_vectorized(
        self, envelope: np.ndarray, batch_size: int = 8
    ) -> Dict[str, Any]:
        """
        Detect quenches using vectorized processing.

        Physical Meaning:
            Detects quenches in the 7D phase field using vectorized processing
            to handle memory-efficient quench detection on large domains.

        Args:
            envelope (np.ndarray): Envelope field data.
            batch_size (int): Number of blocks to process in parallel.

        Returns:
            Dict[str, Any]: Quench detection results.
        """
        self.logger.info("Starting vectorized quench detection")

        if self.use_cuda:
            return self._detect_quenches_cuda_vectorized(envelope, batch_size)
        else:
            return self._detect_quenches_cpu_vectorized(envelope, batch_size)

    def _detect_quenches_cuda_vectorized(
        self, envelope: np.ndarray, batch_size: int
    ) -> Dict[str, Any]:
        """Detect quenches using CUDA vectorized processing."""
        # Transfer envelope to GPU
        envelope_gpu = cp.asarray(envelope)

        quench_blocks = []
        total_quenches = 0

        # Process blocks in batches for quench detection on GPU
        all_blocks = list(self.iterate_blocks())
        for i in range(0, len(all_blocks), batch_size):
            batch_blocks = all_blocks[i : i + batch_size]

            # Extract envelope blocks for batch
            envelope_blocks = []
            for block_data, block_info in batch_blocks:
                envelope_block = self._extract_envelope_block_vectorized(
                    envelope_gpu, block_info
                )
                envelope_blocks.append((envelope_block, block_info))

            # Detect quenches in batch vectorized
            batch_quenches = self._detect_batch_quenches_cuda_vectorized(
                envelope_blocks
            )

            quench_blocks.extend(batch_quenches)
            total_quenches += sum(len(quenches) for quenches, _ in batch_quenches)

        # Cleanup GPU memory
        del envelope_gpu
        cp.get_default_memory_pool().free_all_blocks()

        self.logger.info(
            f"Vectorized quench detection completed: {total_quenches} quenches found"
        )

        return {
            "total_quenches": total_quenches,
            "quench_locations": quench_locations,
            "quench_times": quench_times,
            "quench_amplitudes": quench_amplitudes,
        }
