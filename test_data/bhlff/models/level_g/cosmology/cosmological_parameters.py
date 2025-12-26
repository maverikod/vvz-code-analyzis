"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Cosmological parameters computation for cosmological models in 7D phase field theory.

This module implements cosmological parameters computation for
cosmological evolution, including Hubble parameter computation
and derived cosmological parameters.

Theoretical Background:
    Cosmological parameters in 7D phase field theory include
    Hubble parameter evolution and derived parameters like
    age of the universe and expansion rate.

Mathematical Foundation:
    Implements cosmological parameter calculations:
    - Hubble parameter: H(t) = H0 * sqrt(Ω_Λ) for ΛCDM model
    - Age of universe: based on cosmological time evolution
    - Expansion rate: based on scale factor evolution

Example:
    >>> params = CosmologicalParameters(cosmology_params)
    >>> hubble = params.compute_hubble_parameter(t)
    >>> derived = params.compute_cosmological_parameters(scale_factor, hubble)
"""

import numpy as np
from typing import Dict, Any


class CosmologicalParameters:
    """
    Cosmological parameters computation for cosmological models.

    Physical Meaning:
        Computes cosmological parameters for cosmological evolution,
        including Hubble parameter and derived parameters like
        age of the universe and expansion rate.

    Mathematical Foundation:
        Implements cosmological parameter calculations:
        - Hubble parameter: H(t) = H0 * sqrt(Ω_Λ) for ΛCDM model
        - Age of universe: based on cosmological time evolution
        - Expansion rate: based on scale factor evolution

    Attributes:
        cosmology_params (dict): Cosmological parameters
        H0 (float): Hubble constant
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
        self.omega_lambda = cosmology_params.get("omega_lambda", 0.7)  # Dark energy

        # Physical parameters
        self.c_phi = cosmology_params.get("c_phi", 1e10)  # Phase velocity

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
        self, scale_factor: np.ndarray, hubble_parameter: np.ndarray, time_end: float
    ) -> Dict[str, float]:
        """
        Compute cosmological parameters from evolution.

        Physical Meaning:
            Computes derived cosmological parameters from
            the evolution results.

        Mathematical Foundation:
            Computes derived parameters including expansion rate,
            age of universe, and phase velocity.

        Args:
            scale_factor: Scale factor evolution array
            hubble_parameter: Hubble parameter evolution array
            time_end: End time of evolution

        Returns:
            Dictionary of cosmological parameters
        """
        if len(scale_factor) == 0:
            return {}

        # Compute derived parameters
        parameters = {
            "current_scale_factor": scale_factor[-1],
            "current_hubble_parameter": hubble_parameter[-1],
            "age_universe": time_end,
            "expansion_rate": (
                np.mean(np.diff(scale_factor)) if len(scale_factor) > 1 else 0.0
            ),
            "phase_velocity": self.c_phi,
        }

        return parameters
