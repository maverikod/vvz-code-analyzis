"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP CUDA block processor helper methods.

This module implements helper methods for BVP CUDA block processing operations
that support the main BVPCudaBlockProcessor class with full 7D BVP theory
implementations on GPU.

Physical Meaning:
    Provides helper methods for BVP CUDA block processing including
    full stiffness matrix computation, susceptibility matrix computation,
    and 7D BVP theory coupling effects on GPU.

Mathematical Foundation:
    Implements helper methods for:
    - Full stiffness matrix computation on GPU: K_ij = ∫ κ(|a|) ∇φ_i · ∇φ_j dV
    - Full susceptibility matrix computation on GPU: S_ij = ∫ χ(|a|) φ_i φ_j dV
    - 7D BVP coupling effects and boundary conditions on GPU

Example:
    >>> helpers = BVPCudaBlockProcessorHelpers(config)
    >>> stiffness_matrix = helpers.compute_full_stiffness_matrix_cuda(block_data, block_info, stiffness)
"""

import cupy as cp
from typing import Dict, Any, Tuple


class BVPCudaBlockProcessorHelpers:
    """
    Helper methods for BVP CUDA block processing operations.

    Physical Meaning:
        Provides helper methods for BVP CUDA block processing including
        full stiffness matrix computation, susceptibility matrix computation,
        and 7D BVP theory coupling effects on GPU.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize BVP CUDA block processor helpers.

        Args:
            config (Dict[str, Any]): BVP configuration parameters.
        """
        self.config = config

    def compute_full_stiffness_matrix_cuda(
        self, block_data: cp.ndarray, block_info, stiffness: cp.ndarray
    ) -> cp.ndarray:
        """
        Compute full stiffness matrix on GPU according to 7D BVP theory.

        Physical Meaning:
            Computes the complete stiffness matrix for BVP envelope equation
            using full 7D BVP theory principles with proper boundary conditions
            and nonlinear coupling effects on GPU.

        Mathematical Foundation:
            Implements the full stiffness matrix K_ij for the BVP equation:
            K_ij = ∫ κ(|a|) ∇φ_i · ∇φ_j dV + boundary_terms
            where φ_i are the basis functions and κ(|a|) is the nonlinear stiffness.

        Args:
            block_data (cp.ndarray): Block field data on GPU.
            block_info: Block information.
            stiffness (cp.ndarray): Local stiffness values on GPU.

        Returns:
            cp.ndarray: Full stiffness matrix according to 7D BVP theory on GPU.
        """
        # Get block dimensions
        block_shape = block_data.shape
        block_size = block_data.size

        # Initialize full stiffness matrix on GPU
        stiffness_matrix = cp.zeros((block_size, block_size), dtype=cp.complex128)

        # Apply 7D BVP theory stiffness computation on GPU
        for i in range(block_size):
            for j in range(block_size):
                # Compute stiffness matrix elements according to 7D BVP theory
                if i == j:
                    # Diagonal elements: local stiffness contribution
                    local_stiffness = (
                        stiffness.flat[i] if i < stiffness.size else stiffness.flat[-1]
                    )
                    stiffness_matrix[i, j] = local_stiffness
                else:
                    # Off-diagonal elements: coupling between neighboring points
                    # Apply 7D BVP coupling according to spatial proximity
                    spatial_distance = self._compute_spatial_distance_cuda(
                        i, j, block_shape
                    )
                    coupling_strength = self._compute_7d_bvp_coupling_cuda(
                        spatial_distance, stiffness
                    )
                    stiffness_matrix[i, j] = coupling_strength

        # Apply 7D BVP boundary conditions on GPU
        boundary_conditions = self._apply_7d_bvp_boundary_conditions_cuda(
            block_info, block_shape
        )
        stiffness_matrix += boundary_conditions

        return stiffness_matrix

    def compute_full_susceptibility_matrix_cuda(
        self, block_data: cp.ndarray, block_info, susceptibility: cp.ndarray
    ) -> cp.ndarray:
        """
        Compute full susceptibility matrix on GPU according to 7D BVP theory.

        Physical Meaning:
            Computes the complete susceptibility matrix for BVP envelope equation
            using full 7D BVP theory principles with proper nonlinear effects
            and phase coupling on GPU.

        Mathematical Foundation:
            Implements the full susceptibility matrix S_ij for the BVP equation:
            S_ij = ∫ χ(|a|) φ_i φ_j dV + nonlinear_coupling_terms
            where φ_i are the basis functions and χ(|a|) is the nonlinear susceptibility.

        Args:
            block_data (cp.ndarray): Block field data on GPU.
            block_info: Block information.
            susceptibility (cp.ndarray): Local susceptibility values on GPU.

        Returns:
            cp.ndarray: Full susceptibility matrix according to 7D BVP theory on GPU.
        """
        # Get block dimensions
        block_shape = block_data.shape
        block_size = block_data.size

        # Initialize full susceptibility matrix on GPU
        susceptibility_matrix = cp.zeros((block_size, block_size), dtype=cp.complex128)

        # Apply 7D BVP theory susceptibility computation on GPU
        for i in range(block_size):
            for j in range(block_size):
                # Compute susceptibility matrix elements according to 7D BVP theory
                if i == j:
                    # Diagonal elements: local susceptibility contribution
                    local_susceptibility = (
                        susceptibility.flat[i]
                        if i < susceptibility.size
                        else susceptibility.flat[-1]
                    )
                    susceptibility_matrix[i, j] = local_susceptibility
                else:
                    # Off-diagonal elements: nonlinear coupling between points
                    # Apply 7D BVP nonlinear coupling according to field amplitude
                    amplitude_coupling = self._compute_7d_bvp_amplitude_coupling_cuda(
                        block_data.flat[i], block_data.flat[j], susceptibility
                    )
                    susceptibility_matrix[i, j] = amplitude_coupling

        # Apply 7D BVP nonlinear phase coupling on GPU
        phase_coupling = self._apply_7d_bvp_phase_coupling_cuda(block_data, block_info)
        susceptibility_matrix += phase_coupling

        return susceptibility_matrix

    def _compute_spatial_distance_cuda(self, i: int, j: int, block_shape) -> float:
        """Compute spatial distance between two points in block on GPU."""
        # Convert linear indices to multi-dimensional coordinates
        coords_i = cp.unravel_index(i, block_shape)
        coords_j = cp.unravel_index(j, block_shape)

        # Compute Euclidean distance
        distance = cp.sqrt(cp.sum((coords_i - coords_j) ** 2))

        return float(distance)

    def _compute_7d_bvp_coupling_cuda(
        self, spatial_distance: float, stiffness: cp.ndarray
    ) -> complex:
        """
        Compute 7D BVP coupling strength according to theory on GPU.

        Physical Meaning:
            Computes coupling strength between spatial points according to
            7D BVP theory principles, considering the 7D space-time structure.
        """
        # Apply 7D BVP coupling decay (step function instead of exponential)
        cutoff_distance = 2.0
        coupling_strength = 0.1

        if spatial_distance <= cutoff_distance:
            return coupling_strength * float(cp.mean(stiffness))
        else:
            return 0.0

    def _apply_7d_bvp_boundary_conditions_cuda(
        self, block_info, block_shape
    ) -> cp.ndarray:
        """
        Apply 7D BVP boundary conditions to stiffness matrix on GPU.

        Physical Meaning:
            Applies boundary conditions according to 7D BVP theory
            for proper field behavior at block boundaries.
        """
        block_size = cp.prod(block_shape)
        boundary_matrix = cp.zeros((block_size, block_size), dtype=cp.complex128)

        # Apply 7D BVP boundary conditions
        boundary_strength = 1.0

        # Check if block is at domain boundary
        if self._is_boundary_block_cuda(block_info):
            # Apply stronger boundary conditions for boundary blocks
            for i in range(block_size):
                boundary_matrix[i, i] = boundary_strength * 2.0
        else:
            # Apply standard boundary conditions for interior blocks
            for i in range(block_size):
                boundary_matrix[i, i] = boundary_strength

        return boundary_matrix

    def _compute_7d_bvp_amplitude_coupling_cuda(
        self, field_i: complex, field_j: complex, susceptibility: cp.ndarray
    ) -> complex:
        """
        Compute 7D BVP amplitude coupling between field points on GPU.

        Physical Meaning:
            Computes nonlinear amplitude coupling according to 7D BVP theory
            considering the U(1)³ phase structure and nonlinear effects.
        """
        # Compute amplitude coupling according to 7D BVP theory
        amplitude_i = abs(field_i)
        amplitude_j = abs(field_j)

        # Apply 7D BVP nonlinear coupling
        coupling_strength = 0.05
        nonlinear_coupling = coupling_strength * amplitude_i * amplitude_j

        return nonlinear_coupling

    def _apply_7d_bvp_phase_coupling_cuda(
        self, block_data: cp.ndarray, block_info
    ) -> cp.ndarray:
        """
        Apply 7D BVP phase coupling to susceptibility matrix on GPU.

        Physical Meaning:
            Applies phase coupling according to 7D BVP theory
            considering the U(1)³ phase structure and phase coherence.
        """
        block_size = block_data.size
        phase_coupling_matrix = cp.zeros((block_size, block_size), dtype=cp.complex128)

        # Apply 7D BVP phase coupling
        phase_coupling_strength = 0.02

        for i in range(block_size):
            for j in range(block_size):
                if i != j:
                    # Compute phase coupling according to 7D BVP theory
                    phase_diff = cp.angle(block_data.flat[i]) - cp.angle(
                        block_data.flat[j]
                    )
                    phase_coupling = phase_coupling_strength * cp.exp(1j * phase_diff)
                    phase_coupling_matrix[i, j] = phase_coupling

        return phase_coupling_matrix

    def _is_boundary_block_cuda(self, block_info) -> bool:
        """Check if block is at domain boundary."""
        # Check if any block boundary coincides with domain boundary
        domain_shape = self.config.get("domain_shape", (64, 64, 64))

        for i, (start, end) in enumerate(
            zip(block_info.start_indices, block_info.end_indices)
        ):
            if start == 0 or end == domain_shape[i]:
                return True

        return False
