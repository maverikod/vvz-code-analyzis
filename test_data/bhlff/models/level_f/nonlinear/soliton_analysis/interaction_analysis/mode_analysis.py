"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton mode analysis functionality.

This module implements soliton mode analysis including
collective modes, stability eigenvalues, and interaction-induced
mode splitting using 7D BVP theory.

Physical Meaning:
    Implements soliton mode analysis including collective modes,
    stability eigenvalues, and interaction-induced mode splitting
    for multi-soliton systems.

Example:
    >>> analyzer = SolitonModeAnalyzer(system, nonlinear_params)
    >>> modes = analyzer.compute_full_mode_analysis(amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3)
"""

import numpy as np
from typing import Dict, Any
import logging

from ..base import SolitonAnalysisBase


class SolitonModeAnalyzer(SolitonAnalysisBase):
    """
    Soliton mode analyzer.

    Physical Meaning:
        Implements soliton mode analysis including collective modes,
        stability eigenvalues, and interaction-induced mode splitting
        for multi-soliton systems.

    Mathematical Foundation:
        Computes the full eigenvalue spectrum of multi-soliton
        systems using 7D fractional Laplacian equations and
        soliton-soliton interaction potentials.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton mode analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def compute_full_mode_analysis(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> Dict[str, Any]:
        """
        Compute full mode analysis for three-soliton system using 7D BVP theory.

        Physical Meaning:
            Performs complete mode analysis of the three-soliton system,
            including collective modes, stability eigenvalues, and
            interaction-induced mode splitting.

        Mathematical Foundation:
            Computes the full eigenvalue spectrum of the three-soliton
            system using 7D fractional Laplacian equations and
            soliton-soliton interaction potentials.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            Dict[str, Any]: Complete mode analysis results.
        """
        try:
            # Setup spatial grid for mode analysis
            x = np.linspace(-20.0, 20.0, 400)
            dx = x[1] - x[0]

            # Compute individual soliton profiles using step functions
            profile1 = amp1 * self._step_resonator_profile(x, pos1, width1)
            profile2 = amp2 * self._step_resonator_profile(x, pos2, width2)
            profile3 = amp3 * self._step_resonator_profile(x, pos3, width3)
            total_profile = profile1 + profile2 + profile3

            # Compute interaction potential matrix
            interaction_matrix = self._compute_interaction_matrix(
                x, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
            )

            # Compute kinetic energy matrix (fractional Laplacian)
            kinetic_matrix = self._compute_kinetic_matrix(x)

            # Total Hamiltonian matrix
            hamiltonian_matrix = kinetic_matrix + interaction_matrix

            # Compute eigenvalues and eigenvectors
            eigenvalues, eigenvectors = np.linalg.eigh(hamiltonian_matrix)

            # Analyze mode properties
            stable_modes = sum(1 for ev in eigenvalues if ev > 0)
            unstable_modes = sum(1 for ev in eigenvalues if ev < 0)
            zero_modes = sum(1 for ev in eigenvalues if abs(ev) < 1e-10)

            # Compute collective mode frequencies
            collective_frequencies = np.sqrt(np.abs(eigenvalues[eigenvalues > 0]))

            # Compute mode participation ratios
            participation_ratios = self._compute_mode_participation_ratios(
                eigenvectors, profile1, profile2, profile3
            )

            # Compute interaction-induced mode splitting
            mode_splitting = self._compute_mode_splitting(
                eigenvalues, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
            )

            return {
                "eigenvalues": eigenvalues,
                "eigenvectors": eigenvectors,
                "stable_modes": stable_modes,
                "unstable_modes": unstable_modes,
                "zero_modes": zero_modes,
                "collective_frequencies": collective_frequencies,
                "participation_ratios": participation_ratios,
                "mode_splitting": mode_splitting,
                "hamiltonian_matrix": hamiltonian_matrix,
                "interaction_matrix": interaction_matrix,
                "kinetic_matrix": kinetic_matrix,
            }

        except Exception as e:
            self.logger.error(f"Full mode analysis computation failed: {e}")
            return {
                "eigenvalues": np.array([]),
                "eigenvectors": np.array([]),
                "stable_modes": 0,
                "unstable_modes": 0,
                "zero_modes": 0,
                "collective_frequencies": np.array([]),
                "participation_ratios": {},
                "mode_splitting": 0.0,
            }

    def _compute_interaction_matrix(
        self,
        x: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> np.ndarray:
        """Compute interaction potential matrix."""
        try:
            N = len(x)
            dx = x[1] - x[0] if len(x) > 1 else 1.0

            # Initialize interaction matrix
            interaction_matrix = np.zeros((N, N))

            # Compute pairwise interactions
            for i in range(N):
                for j in range(N):
                    # Pairwise interaction potential
                    interaction_12 = (
                        self.interaction_strength
                        * amp1
                        * amp2
                        * self._step_resonator_interaction(
                            abs(x[i] - x[j]), width1 + width2
                        )
                    )
                    interaction_13 = (
                        self.interaction_strength
                        * amp1
                        * amp3
                        * self._step_resonator_interaction(
                            abs(x[i] - x[j]), width1 + width3
                        )
                    )
                    interaction_23 = (
                        self.interaction_strength
                        * amp2
                        * amp3
                        * self._step_resonator_interaction(
                            abs(x[i] - x[j]), width2 + width3
                        )
                    )

                    # Three-body interaction
                    three_body = (
                        self.three_body_strength
                        * amp1
                        * amp2
                        * amp3
                        * self._step_resonator_interaction(
                            abs(x[i] - x[j]), width1 + width2 + width3
                        )
                    )

                    interaction_matrix[i, j] = (
                        interaction_12 + interaction_13 + interaction_23 + three_body
                    )

            return interaction_matrix

        except Exception as e:
            self.logger.error(f"Interaction matrix computation failed: {e}")
            return np.zeros((len(x), len(x)))

    def _compute_kinetic_matrix(self, x: np.ndarray) -> np.ndarray:
        """Compute kinetic energy matrix (fractional Laplacian)."""
        try:
            N = len(x)
            dx = x[1] - x[0] if len(x) > 1 else 1.0

            # Initialize kinetic matrix
            kinetic_matrix = np.zeros((N, N))

            # Compute fractional Laplacian matrix
            for i in range(N):
                for j in range(N):
                    if i == j:
                        # Diagonal term
                        kinetic_matrix[i, j] = self.mu * (
                            np.abs(x[i]) ** (2 * self.beta)
                        )
                    else:
                        # Off-diagonal terms (simplified)
                        kinetic_matrix[i, j] = (
                            -self.mu
                            * (np.abs(x[i] - x[j]) ** (2 * self.beta))
                            / (2 * N)
                        )

            return kinetic_matrix

        except Exception as e:
            self.logger.error(f"Kinetic matrix computation failed: {e}")
            return np.zeros((len(x), len(x)))

    def _compute_mode_participation_ratios(
        self,
        eigenvectors: np.ndarray,
        profile1: np.ndarray,
        profile2: np.ndarray,
        profile3: np.ndarray,
    ) -> Dict[str, float]:
        """Compute mode participation ratios."""
        try:
            participation_ratios = {}

            # Compute participation ratios for each mode
            for i in range(min(3, eigenvectors.shape[1])):
                mode = eigenvectors[:, i]

                # Compute overlap with individual soliton profiles
                overlap1 = np.abs(np.dot(mode, profile1))
                overlap2 = np.abs(np.dot(mode, profile2))
                overlap3 = np.abs(np.dot(mode, profile3))

                total_overlap = overlap1 + overlap2 + overlap3

                if total_overlap > 0:
                    participation_ratios[f"mode_{i}"] = {
                        "soliton_1": overlap1 / total_overlap,
                        "soliton_2": overlap2 / total_overlap,
                        "soliton_3": overlap3 / total_overlap,
                    }

            return participation_ratios

        except Exception as e:
            self.logger.error(f"Mode participation ratios computation failed: {e}")
            return {}

    def _compute_mode_splitting(
        self,
        eigenvalues: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> float:
        """Compute interaction-induced mode splitting."""
        try:
            # Compute mode splitting as the difference between
            # the highest and lowest eigenvalues
            if len(eigenvalues) > 1:
                mode_splitting = np.max(eigenvalues) - np.min(eigenvalues)
            else:
                mode_splitting = 0.0

            return mode_splitting

        except Exception as e:
            self.logger.error(f"Mode splitting computation failed: {e}")
            return 0.0

    def _step_resonator_interaction(
        self, distance: float, interaction_range: float
    ) -> float:
        """Step resonator interaction function using 7D BVP theory."""
        try:
            if distance < interaction_range:
                return 1.0
            else:
                return 0.0
        except Exception as e:
            self.logger.error(f"Step resonator interaction computation failed: {e}")
            return 0.0

    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """
        Step resonator profile according to 7D BVP theory.

        Physical Meaning:
            Implements step function profile instead of Gaussian profile
            according to 7D BVP theory principles where soliton boundaries
            are determined by step functions rather than smooth transitions.

        Mathematical Foundation:
            Profile = Θ(width - |x - position|) where Θ is the Heaviside step function
            and width is the soliton width.

        Args:
            x (np.ndarray): Spatial coordinates.
            position (float): Soliton position.
            width (float): Soliton width.

        Returns:
            np.ndarray: Step function profile according to 7D BVP theory.
        """
        # Step function profile according to 7D BVP theory
        distance = np.abs(x - position)
        cutoff_distance = width

        # Apply step function boundary condition
        profile = np.where(distance < cutoff_distance, 1.0, 0.0)

        return profile
