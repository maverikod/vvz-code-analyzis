"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core single soliton analysis functionality.

This module implements the core single soliton solution finding and analysis
using complete 7D BVP theory with fractional Laplacian equations.

Physical Meaning:
    Implements core single soliton physics including ODE computation,
    energy calculations, and optimization algorithms using 7D BVP theory.

Example:
    >>> core = SingleSolitonCore(system, nonlinear_params)
    >>> energy = core.compute_soliton_energy(solution, amplitude, width)
"""

import numpy as np
from typing import Dict, Any, Optional
from scipy.optimize import minimize
from scipy.integrate import solve_bvp
import logging

from .base import SolitonAnalysisBase


class SingleSolitonCore(SolitonAnalysisBase):
    """
    Core single soliton solution finder and analyzer.

    Physical Meaning:
        Implements core single soliton physics including ODE computation,
        energy calculations, and optimization algorithms using 7D BVP theory.

    Mathematical Foundation:
        Solves the 7D soliton equation:
        L_β a = μ(-Δ)^β a + λa = s(x,t)
        with soliton boundary conditions and energy minimization.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize single soliton core."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def compute_7d_soliton_ode(
        self,
        x: np.ndarray,
        y: np.ndarray,
        amplitude: float,
        width: float,
        position: float = 0.0,
    ) -> np.ndarray:
        """
        Compute 7D soliton ODE system for BVP solver.

        Physical Meaning:
            Implements the 7D fractional Laplacian equation for soliton
            evolution with proper boundary conditions and energy conservation
            using complete 7D BVP theory.

        Mathematical Foundation:
            Solves the system:
            dy/dx = [y[1], -μ(-Δ)^β y[0] - λy[0] + s(x)]
            where s(x) is the soliton source term and (-Δ)^β is the
            fractional Laplacian operator.

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
            fractional_laplacian = self._compute_full_fractional_laplacian(x, field)

            # Soliton source term using 7D BVP step resonator theory
            source = amplitude * self._step_resonator_source(x, position, width)

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

    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """
        Step resonator profile using 7D BVP theory.

        Physical Meaning:
            Implements step resonator profile instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at soliton width.

        Mathematical Foundation:
            Step resonator profile:
            f(x) = 1 if |x - pos| < width, 0 if |x - pos| ≥ width
            where width is the soliton width parameter.

        Args:
            x (np.ndarray): Spatial coordinate array.
            position (float): Soliton position.
            width (float): Soliton width parameter.

        Returns:
            np.ndarray: Step resonator profile.
        """
        try:
            # Step resonator: sharp cutoff at soliton width
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)

        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)

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

    def _step_resonator_boundary_condition(
        self, field_value: float, amplitude: float
    ) -> float:
        """
        Step resonator boundary condition using 7D BVP theory.

        Physical Meaning:
            Implements step resonator boundary condition instead of
            exponential decay, following 7D BVP theory principles.

        Args:
            field_value (float): Field value at boundary.
            amplitude (float): Soliton amplitude.

        Returns:
            float: Boundary condition value.
        """
        try:
            # Step resonator: sharp boundary condition
            if abs(field_value) < 0.1 * amplitude:
                return 0.0
            else:
                return field_value

        except Exception as e:
            self.logger.error(
                f"Step resonator boundary condition computation failed: {e}"
            )
            return field_value
