"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP envelope modulation integration methods.

This module implements envelope modulation integration methods for BVP
envelope integrator, separated for better code organization and to
maintain file size limits.
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bvp_envelope_integrator import BVPEnvelopeIntegrator


class BVPEnvelopeModulationMixin:
    """
    Mixin class for BVP envelope modulation integration methods.

    Physical Meaning:
        Provides envelope modulation integration methods for BVP envelope
        integrator, implementing the BVP approach where all observed "modes"
        are envelope modulations and beatings of the Base High-Frequency Field.

    Mathematical Foundation:
        For envelope modulation, applies:
        â(k,t) = â₀(k) * envelope_modulation(t) * carrier_modulation(t)
    """

    def integrate_envelope_modulation(
        self: "BVPEnvelopeIntegrator",
        initial_field: np.ndarray,
        carrier_frequency: float,
        modulation_depth: float,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate with envelope modulation using BVP approach.

        Physical Meaning:
            Solves the envelope equation with envelope modulation
            representing the BVP approach where all observed "modes"
            are envelope modulations and beatings.

        Mathematical Foundation:
            For envelope modulation, applies:
            â(k,t) = â₀(k) * envelope_modulation(t) * carrier_modulation(t)

        Args:
            initial_field (np.ndarray): Initial field configuration.
            carrier_frequency (float): Carrier frequency ω₀.
            modulation_depth (float): Modulation depth m.
            time_steps (np.ndarray): Time points for integration.

        Returns:
            np.ndarray: Field evolution over time.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        # Transform to spectral space
        initial_spectral = self._spectral_ops.forward_fft(initial_field, "ortho")

        # Initialize result
        result = np.zeros((len(time_steps),) + self.domain.shape, dtype=np.complex128)

        # Apply envelope modulation for each time step
        for i, t in enumerate(time_steps):
            # Envelope modulation factor
            envelope_modulation = 1.0 + modulation_depth * np.cos(carrier_frequency * t)

            # Carrier modulation
            carrier_modulation = np.exp(1j * carrier_frequency * t)

            # BVP envelope solution
            field_spectral = initial_spectral * envelope_modulation * carrier_modulation

            # Transform back to real space
            result[i] = self._spectral_ops.inverse_fft(field_spectral, "ortho")

        self.logger.info(
            f"BVP envelope modulation integration completed for carrier frequency ω₀={carrier_frequency}"
        )
        return result
