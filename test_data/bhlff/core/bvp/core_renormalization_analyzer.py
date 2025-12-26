"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core renormalization analysis for BVP framework.

This module implements algorithms for analyzing core renormalization,
including coefficient calculation, energy minimization analysis,
and boundary condition computation.

Physical Meaning:
    Analyzes core renormalization of coefficients c_i^eff(|A|,|∇A|)
    and energy minimization in the core region.

Mathematical Foundation:
    c_i^eff = c_i + α_i|A|² + β_i|∇A|²/ω₀²

Example:
    >>> analyzer = CoreRenormalizationAnalyzer(domain, constants)
    >>> coefficients = analyzer.compute_renormalized_coefficients(envelope, core_region)
"""

import numpy as np
from typing import Dict, Any
from scipy import ndimage

from ..domain.domain import Domain
from .bvp_constants import BVPConstants


class CoreRenormalizationAnalyzer:
    """
    Analyzer for core renormalization and energy minimization.

    Physical Meaning:
        Analyzes core renormalization of coefficients and energy
        minimization in the core region.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize core renormalization analyzer.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants

    def compute_renormalized_coefficients(
        self, envelope: np.ndarray, core_region: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compute renormalized coefficients c_i^eff(|A|,|∇A|).

        Physical Meaning:
            Calculates effective coefficients that depend on envelope
            amplitude and gradient, representing BVP renormalization.

        Mathematical Foundation:
            c_i^eff = c_i + α_i|A|² + β_i|∇A|²/ω₀²

        Args:
            envelope (np.ndarray): BVP envelope.
            core_region (Dict[str, Any]): Core region parameters.

        Returns:
            Dict[str, float]: Renormalized coefficients.
        """
        amplitude = np.abs(envelope)
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)
        gradient_magnitude = np.abs(gradient)

        core_mask = core_region["mask"]
        core_amplitude = amplitude[core_mask]
        core_gradient = gradient_magnitude[core_mask]

        # Renormalized coefficients depend on envelope amplitude and gradient
        # c_i^eff = c_i + α_i|A|² + β_i|∇A|²/ω₀²
        alpha_2 = self.constants.get_envelope_parameter("renormalization_alpha_2")
        alpha_4 = self.constants.get_envelope_parameter("renormalization_alpha_4")
        alpha_6 = self.constants.get_envelope_parameter("renormalization_alpha_6")

        beta_2 = self.constants.get_envelope_parameter("renormalization_beta_2")
        beta_4 = self.constants.get_envelope_parameter("renormalization_beta_4")
        beta_6 = self.constants.get_envelope_parameter("renormalization_beta_6")

        omega_0 = self.constants.get_physical_parameter("carrier_frequency")

        # Compute effective coefficients
        c2_eff = (
            1.0
            + alpha_2 * np.mean(core_amplitude**2)
            + beta_2 * np.mean(core_gradient**2) / omega_0**2
        )
        c4_eff = (
            1.0
            + alpha_4 * np.mean(core_amplitude**4)
            + beta_4 * np.mean(core_gradient**4) / omega_0**4
        )
        c6_eff = (
            1.0
            + alpha_6 * np.mean(core_amplitude**6)
            + beta_6 * np.mean(core_gradient**6) / omega_0**6
        )

        return {
            "c2_eff": c2_eff,
            "c4_eff": c4_eff,
            "c6_eff": c6_eff,
            "renormalization_strength": np.mean([alpha_2, alpha_4, alpha_6]),
        }

    def analyze_core_energy_minimization(
        self, envelope: np.ndarray, core_region: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze core energy minimization.

        Physical Meaning:
            Computes energy components and checks if core is at
            energy minimum.

        Args:
            envelope (np.ndarray): BVP envelope.
            core_region (Dict[str, Any]): Core region parameters.

        Returns:
            Dict[str, Any]: Energy analysis results.
        """
        amplitude = np.abs(envelope)
        core_mask = core_region["mask"]
        core_amplitude = amplitude[core_mask]

        # Compute energy components
        potential_energy = np.sum(core_amplitude**2)
        gradient_energy = np.sum(
            np.gradient(core_amplitude, self.domain.dx, axis=0) ** 2
        )
        total_energy = potential_energy + gradient_energy

        # Check if core is at energy minimum
        energy_gradient = np.gradient(total_energy)
        is_minimum = np.allclose(energy_gradient, 0, atol=1e-6)

        return {
            "potential_energy": potential_energy,
            "gradient_energy": gradient_energy,
            "total_energy": total_energy,
            "energy_minimized": is_minimum,
            "energy_gradient": energy_gradient,
        }

    def compute_boundary_conditions(
        self, envelope: np.ndarray, core_region: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute boundary pressure/stiffness conditions.

        Physical Meaning:
            Calculates boundary pressure and stiffness from amplitude
            gradients and second derivatives at core boundary.

        Args:
            envelope (np.ndarray): BVP envelope.
            core_region (Dict[str, Any]): Core region parameters.

        Returns:
            Dict[str, Any]: Boundary conditions.
        """
        amplitude = np.abs(envelope)
        core_mask = core_region["mask"]

        # Compute boundary pressure
        boundary_pressure = self._compute_boundary_pressure(amplitude, core_mask)

        # Compute boundary stiffness
        boundary_stiffness = self._compute_boundary_stiffness(amplitude, core_mask)

        return {
            "boundary_pressure": boundary_pressure,
            "boundary_stiffness": boundary_stiffness,
            "boundary_conditions_set": True,
        }

    def _compute_boundary_pressure(
        self, amplitude: np.ndarray, core_mask: np.ndarray
    ) -> float:
        """
        Compute boundary pressure from amplitude gradients.

        Physical Meaning:
            Calculates pressure at core boundary from amplitude
            gradient magnitude.

        Args:
            amplitude (np.ndarray): Envelope amplitude.
            core_mask (np.ndarray): Core region mask.

        Returns:
            float: Boundary pressure.
        """
        # Find boundary points
        boundary_mask = self._find_boundary_points(core_mask)

        if np.sum(boundary_mask) == 0:
            return 0.0

        # Compute pressure from gradient magnitude at boundary
        gradient = np.gradient(amplitude)
        gradient_magnitude = np.sqrt(sum(g**2 for g in gradient))
        boundary_pressure = np.mean(gradient_magnitude[boundary_mask])

        return boundary_pressure

    def _compute_boundary_stiffness(
        self, amplitude: np.ndarray, core_mask: np.ndarray
    ) -> float:
        """
        Compute boundary stiffness from second derivatives.

        Physical Meaning:
            Calculates stiffness at core boundary from second
            derivative of amplitude.

        Args:
            amplitude (np.ndarray): Envelope amplitude.
            core_mask (np.ndarray): Core region mask.

        Returns:
            float: Boundary stiffness.
        """
        # Find boundary points
        boundary_mask = self._find_boundary_points(core_mask)

        if np.sum(boundary_mask) == 0:
            return 0.0

        # Compute stiffness from second derivative at boundary
        # np.gradient returns a list of arrays, we need to combine them
        gradient_result = np.gradient(amplitude)
        if isinstance(gradient_result, list):
            # For multi-dimensional arrays, np.gradient returns a list
            # We need to compute the magnitude of the gradient
            second_derivative = np.sqrt(sum(g**2 for g in gradient_result))
        else:
            # For 1D arrays, np.gradient returns a single array
            second_derivative = gradient_result
        # Convert boundary_mask to boolean array for indexing
        boundary_boolean = np.zeros_like(amplitude, dtype=bool)
        if len(boundary_mask) > 0:
            # Handle multi-dimensional indexing properly
            for idx in boundary_mask:
                if len(idx) == len(amplitude.shape):
                    boundary_boolean[tuple(idx)] = True

        # Ensure boundary_boolean has the same shape as second_derivative
        if boundary_boolean.shape != second_derivative.shape:
            # Resize boundary_boolean to match second_derivative shape
            boundary_boolean_resized = np.zeros_like(second_derivative, dtype=bool)
            # Copy values where possible
            min_shape = tuple(
                min(boundary_boolean.shape[i], second_derivative.shape[i])
                for i in range(
                    min(len(boundary_boolean.shape), len(second_derivative.shape))
                )
            )
            if len(min_shape) > 0:
                boundary_boolean_resized[tuple(slice(0, s) for s in min_shape)] = (
                    boundary_boolean[tuple(slice(0, s) for s in min_shape)]
                )
            boundary_boolean = boundary_boolean_resized

        boundary_stiffness = np.mean(np.abs(second_derivative[boundary_boolean]))

        return boundary_stiffness

    def _find_boundary_points(self, core_mask: np.ndarray) -> np.ndarray:
        """
        Find boundary points of core region.

        Physical Meaning:
            Identifies points at the boundary of the core region
            for boundary condition analysis.

        Args:
            core_mask (np.ndarray): Core region mask.

        Returns:
            np.ndarray: Boundary points mask.
        """
        # Use morphological operations to find boundary
        # Dilate core mask to find boundary
        dilated = ndimage.binary_dilation(core_mask)
        boundary_mask = dilated & ~core_mask

        return boundary_mask
