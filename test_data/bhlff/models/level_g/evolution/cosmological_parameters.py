"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological parameters computation for evolution models in 7D phase field theory.

This module implements cosmological parameters computation for
cosmological evolution, including scale factor, Hubble parameter,
and derived cosmological parameters.

Theoretical Background:
    Cosmological parameters in 7D phase field theory include
    scale factor evolution, Hubble parameter, and derived
    parameters like redshift and age of the universe.

Mathematical Foundation:
    Implements cosmological parameter calculations:
    - Scale factor: a(t) = a0 * exp(H0 * t) for ΛCDM model
    - Hubble parameter: H(t) = H0 * sqrt(Ω_Λ) for ΛCDM model
    - Redshift: z = 1/a(t) - 1

Example:
    >>> params = CosmologicalParameters(cosmology_params)
    >>> scale_factor = params.compute_scale_factor(t)
    >>> hubble = params.compute_hubble_parameter(t)
"""

import numpy as np
from typing import Dict, Any


class CosmologicalParameters:
    """
    Cosmological parameters computation for evolution models.

    Physical Meaning:
        Computes cosmological parameters for cosmological evolution,
        including scale factor, Hubble parameter, and derived
        parameters like redshift and age of the universe.

    Mathematical Foundation:
        Implements cosmological parameter calculations:
        - Scale factor: a(t) = a0 * exp(H0 * t) for ΛCDM model
        - Hubble parameter: H(t) = H0 * sqrt(Ω_Λ) for ΛCDM model
        - Redshift: z = 1/a(t) - 1

    Attributes:
        cosmology_params (dict): Cosmological parameters
        H0 (float): Hubble constant
        omega_m (float): Matter density parameter
        omega_lambda (float): Dark energy density parameter
        c_phi (float): Phase velocity
    """

    def __init__(self, cosmology_params: Dict[str, Any]):
        """
        Initialize cosmological parameters computation.

        Physical Meaning:
            Sets up the cosmological parameters computation with
            cosmological parameters and physical constants.

        Args:
            cosmology_params: Cosmological parameters
        """
        self.cosmology_params = cosmology_params

        # Cosmological parameters
        self.H0 = cosmology_params.get("H0", 70.0)  # Hubble constant km/s/Mpc
        self.omega_m = cosmology_params.get("omega_m", 0.3)  # Matter density
        self.omega_lambda = cosmology_params.get("omega_lambda", 0.7)  # Dark energy

        # Physical parameters
        self.c_phi = cosmology_params.get("c_phi", 1e10)  # Phase velocity

    def compute_scale_factor(self, t: float) -> float:
        """
        Compute scale factor at time t.

        Physical Meaning:
            Computes the scale factor a(t) for the expanding
            universe at cosmological time t.

        Mathematical Foundation:
            a(t) = a0 * exp(H0 * t) for ΛCDM model

        Args:
            t: Cosmological time

        Returns:
            Scale factor
        """
        if self.omega_lambda > 0:
            # ΛCDM model with dark energy
            scale_factor = np.exp(self.H0 * t * np.sqrt(self.omega_lambda))
        else:
            # Model without dark energy
            scale_factor = 1 + self.H0 * t

        return scale_factor

    def compute_hubble_parameter(self, t: float) -> float:
        """
        Compute Hubble parameter at time t.

        Physical Meaning:
            Computes the Hubble parameter H(t) for the expanding
            universe at cosmological time t.

        Mathematical Foundation:
            H(t) = H0 * sqrt(Ω_Λ) for ΛCDM model

        Args:
            t: Cosmological time

        Returns:
            Hubble parameter
        """
        if self.omega_lambda > 0:
            # ΛCDM model with dark energy
            hubble_parameter = self.H0 * np.sqrt(self.omega_lambda)
        else:
            # Model without dark energy
            hubble_parameter = self.H0

        return hubble_parameter

    def compute_cosmological_parameters(
        self, t: float, scale_factor: float
    ) -> Dict[str, float]:
        """
        Compute cosmological parameters at time t.

        Physical Meaning:
            Computes derived cosmological parameters from
            the evolution at time t.

        Mathematical Foundation:
            Computes derived parameters including redshift,
            age of universe, and phase velocity.

        Args:
            t: Cosmological time
            scale_factor: Current scale factor

        Returns:
            Dictionary of cosmological parameters
        """
        # Compute derived parameters
        parameters = {
            "time": t,
            "scale_factor": scale_factor,
            "hubble_parameter": self.compute_hubble_parameter(t),
            "age_universe": t,
            "redshift": 1.0 / scale_factor - 1.0,
            "phase_velocity": self.c_phi,
        }

        return parameters
