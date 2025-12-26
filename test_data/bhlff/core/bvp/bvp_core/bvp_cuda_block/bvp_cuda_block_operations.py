"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block operations for BVP CUDA block processing.

This module implements block-level operations for BVP CUDA block processing,
including iterative solving, convergence checking, quench detection, and
impedance computation with vectorized CUDA operations.

Physical Meaning:
    Provides block-level operations for BVP CUDA block processing,
    enabling efficient processing of individual blocks with vectorized
    GPU operations for optimal performance.

Mathematical Foundation:
    Implements block-level operations:
    - Iterative solving: Gauss-Seidel with vectorization
    - Convergence checking: vectorized norm computation
    - Quench detection: vectorized threshold-based detection
    - Impedance computation: Z = |a| exp(iφ) with vectorization
"""

from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    try:
        import cupy as cp
    except ImportError:
        cp = None
else:
    try:
        import cupy as cp
    except ImportError:
        cp = None


class BVPCudaBlockOperations:
    """
    Block operations for BVP CUDA block processing.

    Physical Meaning:
        Provides block-level operations for BVP CUDA block processing
        with vectorized GPU operations for optimal performance.
    """

    def __init__(self):
        """
        Initialize block operations.
        
        Physical Meaning:
            No initialization required as all operations are stateless
            and use the global CUDA backend via cupy module.
        """
        # No initialization needed - all operations use global cupy (cp) module
        # and do not require instance state

    def solve_block_iterative_cuda(
        self, lhs: "cp.ndarray", rhs: "cp.ndarray", initial_guess: "cp.ndarray"
    ) -> "cp.ndarray":
        """
        Solve block using vectorized CUDA iterative method.

        Physical Meaning:
            Solves linear system using vectorized CUDA-accelerated iterative
            solver (Gauss-Seidel) for optimal GPU performance.

        Args:
            lhs (cp.ndarray): Left-hand side matrix on GPU.
            rhs (cp.ndarray): Right-hand side vector on GPU.
            initial_guess (cp.ndarray): Initial guess on GPU.

        Returns:
            cp.ndarray: Solution on GPU.
        """
        # CUDA-accelerated iterative solver (Gauss-Seidel) with vectorization
        solution = initial_guess.copy()

        for iteration in range(10):  # Maximum iterations
            old_solution = solution.copy()

            # Vectorized update solution on GPU
            # Use vectorized operations where possible
            diagonal = cp.diag(lhs)
            diagonal = cp.where(cp.abs(diagonal) < 1e-12, 1e-12, diagonal)

            # Vectorized matrix-vector product
            residual = rhs - cp.dot(lhs, solution)
            solution = solution + residual / diagonal

            # Vectorized convergence check on GPU
            if cp.allclose(solution, old_solution, rtol=1e-6):
                break

        # Synchronize GPU operations
        cp.cuda.Stream.null.synchronize()

        return solution

    def check_convergence_cuda(
        self, old_solution: "cp.ndarray", new_solution: "cp.ndarray", tolerance: float
    ) -> bool:
        """
        Check convergence of iterative solution on GPU using vectorized operations.

        Physical Meaning:
            Computes relative error between iterations using vectorized GPU
            operations for optimal performance.

        Args:
            old_solution (cp.ndarray): Previous solution on GPU.
            new_solution (cp.ndarray): New solution on GPU.
            tolerance (float): Convergence tolerance.

        Returns:
            bool: True if converged, False otherwise.
        """
        if old_solution.size == 0:
            return False

        # Vectorized norm computation on GPU
        diff = new_solution - old_solution
        relative_error = cp.linalg.norm(diff) / cp.linalg.norm(old_solution)

        # Synchronize GPU operations
        cp.cuda.Stream.null.synchronize()

        return float(relative_error) < tolerance

    def detect_block_quenches_cuda_vectorized(
        self, envelope_block: "cp.ndarray", block_info
    ) -> List[Dict[str, Any]]:
        """
        Detect quenches in a single block using fully vectorized CUDA operations.

        Physical Meaning:
            Detects quench events in 7D phase field block using fully vectorized
            GPU operations for optimal performance in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            Detects quenches using vectorized threshold-based detection:
            - Amplitude threshold: |a| > μ(|a|) + 2σ(|a|)
            - All operations vectorized on GPU for maximum efficiency

        Args:
            envelope_block (cp.ndarray): Envelope block on GPU (7D) with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            block_info: Block information.

        Returns:
            List[Dict[str, Any]]: List of detected quenches with positions and amplitudes.
        """
        # Verify 7D shape for Level C
        if envelope_block.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block for Level C BVP, got {envelope_block.ndim}D. "
                f"Shape: {envelope_block.shape}."
            )

        # Vectorized quench detection based on amplitude threshold on GPU
        # All operations are fully vectorized for optimal performance
        amplitude = cp.abs(envelope_block)

        # Vectorized statistics computation on GPU (mean and std are vectorized)
        threshold = cp.mean(amplitude) + 2.0 * cp.std(amplitude)

        # Vectorized mask creation and quench location finding on GPU
        quench_mask = amplitude > threshold
        quench_indices = cp.where(quench_mask)

        # Batch convert to CPU for processing (more efficient than per-element)
        # This is the only non-GPU operation, done in batch for efficiency
        quench_indices_cpu = [cp.asnumpy(idx) for idx in quench_indices]
        amplitude_cpu = cp.asnumpy(amplitude)

        # Process quenches (CPU-side processing of results)
        quenches = []
        num_quenches = len(quench_indices_cpu[0]) if len(quench_indices_cpu) > 0 else 0

        for i in range(num_quenches):
            quench_location = tuple(idx[i] for idx in quench_indices_cpu)
            global_location = tuple(
                block_info.start_indices[j] + quench_location[j]
                for j in range(len(quench_location))
            )

            quenches.append(
                {
                    "local_position": quench_location,
                    "global_position": global_location,
                    "amplitude": float(amplitude_cpu[quench_location]),
                    "block_id": block_info.block_id,
                }
            )

        return quenches

    def compute_block_impedance_cuda_vectorized(
        self, envelope_block: "cp.ndarray", block_info
    ) -> "cp.ndarray":
        """
        Compute impedance for a single block using fully vectorized CUDA operations.

        Physical Meaning:
            Computes impedance of 7D phase field block using fully vectorized GPU
            operations, considering amplitude and phase gradients for proper
            7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            Impedance Z = |a| exp(iφ) where |a| is amplitude and φ is phase,
            computed with fully vectorized operations for optimal GPU performance.
            All operations preserve 7D structure: spatial (0,1,2), phase (3,4,5),
            temporal (6).

        Args:
            envelope_block (cp.ndarray): Envelope block on GPU (7D) with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            block_info: Block information.

        Returns:
            cp.ndarray: Impedance block on GPU (7D) with same shape.

        Raises:
            ValueError: If envelope_block is not 7D.
        """
        # Verify 7D shape for Level C
        if envelope_block.ndim != 7:
            raise ValueError(
                f"Expected 7D envelope block for Level C BVP, got {envelope_block.ndim}D. "
                f"Shape: {envelope_block.shape}."
            )

        # Vectorized computation of amplitude and phase on GPU
        # All operations are fully vectorized for optimal performance
        amplitude = cp.abs(envelope_block)
        phase = cp.angle(envelope_block)

        # Vectorized impedance computation: Z = |a| exp(iφ)
        # All operations are vectorized on GPU for maximum efficiency
        impedance = amplitude * cp.exp(1j * phase)

        # Synchronize GPU operations to ensure computation completes
        cp.cuda.Stream.null.synchronize()

        return impedance

    def extract_source_block_cuda(
        self, source_gpu: "cp.ndarray", block_info
    ) -> "cp.ndarray":
        """
        Extract source block on GPU.

        Physical Meaning:
            Extracts a block from source field on GPU for processing.

        Args:
            source_gpu (cp.ndarray): Source field on GPU.
            block_info: Block information.

        Returns:
            cp.ndarray: Source block on GPU.
        """
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        return source_gpu[slices]

    def extract_envelope_block_cuda(
        self, envelope_gpu: "cp.ndarray", block_info
    ) -> "cp.ndarray":
        """
        Extract envelope block on GPU.

        Physical Meaning:
            Extracts a block from envelope field on GPU for processing.

        Args:
            envelope_gpu (cp.ndarray): Envelope field on GPU.
            block_info: Block information.

        Returns:
            cp.ndarray: Envelope block on GPU.
        """
        start_indices = block_info.start_indices
        end_indices = block_info.end_indices

        slices = tuple(
            slice(start, end) for start, end in zip(start_indices, end_indices)
        )
        return envelope_gpu[slices]

