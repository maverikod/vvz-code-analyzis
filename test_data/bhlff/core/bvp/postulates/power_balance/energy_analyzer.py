"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Energy analysis for Power Balance Postulate.

This module implements energy analysis methods for the Power Balance
Postulate, including core energy growth calculation and energy density analysis.

Theoretical Background:
    Core energy growth represents the rate of energy change in the core region
    from envelope dynamics. This is a key component of power balance analysis.

Example:
    >>> energy_analyzer = EnergyAnalyzer(domain, constants)
    >>> core_growth = energy_analyzer.compute_core_energy_growth(envelope)
"""

import numpy as np
from typing import Dict, Any

from ....domain.domain import Domain
from ...bvp_constants import BVPConstants


class EnergyAnalyzer:
    """
    Energy analysis for Power Balance Postulate.

    Physical Meaning:
        Analyzes energy growth in the core region from envelope dynamics,
        representing the rate of energy change in the BVP system.

    Mathematical Foundation:
        Core energy growth is estimated from field gradients and amplitude:
        Growth rate = ⟨A, ∇A⟩ representing energy change rate.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize energy analyzer.

        Physical Meaning:
            Sets up the energy analyzer with domain and constants
            for energy growth calculations.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants

    def compute_core_energy_growth(self, envelope: np.ndarray) -> float:
        """
        Compute growth of static core energy.

        Physical Meaning:
            Calculates rate of energy growth in the core region
            from envelope dynamics.

        Mathematical Foundation:
            Core energy growth is estimated from field gradients and amplitude:
            Growth rate = ⟨A, ∇A⟩ representing energy change rate.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: Core energy growth rate.
        """
        amplitude = np.abs(envelope)

        # Core energy is proportional to amplitude squared
        core_energy = np.sum(amplitude**2)

        # Compute actual growth rate from energy evolution
        # For time-dependent analysis, we would use time derivatives
        # Here we estimate from spatial gradients as proxy
        grad_x = np.gradient(amplitude, axis=0)
        grad_y = np.gradient(amplitude, axis=1)
        grad_z = np.gradient(amplitude, axis=2)

        # Growth rate estimated from field gradients and amplitude
        # This represents the rate of energy change in the core
        gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2 + grad_z**2)
        growth_rate = np.mean(amplitude * gradient_magnitude)

        return growth_rate

    def compute_energy_density(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute energy density distribution.

        Physical Meaning:
            Computes the spatial distribution of energy density
            from the envelope field.

        Mathematical Foundation:
            Energy density is proportional to |A|²:
            ρ_E = ½|A|² representing local energy content.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            np.ndarray: Energy density distribution.
        """
        amplitude = np.abs(envelope)
        return 0.5 * amplitude**2

    def compute_total_energy(self, envelope: np.ndarray) -> float:
        """
        Compute total energy of the system.

        Physical Meaning:
            Computes the total energy of the BVP system
            from the envelope field.

        Mathematical Foundation:
            Total energy is the integral of energy density:
            E_total = ∫ ρ_E dV = ½∫ |A|² dV

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            float: Total energy of the system.
        """
        energy_density = self.compute_energy_density(envelope)
        return float(np.sum(energy_density))
