"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP evolution computation for BVP-modulated integrator.

This module provides BVP evolution computation functionality for the
BVP-modulated time integrator in the 7D phase field theory.

Physical Meaning:
    BVP evolution computer handles the computation of BVP-specific evolution
    terms and modulation effects in the temporal evolution of phase field
    configurations.

Mathematical Foundation:
    Implements computation of F_BVP(a, t) operator for the evolution equation:
    ∂a/∂t = F_BVP(a, t) + modulation_terms

Example:
    >>> evolution_computer = BVPEvolutionComputer(domain, config)
    >>> evolution = evolution_computer.compute_bvp_evolution(field)
"""

import numpy as np
from typing import Dict, Any

from ...core.domain import Domain


class BVPEvolutionComputer:
    """
    BVP evolution computer for BVP-modulated integrator.

    Physical Meaning:
        Computes BVP-specific evolution terms and modulation effects
        in the temporal evolution of phase field configurations.

    Mathematical Foundation:
        Implements computation of F_BVP(a, t) operator for the evolution equation:
        ∂a/∂t = F_BVP(a, t) + modulation_terms

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): BVP integrator configuration.
        carrier_frequency (float): High-frequency carrier frequency.
        modulation_strength (float): Strength of BVP modulation.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize BVP evolution computer.

        Physical Meaning:
            Sets up the BVP evolution computer with carrier frequency
            and modulation parameters for evolution computation.

        Args:
            domain (Domain): Computational domain for the computer.
            config (Dict[str, Any]): BVP integrator configuration.
        """
        self.domain = domain
        self.config = config
        self.carrier_frequency = config.get("carrier_frequency", 1.85e43)
        self.modulation_strength = config.get("modulation_strength", 1.0)

    def compute_bvp_evolution(self, field: np.ndarray) -> np.ndarray:
        """
        Compute BVP evolution terms.

        Physical Meaning:
            Computes the BVP-specific evolution terms F_BVP(a, t) for
            the temporal evolution of the phase field configuration.

        Mathematical Foundation:
            Computes F_BVP(a, t) = BVP_terms + modulation_terms
            where BVP_terms represent the core BVP evolution and
            modulation_terms represent high-frequency carrier effects.

        Args:
            field (np.ndarray): Current field configuration a(x, t).

        Returns:
            np.ndarray: BVP evolution terms F_BVP(a, t).
        """
        # Compute core BVP terms
        bvp_terms = self._compute_bvp_terms(field)

        # Compute modulation terms
        modulation_terms = self._compute_modulation_terms(field)

        # Combine terms
        evolution = bvp_terms + modulation_terms

        return evolution

    def _compute_bvp_terms(self, field: np.ndarray) -> np.ndarray:
        """
        Compute core BVP evolution terms.

        Physical Meaning:
            Computes the core BVP evolution terms representing the
            fundamental dynamics of the BVP field configuration.

        Mathematical Foundation:
            Computes the core BVP terms including:
            - Linear evolution terms
            - Nonlinear self-interaction terms
            - Spectral evolution terms

        Args:
            field (np.ndarray): Current field configuration.

        Returns:
            np.ndarray: Core BVP evolution terms.
        """
        # Initialize evolution terms
        evolution = np.zeros_like(field, dtype=complex)

        # Linear evolution terms (spectral)
        if hasattr(self, "_spectral_evolution_matrix"):
            field_spectral = np.fft.fftn(field)
            evolution_spectral = self._spectral_evolution_matrix * field_spectral
            evolution += np.fft.ifftn(evolution_spectral)

        # Nonlinear self-interaction terms
        nonlinear_terms = self._compute_bvp_nonlinear_terms_spectral(field)
        evolution += nonlinear_terms

        return evolution

    def _compute_bvp_nonlinear_terms_spectral(
        self, field_spectral: np.ndarray
    ) -> np.ndarray:
        """
        Compute BVP nonlinear terms in spectral space.

        Physical Meaning:
            Computes nonlinear self-interaction terms of the BVP field
            in spectral space for efficient computation.

        Mathematical Foundation:
            Computes nonlinear terms including:
            - Cubic self-interaction: |a|²a
            - Higher-order nonlinearities
            - Spectral convolution terms

        Args:
            field_spectral (np.ndarray): Field in spectral space.

        Returns:
            np.ndarray: Nonlinear terms in real space.
        """
        # Convert to real space for nonlinear computation
        field_real = np.fft.ifftn(field_spectral)

        # Cubic self-interaction: |a|²a
        amplitude_squared = np.abs(field_real) ** 2
        cubic_term = amplitude_squared * field_real

        # Higher-order nonlinearities (quintic term)
        amplitude_fourth = amplitude_squared**2
        quintic_term = 0.1 * amplitude_fourth * field_real

        # Combine nonlinear terms
        nonlinear_real = cubic_term + quintic_term

        # Convert back to spectral space
        nonlinear_spectral = np.fft.fftn(nonlinear_real)

        # Apply spectral filtering for stability
        k_max = self.domain.N // 2
        kx = np.fft.fftfreq(self.domain.N, self.domain.dx)
        ky = np.fft.fftfreq(self.domain.N, self.domain.dx)
        kz = np.fft.fftfreq(self.domain.N, self.domain.dx)

        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)

        # Apply spectral filter
        spectral_filter = self._step_resonator_spectral_filter(k_magnitude, k_max)
        nonlinear_spectral *= spectral_filter

        # Convert back to real space
        return np.fft.ifftn(nonlinear_spectral)

    def _compute_modulation_terms(self, field: np.ndarray) -> np.ndarray:
        """
        Compute BVP modulation terms.

        Physical Meaning:
            Computes modulation terms representing the effects of the
            high-frequency carrier on the BVP field evolution.

        Mathematical Foundation:
            Computes modulation terms including:
            - Carrier frequency modulation
            - Amplitude modulation effects
            - Phase modulation terms

        Args:
            field (np.ndarray): Current field configuration.

        Returns:
            np.ndarray: Modulation terms.
        """
        # Carrier frequency modulation
        carrier_modulation = 1j * self.carrier_frequency * field

        # Amplitude modulation
        amplitude = np.abs(field)
        amplitude_modulation = self.modulation_strength * amplitude * field

        # Phase modulation
        phase = np.angle(field)
        phase_modulation = 0.1 * self.modulation_strength * np.sin(phase) * field

        # Combine modulation terms
        modulation = carrier_modulation + amplitude_modulation + phase_modulation

        return modulation

    def setup_spectral_evolution_matrix(self) -> None:
        """
        Setup spectral evolution matrix.

        Physical Meaning:
            Pre-computes the spectral evolution matrix for efficient
            linear evolution computation.

        Mathematical Foundation:
            Computes the spectral representation of the linear evolution
            operator for efficient spectral time integration.
        """
        # Compute wave vectors
        kx = np.fft.fftfreq(self.domain.N, self.domain.dx)
        ky = np.fft.fftfreq(self.domain.N, self.domain.dx)
        kz = np.fft.fftfreq(self.domain.N, self.domain.dx)

        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_squared = KX**2 + KY**2 + KZ**2

        # BVP evolution matrix in spectral space
        # This represents the linear part of the BVP evolution
        self._spectral_evolution_matrix = -0.5 * k_squared + 1j * self.carrier_frequency

    def _step_resonator_spectral_filter(
        self, k_magnitude: np.ndarray, k_max: float
    ) -> np.ndarray:
        """
        Step resonator spectral filter according to 7D BVP theory.

        Physical Meaning:
            Implements step function spectral filter instead of exponential decay
            according to 7D BVP theory principles.
        """
        cutoff_frequency = k_max * 0.8  # 80% of maximum frequency
        return np.where(k_magnitude < cutoff_frequency, 1.0, 0.0)
