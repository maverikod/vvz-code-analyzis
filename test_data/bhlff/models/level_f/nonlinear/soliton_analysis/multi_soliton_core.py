"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core multi-soliton analysis functionality.

This module implements the core multi-soliton analysis functionality
including ODE computation and energy calculations for multi-soliton
systems using 7D BVP theory.

Physical Meaning:
    Implements core multi-soliton physics including ODE systems,
    energy calculations, and interaction potentials for
    multi-soliton configurations in 7D phase field theory.

Example:
    >>> core = MultiSolitonCore(system, nonlinear_params)
    >>> energy = core.compute_multi_soliton_energy(solution, params)
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .base import SolitonAnalysisBase


class MultiSolitonCore(SolitonAnalysisBase):
    """
    Core multi-soliton analysis functionality.

    Physical Meaning:
        Implements core multi-soliton physics including ODE systems,
        energy calculations, and interaction potentials for
        multi-soliton configurations in 7D phase field theory.

    Mathematical Foundation:
        Implements the multi-soliton system:
        L_β a = μ(-Δ)^β a + λa + V_int(a₁, a₂, ...) = s(x,t)
        where V_int represents soliton-soliton interactions.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton core."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def compute_7d_two_soliton_ode(
        self,
        x: np.ndarray,
        y: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> np.ndarray:
        """
        Compute 7D two-soliton ODE system with interactions.

        Physical Meaning:
            Implements the 7D fractional Laplacian equation for
            two-soliton system with soliton-soliton interactions
            using complete 7D BVP theory.

        Mathematical Foundation:
            Solves the system:
            dy/dx = [y[1], -μ(-Δ)^β y[0] - λy[0] - V_int(y[0], s₁, s₂) + s₁ + s₂]
            where V_int is the interaction potential.

        Args:
            x (np.ndarray): Spatial coordinate.
            y (np.ndarray): Solution vector [field, derivative].
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            np.ndarray: ODE system derivatives.
        """
        try:
            # Extract field and derivative
            field = y[0]
            field_deriv = y[1]

            # Compute fractional Laplacian term
            fractional_laplacian = self.mu * (np.abs(x) ** (2 * self.beta)) * field

            # Two soliton source terms using 7D BVP step resonator theory
            source1 = amp1 * self._step_resonator_source(x, pos1, width1)
            source2 = amp2 * self._step_resonator_source(x, pos2, width2)
            total_source = source1 + source2

            # Soliton-soliton interaction potential
            interaction_potential = (
                self.interaction_strength * field * (source1 * source2)
            )

            # ODE system with interactions
            dydx = np.array(
                [
                    field_deriv,  # dy[0]/dx = y[1]
                    -fractional_laplacian
                    - self.lambda_param * field
                    - interaction_potential
                    + total_source,
                ]
            )

            return dydx

        except Exception as e:
            self.logger.error(f"7D two-soliton ODE computation failed: {e}")
            return np.zeros_like(y)

    def compute_7d_three_soliton_ode(
        self,
        x: np.ndarray,
        y: np.ndarray,
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
        Compute 7D three-soliton ODE system with interactions.

        Physical Meaning:
            Implements the 7D fractional Laplacian equation for
            three-soliton system with all pairwise and three-body
            interactions using complete 7D BVP theory.

        Mathematical Foundation:
            Solves the system:
            dy/dx = [y[1], -μ(-Δ)^β y[0] - λy[0] - V_int(y[0], s₁, s₂, s₃) + s₁ + s₂ + s₃]
            where V_int includes all pairwise and three-body interactions.

        Args:
            x (np.ndarray): Spatial coordinate.
            y (np.ndarray): Solution vector [field, derivative].
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            np.ndarray: ODE system derivatives.
        """
        try:
            # Extract field and derivative
            field = y[0]
            field_deriv = y[1]

            # Compute fractional Laplacian term
            fractional_laplacian = self.mu * (np.abs(x) ** (2 * self.beta)) * field

            # Three soliton source terms using 7D BVP step resonator theory
            source1 = amp1 * self._step_resonator_source(x, pos1, width1)
            source2 = amp2 * self._step_resonator_source(x, pos2, width2)
            source3 = amp3 * self._step_resonator_source(x, pos3, width3)
            total_source = source1 + source2 + source3

            # Multi-soliton interaction potential
            pairwise_12 = self.interaction_strength * field * (source1 * source2)
            pairwise_13 = self.interaction_strength * field * (source1 * source3)
            pairwise_23 = self.interaction_strength * field * (source2 * source3)
            three_body = (
                self.three_body_strength * field * (source1 * source2 * source3)
            )

            total_interaction = pairwise_12 + pairwise_13 + pairwise_23 + three_body

            # ODE system with all interactions
            dydx = np.array(
                [
                    field_deriv,  # dy[0]/dx = y[1]
                    -fractional_laplacian
                    - self.lambda_param * field
                    - total_interaction
                    + total_source,
                ]
            )

            return dydx

        except Exception as e:
            self.logger.error(f"7D three-soliton ODE computation failed: {e}")
            return np.zeros_like(y)

    def compute_two_soliton_energy(
        self,
        solution: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """
        Compute total energy of two-soliton system including interactions.

        Physical Meaning:
            Calculates the total energy of two-soliton system including
            individual soliton energies and interaction energy using
            7D BVP step resonator theory.

        Mathematical Foundation:
            E_total = E₁ + E₂ + E_int
            where E_int uses step resonator interaction instead of
            exponential decay.

        Args:
            solution (np.ndarray): Solution field.
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            float: Total energy including interactions.
        """
        try:
            # Individual soliton energies
            energy1 = self.compute_soliton_energy(solution, amp1, width1)
            energy2 = self.compute_soliton_energy(solution, amp2, width2)

            # Interaction energy using 7D BVP step resonator theory
            distance = abs(pos2 - pos1)
            interaction_energy = (
                self.interaction_strength
                * amp1
                * amp2
                * self._step_resonator_interaction(distance, width1 + width2)
            )

            # Total energy
            total_energy = energy1 + energy2 + interaction_energy

            return total_energy

        except Exception as e:
            self.logger.error(f"Two-soliton energy computation failed: {e}")
            return 0.0

    def compute_three_soliton_energy(
        self,
        solution: np.ndarray,
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
        Compute total energy of three-soliton system including all interactions.

        Physical Meaning:
            Calculates the total energy of three-soliton system including
            individual soliton energies, pairwise interactions, and
            three-body interactions using 7D BVP step resonator theory.

        Mathematical Foundation:
            E_total = E₁ + E₂ + E₃ + E₁₂ + E₁₃ + E₂₃ + E₁₂₃
            where all interactions use step resonator theory.

        Args:
            solution (np.ndarray): Solution field.
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.

        Returns:
            float: Total energy including all interactions.
        """
        try:
            # Individual soliton energies
            energy1 = self.compute_soliton_energy(solution, amp1, width1)
            energy2 = self.compute_soliton_energy(solution, amp2, width2)
            energy3 = self.compute_soliton_energy(solution, amp3, width3)

            # Pairwise interaction energies
            distance_12 = abs(pos2 - pos1)
            distance_13 = abs(pos3 - pos1)
            distance_23 = abs(pos3 - pos2)

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

            # Three-body interaction energy using 7D BVP step resonator theory
            total_distance = distance_12 + distance_13 + distance_23
            three_body_energy = (
                self.three_body_strength
                * amp1
                * amp2
                * amp3
                * self._step_resonator_interaction(
                    total_distance, width1 + width2 + width3
                )
            )

            # Total energy
            total_energy = (
                energy1
                + energy2
                + energy3
                + interaction_12
                + interaction_13
                + interaction_23
                + three_body_energy
            )

            return total_energy

        except Exception as e:
            self.logger.error(f"Three-soliton energy computation failed: {e}")
            return 0.0

    def _step_resonator_interaction(
        self, distance: float, interaction_range: float
    ) -> float:
        """
        Step resonator interaction function using 7D BVP theory.

        Physical Meaning:
            Implements step resonator interaction instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at interaction range.

        Mathematical Foundation:
            Step function interaction:
            f(d) = 1 if d < R, 0 if d ≥ R
            where R is the interaction range.

        Args:
            distance (float): Distance between solitons.
            interaction_range (float): Interaction range.

        Returns:
            float: Step resonator interaction factor.
        """
        try:
            # Step resonator: sharp cutoff at interaction range
            if distance < interaction_range:
                return 1.0
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Step resonator interaction computation failed: {e}")
            return 0.0

    def _step_resonator_source(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """
        Step resonator source term using 7D BVP theory.

        Physical Meaning:
            Implements step resonator source term instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at source width.

        Mathematical Foundation:
            Step resonator source:
            s(x) = 1 if |x - pos| < width, 0 if |x - pos| ≥ width
            where width is the source width parameter.

        Args:
            x (np.ndarray): Spatial coordinate array.
            position (float): Source position.
            width (float): Source width parameter.

        Returns:
            np.ndarray: Step resonator source term.
        """
        try:
            # Step resonator: sharp cutoff at source width
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)

        except Exception as e:
            self.logger.error(f"Step resonator source computation failed: {e}")
            return np.zeros_like(x)
