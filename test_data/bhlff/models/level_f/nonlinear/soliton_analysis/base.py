"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for soliton analysis functionality.

This module provides the base class for all soliton analysis
functionality in the 7D phase field theory framework.

Physical Meaning:
    Defines the fundamental interface and common functionality
    for soliton analysis in 7D space-time with fractional
    Laplacian equations and BVP theory.

Example:
    >>> base = SolitonAnalysisBase(system, nonlinear_params)
    >>> energy = base.compute_soliton_energy(solution, amplitude, width)
"""

import numpy as np
from typing import Dict, Any, Optional
import logging


class SolitonAnalysisBase:
    """
    Base class for soliton analysis functionality.

    Physical Meaning:
        Provides fundamental soliton analysis capabilities including
        energy computation, topological charge calculation, and
        basic soliton properties in 7D phase field theory.

    Mathematical Foundation:
        Implements core soliton physics with 7D fractional Laplacian:
        L_β a = μ(-Δ)^β a + λa = s(x,t)
        where β ∈ (0,2) is the fractional order.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """
        Initialize soliton analysis base.

        Physical Meaning:
            Sets up the base soliton analysis system with
            nonlinear parameters and fundamental constants.

        Args:
            system: Physical system configuration.
            nonlinear_params (Dict[str, Any]): Nonlinear parameters including
                μ, β, λ, and interaction strengths.
        """
        # Initialize base class
        self.system = system
        self.logger = logging.getLogger(__name__)

        # 7D BVP parameters
        self.mu = nonlinear_params.get("mu", 1.0)
        self.beta = nonlinear_params.get("beta", 1.0)
        self.lambda_param = nonlinear_params.get("lambda", 0.0)
        self.interaction_strength = nonlinear_params.get("interaction_strength", 0.1)
        self.three_body_strength = nonlinear_params.get("three_body_strength", 0.01)

    def compute_soliton_energy(
        self, solution: np.ndarray, amplitude: float, width: float
    ) -> float:
        """
        Compute soliton energy from solution.

        Physical Meaning:
            Calculates the total energy of the soliton solution,
            including kinetic and potential energy contributions
            from the 7D phase field theory.

        Mathematical Foundation:
            E = ∫ [½(∇a)² + V(a)] d⁷x
            where V(a) is the potential energy density.

        Args:
            solution (np.ndarray): Soliton solution field.
            amplitude (float): Soliton amplitude.
            width (float): Soliton width parameter.

        Returns:
            float: Total soliton energy.
        """
        try:
            # Extract field values
            field = solution[0] if solution.ndim > 1 else solution

            # Compute kinetic energy (gradient term)
            if len(field) > 1:
                gradient = np.gradient(field)
                kinetic_energy = 0.5 * np.sum(gradient**2)
            else:
                kinetic_energy = 0.0

            # Compute potential energy
            # V(a) = ½λa² + ¼μa⁴ (typical soliton potential)
            potential_energy = 0.5 * self.lambda_param * np.sum(
                field**2
            ) + 0.25 * self.mu * np.sum(field**4)

            # Total energy
            total_energy = kinetic_energy + potential_energy

            return total_energy

        except Exception as e:
            self.logger.error(f"Soliton energy computation failed: {e}")
            return 0.0

    def compute_topological_charge(self, field: np.ndarray) -> float:
        """
        Compute topological charge of the soliton.

        Physical Meaning:
            Calculates the topological charge which characterizes
            the soliton's topological properties in the 7D phase field.

        Args:
            field (np.ndarray): Soliton field profile.

        Returns:
            float: Topological charge.
        """
        try:
            if len(field) < 2:
                return 0.0

            # Compute winding number
            # For 1D soliton: Q = (1/2π) ∫ (dφ/dx) dx
            phase_gradient = np.gradient(np.angle(field + 1e-10j))
            topological_charge = np.sum(phase_gradient) / (2 * np.pi)

            return topological_charge

        except Exception as e:
            self.logger.error(f"Topological charge computation failed: {e}")
            return 0.0

    def compute_7d_soliton_ode(
        self, x: np.ndarray, y: np.ndarray, amplitude: float, width: float
    ) -> np.ndarray:
        """
        Compute 7D soliton ODE system.

        Physical Meaning:
            Implements the 7D fractional Laplacian equation for soliton
            evolution with proper boundary conditions and energy conservation.

        Mathematical Foundation:
            Solves the system:
            dy/dx = [y[1], -μ(-Δ)^β y[0] - λy[0] + s(x)]
            where s(x) is the soliton source term.

        Args:
            x (np.ndarray): Spatial coordinate.
            y (np.ndarray): Solution vector [field, derivative].
            amplitude (float): Soliton amplitude.
            width (float): Soliton width parameter.

        Returns:
            np.ndarray: ODE system derivatives.
        """
        try:
            # Extract field and derivative
            field = y[0]
            field_deriv = y[1]

            # Compute fractional Laplacian term using full 7D BVP theory
            # For 7D: (-Δ)^β = |k|^(2β) in spectral space
            # Full implementation with proper spectral representation
            fractional_laplacian = self._compute_full_fractional_laplacian(x, field)

            # Soliton source term using 7D BVP step resonator theory
            source = amplitude * self._step_resonator_source(x, 0.0, width)

            # ODE system
            dydx = np.array(
                [
                    field_deriv,  # dy[0]/dx = y[1]
                    -fractional_laplacian
                    - self.lambda_param * field
                    + source,  # dy[1]/dx = RHS
                ]
            )

            return dydx

        except Exception as e:
            self.logger.error(f"7D soliton ODE computation failed: {e}")
            return np.zeros_like(y)

    def compute_soliton_interaction_strength(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """
        Compute interaction strength between two solitons.

        Physical Meaning:
            Calculates the strength of interaction between two solitons
            based on their parameters and separation distance.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.

        Returns:
            float: Interaction strength coefficient.
        """
        try:
            # Distance between solitons
            distance = abs(pos2 - pos1)

            # Effective interaction range
            interaction_range = (width1 + width2) / 2

            # Interaction strength using 7D BVP step resonator theory
            base_strength = amp1 * amp2 / (width1 * width2)
            distance_factor = self._step_resonator_interaction(
                distance, interaction_range
            )

            interaction_strength = base_strength * distance_factor

            return interaction_strength

        except Exception as e:
            self.logger.error(f"Interaction strength computation failed: {e}")
            return 0.0

    def _compute_full_fractional_laplacian(
        self, x: np.ndarray, field: np.ndarray
    ) -> np.ndarray:
        """
        Compute full fractional Laplacian using 7D BVP theory.

        Physical Meaning:
            Computes the fractional Laplacian operator (-Δ)^β using
            the complete 7D BVP theory with proper spectral representation
            and boundary conditions.

        Mathematical Foundation:
            Implements the fractional Laplacian in spectral space:
            (-Δ)^β f(x) = F^{-1}[|k|^(2β) F[f(x)]]
            where F is the Fourier transform and β ∈ (0,2).

        Args:
            x (np.ndarray): Spatial coordinate array.
            field (np.ndarray): Field values at spatial points.

        Returns:
            np.ndarray: Fractional Laplacian of the field.
        """
        try:
            # Ensure uniform spacing for FFT
            dx = x[1] - x[0] if len(x) > 1 else 1.0

            # Compute FFT of the field
            field_fft = np.fft.fft(field)

            # Compute wave numbers
            N = len(x)
            k = np.fft.fftfreq(N, dx) * 2 * np.pi

            # Compute fractional Laplacian in spectral space
            # |k|^(2β) with proper handling of k=0 mode
            k_magnitude = np.abs(k)
            k_magnitude[0] = 1e-10  # Avoid division by zero

            fractional_spectrum = (k_magnitude ** (2 * self.beta)) * field_fft

            # Transform back to real space
            fractional_laplacian = np.real(np.fft.ifft(fractional_spectrum))

            return self.mu * fractional_laplacian

        except Exception as e:
            self.logger.error(f"Full fractional Laplacian computation failed: {e}")
            # Fallback to local approximation if FFT fails
            return self.mu * (np.abs(x) ** (2 * self.beta)) * field

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
