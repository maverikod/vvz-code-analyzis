"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Tail interface implementation for BVP framework.

This module implements the interface between BVP and tail resonators,
providing the necessary data transformations for tail resonator calculations.

Theoretical Background:
    The tail interface provides the necessary data for tail resonator
    calculations including admittance Y(ω), resonance peaks {ω_n,Q_n},
    reflection R(ω) and transmission T(ω) coefficients, and spectral data S(ω).

Example:
    >>> tail_interface = TailInterface(bvp_core)
    >>> tail_data = tail_interface.interface_with_tail(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_core.bvp_core_facade_impl import BVPCoreFacade as BVPCore
from ...fft.unified_spectral_operations import UnifiedSpectralOperations


class TailInterface:
    """
    Interface between BVP and tail resonators.

    Physical Meaning:
        Provides the connection between BVP envelope and tail resonators.
        This interface implements the data transformations required for
        integrating BVP with tail resonator calculations.

    Mathematical Foundation:
        Implements interface functions for tail interface:
        1. Admittance Y(ω) for cascade resonator calculations
        2. Resonance peaks {ω_n,Q_n} for resonator chain analysis
        3. Reflection R(ω) and transmission T(ω) coefficients
        4. Spectral data S(ω) inherited from BVP
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize tail interface.

        Physical Meaning:
            Sets up the interface with the BVP core module for
            tail resonator calculations.

        Args:
            bvp_core (BVPCore): BVP core module instance.
        """
        self.bvp_core = bvp_core
        self.domain_7d = bvp_core.domain_7d
        self.config = bvp_core.config

    def interface_with_tail(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Interface BVP with tail resonators.

        Physical Meaning:
            Provides the necessary data for tail resonator calculations:
            - Admittance Y(ω) for cascade resonator calculations
            - Resonance peaks {ω_n,Q_n} for resonator chain analysis
            - Reflection R(ω) and transmission T(ω) coefficients
            - Spectral data S(ω) inherited from BVP

        Mathematical Foundation:
            Computes boundary functions from BVP envelope:
            - Y(ω) = I(ω)/V(ω) - admittance response
            - {ω_n, Q_n} - resonance frequencies and quality factors
            - R(ω), T(ω) - reflection and transmission coefficients
            - S(ω) - spectral data for cascade calculations

        Args:
            envelope (np.ndarray): 7D envelope field at boundaries.

        Returns:
            Dict[str, Any]: Tail interface data including:
                - admittance (np.ndarray): Y(ω) frequency response
                - resonance_peaks (List[Dict]): {ω_n, Q_n} resonance data
                - reflection_coefficient (np.ndarray): R(ω) reflection
                - transmission_coefficient (np.ndarray): T(ω) transmission
                - spectral_data (np.ndarray): S(ω) spectral information
        """
        # Compute impedance data from BVP envelope
        impedance_data = self.bvp_core.compute_impedance(envelope)

        # Extract tail-specific data
        tail_data = {
            "admittance": impedance_data["admittance"],
            "resonance_peaks": impedance_data.get(
                "peaks", {"frequencies": [], "quality_factors": []}
            ),
            "reflection_coefficient": impedance_data["reflection"],
            "transmission_coefficient": impedance_data["transmission"],
            "spectral_data": self._compute_spectral_data(envelope),
        }

        return tail_data

    def _compute_spectral_data(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute spectral data S(ω) from BVP envelope.

        Physical Meaning:
            Computes the spectral data S(ω) that represents the
            frequency content of the BVP envelope for cascade
            resonator calculations.

        Returns:
            np.ndarray: Spectral data S(ω).
        """
        # Use unified backend to compute spectral data along time with physics normalization
        spectral_ops = UnifiedSpectralOperations(self.domain_7d, precision="float64")
        spectral_full = spectral_ops.forward_fft(envelope, normalization="physics")
        # Extract 1D spectral density along time axis by collapsing spatial/phase dims
        spectral_data = np.sum(
            np.abs(spectral_full) ** 2, axis=tuple(range(envelope.ndim - 1))
        )
        return spectral_data
