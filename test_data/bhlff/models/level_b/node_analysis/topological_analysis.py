"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological analysis module for node analysis.

This module implements topological analysis operations for node classification,
including Hessian matrix computation, Morse theory, and stability analysis.

Physical Meaning:
    Performs complete topological analysis of saddle nodes in 7D space-time
    using full Hessian analysis and topological invariants according to the 7D theory.

Mathematical Foundation:
    Implements full topological analysis:
    - Hessian matrix computation in 7D
    - Morse theory analysis
    - Topological index computation
    - Stability analysis
"""

import numpy as np
from typing import Dict, Any, Tuple
import logging

from bhlff.core.bvp import BVPCore


class TopologicalAnalysis:
    """
    Topological analysis for node classification.

    Physical Meaning:
        Performs complete topological analysis of saddle nodes
        in 7D space-time using full Hessian analysis and
        topological invariants according to the 7D theory.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize topological analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def is_saddle_node(self, envelope: np.ndarray, node: Tuple[int, ...]) -> bool:
        """
        Full topological analysis of saddle nodes in 7D.

        Physical Meaning:
            Performs complete topological analysis of saddle nodes
            in 7D space-time using full Hessian analysis and
            topological invariants according to the 7D theory.
        """
        if len(node) >= 7:  # Full 7D analysis
            # Compute full 7D Hessian matrix
            hessian_7d = self._compute_7d_hessian(envelope, node)

            # Compute topological index
            topological_index = self._compute_topological_index(hessian_7d)

            # Apply Morse theory
            morse_analysis = self._apply_morse_theory(hessian_7d)

            # Check stability
            stability = self._analyze_stability(hessian_7d)

            return (
                topological_index == 0
                and morse_analysis["type"] == "saddle"  # Saddle condition
                and stability["type"] == "unstable"
            )
        elif len(node) >= 3:  # Fallback for lower dimensions
            # Compute 3D Hessian matrix
            hessian_3d = self._compute_3d_hessian(envelope, node)

            # Compute topological index
            topological_index = self._compute_topological_index(hessian_3d)

            # Apply Morse theory
            morse_analysis = self._apply_morse_theory(hessian_3d)

            return (
                topological_index == 0
                and morse_analysis["type"] == "saddle"  # Saddle condition
            )

        return False

    def _compute_7d_hessian(
        self, envelope: np.ndarray, node: Tuple[int, ...]
    ) -> np.ndarray:
        """Compute full 7D Hessian matrix at node."""
        if len(node) < 7:
            # Fallback to 3D if not enough dimensions
            return self._compute_3d_hessian(envelope, node)

        # Extract 7D neighborhood
        neighborhood = self._extract_7d_neighborhood(envelope, node)

        # Compute second derivatives in all 7 dimensions
        hessian = np.zeros((7, 7))

        for i in range(7):
            for j in range(7):
                # Compute second derivative ∂²φ/∂xᵢ∂xⱼ
                hessian[i, j] = self._compute_mixed_derivative(neighborhood, i, j)

        return hessian

    def _compute_3d_hessian(
        self, envelope: np.ndarray, node: Tuple[int, ...]
    ) -> np.ndarray:
        """Compute 3D Hessian matrix at node."""
        if len(node) < 3:
            return np.zeros((3, 3))

        # Extract 3D neighborhood
        neighborhood = self._extract_3d_neighborhood(envelope, node)

        # Compute second derivatives in 3D
        hessian = np.zeros((3, 3))

        for i in range(3):
            for j in range(3):
                # Compute second derivative ∂²φ/∂xᵢ∂xⱼ
                hessian[i, j] = self._compute_mixed_derivative_3d(neighborhood, i, j)

        return hessian

    def _extract_7d_neighborhood(
        self, envelope: np.ndarray, node: Tuple[int, ...]
    ) -> np.ndarray:
        """Extract 7D neighborhood around node."""
        if len(node) < 7:
            return self._extract_3d_neighborhood(envelope, node)

        # Extract 3x3x3x3x3x3x3 neighborhood
        neighborhood = np.zeros((3, 3, 3, 3, 3, 3, 3))

        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for l in range(3):
                        for m in range(3):
                            for n in range(3):
                                for o in range(3):
                                    idx = (
                                        node[0] + i - 1,
                                        node[1] + j - 1,
                                        node[2] + k - 1,
                                        node[3] + l - 1,
                                        node[4] + m - 1,
                                        node[5] + n - 1,
                                        node[6] + o - 1,
                                    )

                                    # Check bounds
                                    if all(
                                        0 <= idx[dim] < envelope.shape[dim]
                                        for dim in range(7)
                                    ):
                                        neighborhood[i, j, k, l, m, n, o] = envelope[
                                            idx
                                        ]

        return neighborhood

    def _extract_3d_neighborhood(
        self, envelope: np.ndarray, node: Tuple[int, ...]
    ) -> np.ndarray:
        """Extract 3D neighborhood around node."""
        if len(node) < 3:
            return np.zeros((3, 3, 3))

        # Extract 3x3x3 neighborhood
        neighborhood = np.zeros((3, 3, 3))

        for i in range(3):
            for j in range(3):
                for k in range(3):
                    idx = (node[0] + i - 1, node[1] + j - 1, node[2] + k - 1)

                    # Check bounds
                    if all(0 <= idx[dim] < envelope.shape[dim] for dim in range(3)):
                        neighborhood[i, j, k] = envelope[idx]

        return neighborhood

    def _compute_mixed_derivative(
        self, neighborhood: np.ndarray, i: int, j: int
    ) -> float:
        """Compute mixed derivative ∂²φ/∂xᵢ∂xⱼ from neighborhood."""
        if neighborhood.ndim == 7:
            # 7D case - full implementation
            if i == j:
                # Second derivative ∂²φ/∂xᵢ² using central difference
                indices = [1, 1, 1, 1, 1, 1, 1]  # Center point
                indices[i] = 2  # Forward point
                forward = neighborhood[tuple(indices)]

                indices[i] = 0  # Backward point
                backward = neighborhood[tuple(indices)]

                indices[i] = 1  # Center point
                center = neighborhood[tuple(indices)]

                return forward - 2 * center + backward
            else:
                # Mixed derivative ∂²φ/∂xᵢ∂xⱼ using central difference
                indices = [1, 1, 1, 1, 1, 1, 1]  # Center point

                # Four corner points for mixed derivative
                indices[i] = 2
                indices[j] = 2
                corner_pp = neighborhood[tuple(indices)]

                indices[i] = 2
                indices[j] = 0
                corner_pm = neighborhood[tuple(indices)]

                indices[i] = 0
                indices[j] = 2
                corner_mp = neighborhood[tuple(indices)]

                indices[i] = 0
                indices[j] = 0
                corner_mm = neighborhood[tuple(indices)]

                return (corner_pp - corner_pm - corner_mp + corner_mm) / 4.0
        else:
            # 3D case
            return self._compute_mixed_derivative_3d(neighborhood, i, j)

    def _compute_mixed_derivative_3d(
        self, neighborhood: np.ndarray, i: int, j: int
    ) -> float:
        """Compute mixed derivative ∂²φ/∂xᵢ∂xⱼ from 3D neighborhood."""
        if i == j:
            # Second derivative ∂²φ/∂xᵢ²
            if i == 0:
                return (
                    neighborhood[2, 1, 1]
                    - 2 * neighborhood[1, 1, 1]
                    + neighborhood[0, 1, 1]
                )
            elif i == 1:
                return (
                    neighborhood[1, 2, 1]
                    - 2 * neighborhood[1, 1, 1]
                    + neighborhood[1, 0, 1]
                )
            else:
                return (
                    neighborhood[1, 1, 2]
                    - 2 * neighborhood[1, 1, 1]
                    + neighborhood[1, 1, 0]
                )
        else:
            # Mixed derivative ∂²φ/∂xᵢ∂xⱼ
            if i == 0 and j == 1:
                return (
                    neighborhood[2, 2, 1]
                    - neighborhood[2, 0, 1]
                    - neighborhood[0, 2, 1]
                    + neighborhood[0, 0, 1]
                ) / 4
            elif i == 0 and j == 2:
                return (
                    neighborhood[2, 1, 2]
                    - neighborhood[2, 1, 0]
                    - neighborhood[0, 1, 2]
                    + neighborhood[0, 1, 0]
                ) / 4
            elif i == 1 and j == 2:
                return (
                    neighborhood[1, 2, 2]
                    - neighborhood[1, 2, 0]
                    - neighborhood[1, 0, 2]
                    + neighborhood[1, 0, 0]
                ) / 4
            else:
                return 0.0

    def _compute_topological_index(self, hessian: np.ndarray) -> int:
        """Compute topological index from Hessian matrix."""
        # Compute eigenvalues
        eigenvalues = np.linalg.eigvals(hessian)

        # Count negative eigenvalues (unstable directions)
        negative_count = np.sum(eigenvalues < 0)

        return negative_count

    def _apply_morse_theory(self, hessian: np.ndarray) -> Dict[str, Any]:
        """Apply Morse theory to analyze critical point."""
        # Compute eigenvalues
        eigenvalues = np.linalg.eigvals(hessian)

        # Count positive and negative eigenvalues
        positive_count = np.sum(eigenvalues > 0)
        negative_count = np.sum(eigenvalues < 0)
        zero_count = np.sum(np.abs(eigenvalues) < 1e-10)

        # Classify based on Morse theory
        if negative_count == 0:
            node_type = "minimum"
        elif positive_count == 0:
            node_type = "maximum"
        elif negative_count == 1:
            node_type = "saddle"
        else:
            node_type = "degenerate"

        return {
            "type": node_type,
            "positive_eigenvalues": positive_count,
            "negative_eigenvalues": negative_count,
            "zero_eigenvalues": zero_count,
            "eigenvalues": eigenvalues.tolist(),
        }

    def _analyze_stability(self, hessian: np.ndarray) -> Dict[str, Any]:
        """Analyze stability of critical point."""
        # Compute eigenvalues
        eigenvalues = np.linalg.eigvals(hessian)

        # Determine stability
        if np.all(eigenvalues > 0):
            stability_type = "stable"
        elif np.all(eigenvalues < 0):
            stability_type = "unstable"
        else:
            stability_type = "saddle"

        # Compute stability measures
        min_eigenvalue = np.min(eigenvalues)
        max_eigenvalue = np.max(eigenvalues)
        condition_number = (
            max_eigenvalue / min_eigenvalue if min_eigenvalue != 0 else np.inf
        )

        return {
            "type": stability_type,
            "min_eigenvalue": float(min_eigenvalue),
            "max_eigenvalue": float(max_eigenvalue),
            "condition_number": float(condition_number),
            "eigenvalues": eigenvalues.tolist(),
        }

    def is_source_node(self, envelope: np.ndarray, node: Tuple[int, ...]) -> bool:
        """
        Check if node is a source node using full topological analysis.

        Physical Meaning:
            Determines if a node is a source node based on complete
            topological analysis including Hessian matrix and stability analysis.
        """
        if len(node) >= 3:
            # Compute Hessian matrix
            if len(node) >= 7:
                hessian = self._compute_7d_hessian(envelope, node)
            else:
                hessian = self._compute_3d_hessian(envelope, node)

            # Apply Morse theory
            morse_analysis = self._apply_morse_theory(hessian)

            # Check stability
            stability = self._analyze_stability(hessian)

            # Source node: all eigenvalues positive (local minimum)
            return (
                morse_analysis["type"] == "minimum"
                and stability["type"] == "stable"
                and morse_analysis["positive_eigenvalues"] == hessian.shape[0]
            )

        return False

    def is_sink_node(self, envelope: np.ndarray, node: Tuple[int, ...]) -> bool:
        """
        Check if node is a sink node using full topological analysis.

        Physical Meaning:
            Determines if a node is a sink node based on complete
            topological analysis including Hessian matrix and stability analysis.
        """
        if len(node) >= 3:
            # Compute Hessian matrix
            if len(node) >= 7:
                hessian = self._compute_7d_hessian(envelope, node)
            else:
                hessian = self._compute_3d_hessian(envelope, node)

            # Apply Morse theory
            morse_analysis = self._apply_morse_theory(hessian)

            # Check stability
            stability = self._analyze_stability(hessian)

            # Sink node: all eigenvalues negative (local maximum)
            return (
                morse_analysis["type"] == "maximum"
                and stability["type"] == "unstable"
                and morse_analysis["negative_eigenvalues"] == hessian.shape[0]
            )

        return False
