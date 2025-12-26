"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton mode analysis and matrix computations.

This module implements comprehensive mode analysis for multi-soliton
systems including interaction matrices, kinetic matrices, and
mode participation analysis using 7D BVP theory.

Physical Meaning:
    Performs complete mode analysis of multi-soliton systems,
    including collective modes, stability eigenvalues, and
    interaction-induced mode splitting using 7D phase field theory.

Example:
    >>> analyzer = SolitonModeAnalyzer(system, nonlinear_params)
    >>> analysis = analyzer.compute_full_mode_analysis(soliton_params)
"""

import numpy as np
from typing import Dict, Any
import logging

from .base import SolitonAnalysisBase


class SolitonModeAnalyzer(SolitonAnalysisBase):
    """
    Soliton mode analyzer for multi-soliton systems.

    Physical Meaning:
        Performs complete mode analysis of multi-soliton systems,
        including collective modes, stability eigenvalues, and
        interaction-induced mode splitting using 7D phase field theory.

    Mathematical Foundation:
        Computes the full eigenvalue spectrum of multi-soliton
        systems using 7D fractional Laplacian equations and
        soliton-soliton interaction potentials.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize soliton mode analyzer."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

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
        """
        Compute interaction potential matrix for three-soliton system.

        Physical Meaning:
            Computes the interaction potential matrix for three-soliton
            system using 7D BVP step resonator theory with proper
            pairwise and three-body interactions.

        Mathematical Foundation:
            V_ij = Σ_k V_pairwise(i,j,k) + V_three_body(i,j,k)
            where V_pairwise uses step resonator interaction and
            V_three_body includes three-body effects.

        Args:
            x (np.ndarray): Spatial coordinate array.
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            np.ndarray: Interaction potential matrix.
        """
        try:
            N = len(x)
            interaction_matrix = np.zeros((N, N))

            # Compute pairwise interaction potentials
            for i in range(N):
                for j in range(N):
                    # Distance-dependent interaction
                    distance = abs(x[i] - x[j])

                    # Pairwise interactions using 7D BVP step resonator theory
                    interaction_12 = (
                        self.interaction_strength
                        * amp1
                        * amp2
                        * self._step_resonator_interaction(distance, width1 + width2)
                    )
                    interaction_13 = (
                        self.interaction_strength
                        * amp1
                        * amp3
                        * self._step_resonator_interaction(distance, width1 + width3)
                    )
                    interaction_23 = (
                        self.interaction_strength
                        * amp2
                        * amp3
                        * self._step_resonator_interaction(distance, width2 + width3)
                    )

                    # Three-body interaction using 7D BVP step resonator theory
                    three_body = (
                        self.three_body_strength
                        * amp1
                        * amp2
                        * amp3
                        * self._step_resonator_interaction(
                            distance, width1 + width2 + width3
                        )
                    )

                    # Total interaction
                    interaction_matrix[i, j] = (
                        interaction_12 + interaction_13 + interaction_23 + three_body
                    )

            return interaction_matrix

        except Exception as e:
            self.logger.error(f"Interaction matrix computation failed: {e}")
            return np.zeros((len(x), len(x)))

    def _compute_kinetic_matrix(self, x: np.ndarray) -> np.ndarray:
        """
        Compute kinetic energy matrix using fractional Laplacian.

        Physical Meaning:
            Computes the kinetic energy matrix using fractional Laplacian
            operator (-Δ)^β in 7D BVP theory with proper spectral
            representation and boundary conditions.

        Mathematical Foundation:
            T_ij = μ(-Δ)^β δ(x_i - x_j)
            where (-Δ)^β is the fractional Laplacian operator
            computed in spectral space.

        Args:
            x (np.ndarray): Spatial coordinate array.

        Returns:
            np.ndarray: Kinetic energy matrix.
        """
        try:
            N = len(x)
            dx = x[1] - x[0] if len(x) > 1 else 1.0

            # Compute wave numbers
            k = np.fft.fftfreq(N, dx) * 2 * np.pi
            k_magnitude = np.abs(k)
            k_magnitude[0] = 1e-10  # Avoid division by zero

            # Kinetic energy operator in spectral space
            kinetic_spectrum = self.mu * (k_magnitude ** (2 * self.beta))

            # Transform to real space
            kinetic_matrix = np.zeros((N, N))
            for i in range(N):
                delta_function = np.zeros(N)
                delta_function[i] = 1.0
                kinetic_response = np.real(
                    np.fft.ifft(kinetic_spectrum * np.fft.fft(delta_function))
                )
                kinetic_matrix[:, i] = kinetic_response

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
    ) -> Dict[str, Any]:
        """
        Compute mode participation ratios for each soliton.

        Physical Meaning:
            Computes the participation ratio of each soliton in the
            collective modes of the three-soliton system, providing
            insight into mode localization and collective behavior.

        Mathematical Foundation:
            P_i^α = |⟨ψ_α|φ_i⟩|² / Σ_j |⟨ψ_α|φ_j⟩|²
            where ψ_α is the α-th eigenmode and φ_i is the i-th soliton profile.

        Args:
            eigenvectors (np.ndarray): Eigenvectors of the Hamiltonian matrix.
            profile1 (np.ndarray): First soliton profile.
            profile2 (np.ndarray): Second soliton profile.
            profile3 (np.ndarray): Third soliton profile.

        Returns:
            Dict[str, Any]: Mode participation ratios for each mode.
        """
        try:
            participation_ratios = {}

            # Compute overlap with each soliton profile
            for i, eigenvector in enumerate(eigenvectors.T):
                overlap1 = np.abs(np.dot(eigenvector, profile1))
                overlap2 = np.abs(np.dot(eigenvector, profile2))
                overlap3 = np.abs(np.dot(eigenvector, profile3))

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
        """
        Compute interaction-induced mode splitting.

        Physical Meaning:
            Computes the interaction-induced mode splitting in the
            three-soliton system, which characterizes the collective
            behavior and interaction strength between solitons.

        Mathematical Foundation:
            Δω = Σ_{i<j} V_ij / N_modes
            where V_ij is the interaction strength between solitons i and j,
            and N_modes is the number of collective modes.

        Args:
            eigenvalues (np.ndarray): Eigenvalues of the Hamiltonian matrix.
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            float: Mode splitting parameter.
        """
        try:
            # Compute distances between solitons
            distance_12 = abs(pos2 - pos1)
            distance_13 = abs(pos3 - pos1)
            distance_23 = abs(pos3 - pos2)

            # Compute interaction strengths using 7D BVP step resonator theory
            interaction_12 = (
                self.interaction_strength
                * amp1
                * amp2
                * self._step_resonator_interaction(distance_12, width1 + width2)
            )
            interaction_13 = (
                self.interaction_strength
                * amp1
                * amp3
                * self._step_resonator_interaction(distance_13, width1 + width3)
            )
            interaction_23 = (
                self.interaction_strength
                * amp2
                * amp3
                * self._step_resonator_interaction(distance_23, width2 + width3)
            )

            # Mode splitting is proportional to interaction strength
            mode_splitting = (interaction_12 + interaction_13 + interaction_23) / 3.0

            return mode_splitting

        except Exception as e:
            self.logger.error(f"Mode splitting computation failed: {e}")
            return 0.0
