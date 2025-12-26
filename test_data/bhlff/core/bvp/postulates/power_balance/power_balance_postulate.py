"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power Balance Postulate implementation for BVP framework.

This module implements Postulate 9 of the BVP framework, which states that
BVP flux at external boundary equals the sum of growth of static core energy,
EM/weak radiation/losses, and reflection, controlled by integral identity.

Theoretical Background:
    Power balance is maintained at the external boundary through proper
    accounting of energy flows. The integral identity ensures conservation
    of energy in the BVP system.

Example:
    >>> postulate = PowerBalancePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any

from ....domain.domain import Domain
from ...bvp_constants import BVPConstants
from ...bvp_postulate_base import BVPPostulate
from .flux_computer import FluxComputer
from .energy_analyzer import EnergyAnalyzer
from .radiation_calculator import RadiationCalculator


class PowerBalancePostulate(BVPPostulate):
    """
    Postulate 9: Power Balance.

    Physical Meaning:
        BVP flux at external boundary = (growth of static core energy) +
        (EM/weak radiation/losses) + (reflection). This is controlled
        by integral identity.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize power balance postulate.

        Physical Meaning:
            Sets up the postulate for analyzing power balance
            at external boundaries.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.power_balance_tolerance = (
            constants.get_quench_parameter("power_balance_tolerance")
            if hasattr(constants, "get_quench_parameter")
            else 0.05
        )
        self.flux_threshold = (
            constants.get_quench_parameter("flux_threshold")
            if hasattr(constants, "get_quench_parameter")
            else 0.1
        )

        # Initialize component analyzers
        self.flux_computer = FluxComputer(domain, constants)
        self.energy_analyzer = EnergyAnalyzer(domain, constants)
        self.radiation_calculator = RadiationCalculator(domain, constants)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply power balance postulate.

        Physical Meaning:
            Verifies that power balance is maintained at the external
            boundary with proper accounting of energy flows.

        Mathematical Foundation:
            Checks integral identity: BVP flux = core energy growth +
            radiation/losses + reflection.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including power balance components,
                flux analysis, and balance validation.
        """
        # Compute BVP flux at external boundary
        bvp_flux = self.flux_computer.compute_bvp_flux(envelope)

        # Compute core energy growth
        core_energy_growth = self.energy_analyzer.compute_core_energy_growth(envelope)

        # Compute radiation and losses
        radiation_losses = self.radiation_calculator.compute_radiation_losses(envelope)

        # Compute reflection
        reflection = self.radiation_calculator.compute_reflection(envelope)

        # Analyze power balance
        power_balance = self._analyze_power_balance(
            bvp_flux, core_energy_growth, radiation_losses, reflection
        )

        # Validate power balance
        is_balanced = self._validate_power_balance(power_balance)

        return {
            "bvp_flux": bvp_flux,
            "core_energy_growth": core_energy_growth,
            "radiation_losses": radiation_losses,
            "reflection": reflection,
            "power_balance": power_balance,
            "is_balanced": is_balanced,
            "postulate_satisfied": is_balanced,
        }

    def _analyze_power_balance(
        self,
        bvp_flux: float,
        core_energy_growth: float,
        radiation_losses: float,
        reflection: float,
    ) -> Dict[str, Any]:
        """
        Analyze power balance components.

        Physical Meaning:
            Computes power balance ratio and error to verify
            energy conservation.

        Mathematical Foundation:
            Balance ratio = BVP_flux / (core_growth + radiation + reflection)

        Args:
            bvp_flux (float): BVP flux at boundary.
            core_energy_growth (float): Core energy growth rate.
            radiation_losses (float): Radiation losses.
            reflection (float): Reflected energy.

        Returns:
            Dict[str, Any]: Power balance analysis.
        """
        total_output = core_energy_growth + radiation_losses + reflection
        balance_ratio = bvp_flux / (total_output + 1e-12)
        balance_error = abs(balance_ratio - 1.0)

        return {
            "total_input": bvp_flux,
            "total_output": total_output,
            "balance_ratio": balance_ratio,
            "balance_error": balance_error,
            "components": {
                "core_energy_growth": core_energy_growth,
                "radiation_losses": radiation_losses,
                "reflection": reflection,
            },
        }

    def _validate_power_balance(self, power_balance: Dict[str, Any]) -> bool:
        """
        Validate that power balance is maintained.

        Physical Meaning:
            Checks if power balance error is within acceptable
            tolerance for energy conservation.

        Args:
            power_balance (Dict[str, Any]): Power balance analysis.

        Returns:
            bool: True if power balance is maintained.
        """
        balance_error = power_balance["balance_error"]
        return balance_error < self.power_balance_tolerance
