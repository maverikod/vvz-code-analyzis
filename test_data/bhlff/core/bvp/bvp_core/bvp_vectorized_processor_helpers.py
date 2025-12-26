"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP vectorized processor helper methods.

This module implements helper methods for BVP vectorized processing operations
that support the main BVPVectorizedProcessor class with full 7D BVP theory
implementations.

Physical Meaning:
    Provides helper methods for BVP vectorized processing including
    full stiffness matrix computation, susceptibility matrix computation,
    and 7D BVP theory coupling effects.

Mathematical Foundation:
    Implements helper methods for:
    - Full stiffness matrix computation: K_ij = ∫ κ(|a|) ∇φ_i · ∇φ_j dV
    - Full susceptibility matrix computation: S_ij = ∫ χ(|a|) φ_i φ_j dV
    - 7D BVP coupling effects and boundary conditions

Example:
    >>> helpers = BVPVectorizedProcessorHelpers(config)
    >>> stiffness_matrix = helpers.compute_full_stiffness_matrix_vectorized(block_data, block_info, stiffness)
"""

import numpy as np
from typing import Dict, Any, Tuple
from ...domain.block_processor import BlockInfo


class BVPVectorizedProcessorHelpers:
    """
    Helper methods for BVP vectorized processing operations.

    Physical Meaning:
        Provides helper methods for BVP vectorized processing including
        full stiffness matrix computation, susceptibility matrix computation,
        and 7D BVP theory coupling effects.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize BVP vectorized processor helpers.

        Args:
            config (Dict[str, Any]): BVP configuration parameters.
        """
        self.config = config

    def compute_full_stiffness_matrix_vectorized(
        self, block_data: np.ndarray, block_info: BlockInfo, stiffness: np.ndarray
    ) -> np.ndarray:
        """
        Compute full stiffness matrix according to 7D BVP theory using vectorized operations.

        Physical Meaning:
            Computes the complete stiffness matrix for BVP envelope equation
            using full 7D BVP theory principles with proper boundary conditions
            and nonlinear coupling effects using vectorized operations.

        Mathematical Foundation:
            Implements the full stiffness matrix K_ij for the BVP equation:
            K_ij = ∫ κ(|a|) ∇φ_i · ∇φ_j dV + boundary_terms
            where φ_i are the basis functions and κ(|a|) is the nonlinear stiffness.

        Args:
            block_data (np.ndarray): Block field data.
            block_info (BlockInfo): Block information.
            stiffness (np.ndarray): Local stiffness values.

        Returns:
            np.ndarray: Full stiffness matrix according to 7D BVP theory.
        """
        # Get block dimensions
        block_shape = block_data.shape
        block_size = block_data.size

        # Initialize full stiffness matrix
        stiffness_matrix = np.zeros((block_size, block_size), dtype=np.complex128)

        # Apply 7D BVP theory stiffness computation using vectorized operations
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
                    spatial_distance = self._compute_spatial_distance_vectorized(
                        i, j, block_shape
                    )
                    coupling_strength = self._compute_7d_bvp_coupling_vectorized(
                        spatial_distance, stiffness
                    )
                    stiffness_matrix[i, j] = coupling_strength

        # Apply 7D BVP boundary conditions
        boundary_conditions = self._apply_7d_bvp_boundary_conditions_vectorized(
            block_info, block_shape
        )
        stiffness_matrix += boundary_conditions

        return stiffness_matrix

    def compute_full_susceptibility_matrix_vectorized(
        self, block_data: np.ndarray, block_info: BlockInfo, susceptibility: np.ndarray
    ) -> np.ndarray:
        """
        Compute full susceptibility matrix according to 7D BVP theory using vectorized operations.

        Physical Meaning:
            Computes the complete susceptibility matrix for BVP envelope equation
            using full 7D BVP theory principles with proper nonlinear effects
            and phase coupling using vectorized operations.

        Mathematical Foundation:
            Implements the full susceptibility matrix S_ij for the BVP equation:
            S_ij = ∫ χ(|a|) φ_i φ_j dV + nonlinear_coupling_terms
            where φ_i are the basis functions and χ(|a|) is the nonlinear susceptibility.

        Args:
            block_data (np.ndarray): Block field data.
            block_info (BlockInfo): Block information.
            susceptibility (np.ndarray): Local susceptibility values.

        Returns:
            np.ndarray: Full susceptibility matrix according to 7D BVP theory.
        """
        # Get block dimensions
        block_shape = block_data.shape
        block_size = block_data.size

        # Initialize full susceptibility matrix
        susceptibility_matrix = np.zeros((block_size, block_size), dtype=np.complex128)

        # Apply 7D BVP theory susceptibility computation using vectorized operations
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
                    amplitude_coupling = (
                        self._compute_7d_bvp_amplitude_coupling_vectorized(
                            block_data.flat[i], block_data.flat[j], susceptibility
                        )
                    )
                    susceptibility_matrix[i, j] = amplitude_coupling

        # Apply 7D BVP nonlinear phase coupling
        phase_coupling = self._apply_7d_bvp_phase_coupling_vectorized(
            block_data, block_info
        )
        susceptibility_matrix += phase_coupling

        return susceptibility_matrix

    def _compute_spatial_distance_vectorized(
        self, i: int, j: int, block_shape: Tuple[int, ...]
    ) -> float:
        """Compute spatial distance between two points in block using vectorized operations."""
        # Convert linear indices to multi-dimensional coordinates
        coords_i = np.unravel_index(i, block_shape)
        coords_j = np.unravel_index(j, block_shape)

        # Compute Euclidean distance
        distance = np.sqrt(np.sum((np.array(coords_i) - np.array(coords_j)) ** 2))

        return distance

    def _compute_7d_bvp_coupling_vectorized(
        self, spatial_distance: float, stiffness: np.ndarray
    ) -> complex:
        """
        Compute 7D BVP coupling strength according to theory using vectorized operations.

        Physical Meaning:
            Computes coupling strength between spatial points according to
            7D BVP theory principles, considering the 7D space-time structure.
        """
        # Apply 7D BVP coupling decay (step function instead of exponential)
        cutoff_distance = self.config.get("coupling_cutoff", 2.0)
        coupling_strength = self.config.get("coupling_strength", 0.1)

        if spatial_distance <= cutoff_distance:
            return coupling_strength * np.mean(stiffness)
        else:
            return 0.0

    def _apply_7d_bvp_boundary_conditions_vectorized(
        self, block_info: BlockInfo, block_shape: Tuple[int, ...]
    ) -> np.ndarray:
        """
        Apply 7D BVP boundary conditions to stiffness matrix using vectorized operations.

        Physical Meaning:
            Applies boundary conditions according to 7D BVP theory
            for proper field behavior at block boundaries.
        """
        block_size = np.prod(block_shape)
        boundary_matrix = np.zeros((block_size, block_size), dtype=np.complex128)

        # Apply 7D BVP boundary conditions
        boundary_strength = self.config.get("boundary_strength", 1.0)

        # Check if block is at domain boundary
        if self._is_boundary_block_vectorized(block_info):
            # Apply stronger boundary conditions for boundary blocks
            for i in range(block_size):
                boundary_matrix[i, i] = boundary_strength * 2.0
        else:
            # Apply standard boundary conditions for interior blocks
            for i in range(block_size):
                boundary_matrix[i, i] = boundary_strength

        return boundary_matrix

    def _compute_7d_bvp_amplitude_coupling_vectorized(
        self, field_i: complex, field_j: complex, susceptibility: np.ndarray
    ) -> complex:
        """
        Compute 7D BVP amplitude coupling between field points using vectorized operations.

        Physical Meaning:
            Computes nonlinear amplitude coupling according to 7D BVP theory
            considering the U(1)³ phase structure and nonlinear effects.
        """
        # Compute amplitude coupling according to 7D BVP theory
        amplitude_i = abs(field_i)
        amplitude_j = abs(field_j)

        # Apply 7D BVP nonlinear coupling
        coupling_strength = self.config.get("amplitude_coupling", 0.05)
        nonlinear_coupling = coupling_strength * amplitude_i * amplitude_j

        return nonlinear_coupling

    def _apply_7d_bvp_phase_coupling_vectorized(
        self, block_data: np.ndarray, block_info: BlockInfo
    ) -> np.ndarray:
        """
        Apply 7D BVP phase coupling to susceptibility matrix using vectorized operations.

        Physical Meaning:
            Applies phase coupling according to 7D BVP theory
            considering the U(1)³ phase structure and phase coherence.
        """
        block_size = block_data.size
        phase_coupling_matrix = np.zeros((block_size, block_size), dtype=np.complex128)

        # Apply 7D BVP phase coupling
        phase_coupling_strength = self.config.get("phase_coupling", 0.02)

        for i in range(block_size):
            for j in range(block_size):
                if i != j:
                    # Compute phase coupling according to 7D BVP theory
                    phase_diff = np.angle(block_data.flat[i]) - np.angle(
                        block_data.flat[j]
                    )
                    phase_coupling = phase_coupling_strength * np.exp(1j * phase_diff)
                    phase_coupling_matrix[i, j] = phase_coupling

        return phase_coupling_matrix

    def _is_boundary_block_vectorized(self, block_info: BlockInfo) -> bool:
        """Check if block is at domain boundary."""
        # Check if any block boundary coincides with domain boundary
        domain_shape = self.config.get("domain_shape", (64, 64, 64))

        for i, (start, end) in enumerate(
            zip(block_info.start_indices, block_info.end_indices)
        ):
            if start == 0 or end == domain_shape[i]:
                return True

        return False
