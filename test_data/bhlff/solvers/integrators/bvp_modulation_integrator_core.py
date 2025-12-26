"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP-modulated time integrator core implementation.

This module implements the core BVP-modulated time integrator for the 7D phase
field theory, providing temporal evolution with BVP modulation.

Physical Meaning:
    BVP-modulated integrator implements temporal evolution of phase field
    configurations with modulation by the Base High-Frequency Field,
    representing the temporal dynamics of BVP-modulated systems.

Mathematical Foundation:
    Implements time integration for BVP-modulated equations:
    ∂a/∂t = F_BVP(a, t) + modulation_terms
    where F_BVP represents BVP-specific evolution terms.

Example:
    >>> integrator = BVPModulationIntegrator(domain, config)
    >>> field_next = integrator.step(field_current, dt)
"""

import numpy as np
from typing import Dict, Any

from bhlff.core.domain import Domain
from .time_integrator import TimeIntegrator
from .bvp_evolution_computer import BVPEvolutionComputer
from .bvp_integration_schemes import BVPIntegrationSchemes


class BVPModulationIntegrator(TimeIntegrator):
    """
    BVP-modulated time integrator for 7D phase field theory.

    Physical Meaning:
        Implements temporal evolution of phase field configurations with
        modulation by the Base High-Frequency Field, representing the
        temporal dynamics of BVP-modulated systems.

    Mathematical Foundation:
        BVP-modulated integrator solves:
        ∂a/∂t = F_BVP(a, t) + modulation_terms
        where F_BVP represents BVP-specific evolution terms and
        modulation_terms represent high-frequency carrier effects.

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): BVP integrator configuration.
        carrier_frequency (float): High-frequency carrier frequency.
        modulation_strength (float): Strength of BVP modulation.
        _evolution_computer: BVP evolution computer.
        _integration_schemes: BVP integration schemes.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize BVP-modulated integrator.

        Physical Meaning:
            Sets up the BVP-modulated integrator with carrier frequency
            and modulation parameters for temporal evolution.

        Args:
            domain (Domain): Computational domain for the integrator.
            config (Dict[str, Any]): BVP integrator configuration including:
                - carrier_frequency: High-frequency carrier frequency
                - modulation_strength: Strength of BVP modulation
                - integration_scheme: Time integration scheme
        """
        super().__init__(domain, config)
        self._setup_bvp_parameters()

    def _setup_bvp_parameters(self) -> None:
        """
        Setup BVP integrator parameters.

        Physical Meaning:
            Initializes the BVP integrator parameters from configuration
            including carrier frequency and modulation properties.
        """
        self.carrier_frequency = self.config.get("carrier_frequency", 1.85e43)
        self.modulation_strength = self.config.get("modulation_strength", 1.0)
        self.integration_scheme = self.config.get("integration_scheme", "rk4")

        # Initialize component computers
        self._evolution_computer = BVPEvolutionComputer(self.domain, self.config)
        self._integration_schemes = BVPIntegrationSchemes(self.domain, self.config)

        # Setup BVP evolution matrix
        self._evolution_computer.setup_spectral_evolution_matrix()

    def step(self, field: np.ndarray, dt: float) -> np.ndarray:
        """
        Perform one time integration step.

        Physical Meaning:
            Advances the field configuration by one time step using the
            specified integration scheme for BVP-modulated evolution.

        Mathematical Foundation:
            Solves the BVP-modulated evolution equation:
            ∂a/∂t = F_BVP(a, t) + modulation_terms
            using the specified time integration scheme.

        Args:
            field (np.ndarray): Current field configuration a(x, t).
            dt (float): Time step size.

        Returns:
            np.ndarray: Field configuration at next time step a(x, t + dt).

        Raises:
            ValueError: If integration scheme is not supported.
        """
        # Get evolution function
        evolution_func = self._evolution_computer.compute_bvp_evolution

        # Apply integration scheme
        if self.integration_scheme == "rk4":
            field_new = self._integration_schemes.rk4_step(field, dt, evolution_func)
        elif self.integration_scheme == "euler":
            field_new = self._integration_schemes.euler_step(field, dt, evolution_func)
        elif self.integration_scheme == "crank_nicolson":
            field_new = self._integration_schemes.crank_nicolson_step(
                field, dt, evolution_func
            )
        elif self.integration_scheme == "adaptive":
            field_new, dt_new, error = self._integration_schemes.adaptive_step(
                field, dt, evolution_func
            )
            # Store adaptive step information
            self._last_dt = dt_new
            self._last_error = error
        else:
            raise ValueError(
                f"Unsupported integration scheme: {self.integration_scheme}"
            )

        return field_new

    def get_integrator_type(self) -> str:
        """
        Get the integrator type.

        Physical Meaning:
            Returns the type of integrator being used.

        Returns:
            str: Integrator type.
        """
        return "BVP-modulated"

    def get_carrier_frequency(self) -> float:
        """
        Get the carrier frequency.

        Physical Meaning:
            Returns the high-frequency carrier frequency used in
            BVP modulation.

        Returns:
            float: Carrier frequency.
        """
        return self.carrier_frequency

    def get_modulation_strength(self) -> float:
        """
        Get the modulation strength.

        Physical Meaning:
            Returns the strength of BVP modulation.

        Returns:
            float: Modulation strength.
        """
        return self.modulation_strength

    def get_integration_scheme(self) -> str:
        """
        Get the integration scheme.

        Physical Meaning:
            Returns the time integration scheme being used.

        Returns:
            str: Integration scheme name.
        """
        return self.integration_scheme

    def get_scheme_info(self) -> Dict[str, Any]:
        """
        Get information about the current integration scheme.

        Physical Meaning:
            Returns detailed information about the current integration
            scheme including order of accuracy and stability properties.

        Returns:
            Dict[str, Any]: Scheme information.
        """
        return self._integration_schemes.get_scheme_info(self.integration_scheme)

    def __repr__(self) -> str:
        """String representation of the BVP-modulated integrator."""
        return (
            f"BVPModulationIntegrator(domain={self.domain}, "
            f"carrier_frequency={self.carrier_frequency}, "
            f"modulation_strength={self.modulation_strength}, "
            f"scheme={self.integration_scheme})"
        )
