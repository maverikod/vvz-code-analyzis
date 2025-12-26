"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Fractional Riesz operator implementation.

This module implements the fractional Riesz operator for the 7D phase field
theory, providing the core mathematical operator for phase field equations.

Physical Meaning:
    The fractional Riesz operator L_β = μ(-Δ)^β + λ represents the fundamental
    mathematical operator governing phase field evolution in 7D space-time.

Mathematical Foundation:
    Implements the fractional Riesz operator:
    L_β a = μ(-Δ)^β a + λa = s(x)
    where β ∈ (0,2) is the fractional order, μ > 0 is the diffusion coefficient,
    and λ ≥ 0 is the damping parameter.

Example:
    >>> operator = OperatorRiesz(domain, parameters)
    >>> result = operator.apply(field)
"""

import numpy as np

# No additional typing imports needed

from ..domain import Domain
from ..domain import Parameters


class OperatorRiesz:
    """
    Fractional Riesz operator for 7D phase field theory.

    Physical Meaning:
        Implements the fractional Riesz operator L_β = μ(-Δ)^β + λ that
        governs the evolution of phase field configurations in 7D space-time.

    Mathematical Foundation:
        The operator L_β a = μ(-Δ)^β a + λa represents the fundamental
        mathematical structure for phase field equations, where:
        - (-Δ)^β is the fractional Laplacian of order β
        - μ is the diffusion coefficient
        - λ is the damping parameter

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _spectral_coeffs (np.ndarray): Pre-computed spectral coefficients.
    """

    def __init__(self, domain: Domain, parameters: Parameters) -> None:
        """
        Initialize fractional Riesz operator.

        Physical Meaning:
            Sets up the operator with computational domain and physics
            parameters, pre-computing spectral coefficients for efficient
            application of the fractional operator.

        Args:
            domain (Domain): Computational domain for the operator.
            parameters (Parameters): Physics parameters including μ, β, λ.
        """
        self.domain = domain
        self.parameters = parameters
        self._spectral_coeffs: np.ndarray
        self._setup_spectral_coefficients()

    def _setup_spectral_coefficients(self) -> None:
        """
        Setup spectral coefficients for fractional operator.

        Physical Meaning:
            Pre-computes the spectral representation of the fractional
            Riesz operator for efficient application in frequency space.

        Mathematical Foundation:
            Computes D(k) = μ|k|^(2β) + λ where |k| is the magnitude
            of the wave vector.
        """
        # Get 7D wave vectors for BVP theory
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kphi1 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi2 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi3 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kt = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)

        # Create 7D meshgrids
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
        )

        # Compute 7D wave vector magnitude
        k_magnitude = np.sqrt(
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )

        # Compute spectral coefficients
        self._spectral_coeffs = self.parameters.get_spectral_coefficients(k_magnitude)

    def apply(self, field: np.ndarray) -> np.ndarray:
        """
        Apply fractional Riesz operator to field.

        Physical Meaning:
            Applies the fractional Riesz operator L_β to the field,
            computing the result of the operator action on the phase
            field configuration.

        Mathematical Foundation:
            Computes L_β a = μ(-Δ)^β a + λa using spectral methods:
            L_β a = FFT^{-1}(D(k) * FFT(a))

        Args:
            field (np.ndarray): Input field a(x).

        Returns:
            np.ndarray: Result of operator application L_β a(x).

        Raises:
            ValueError: If field shape is incompatible with domain.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with "
                f"domain shape {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)

        # Apply spectral operator
        result_spectral = self._spectral_coeffs * field_spectral

        # Transform back to real space
        result = np.fft.ifftn(result_spectral)

        return result.real

    def get_spectral_coefficients(self) -> np.ndarray:
        """
        Get spectral coefficients of the operator.

        Physical Meaning:
            Returns the pre-computed spectral coefficients D(k) for
            the fractional Riesz operator.

        Returns:
            np.ndarray: Spectral coefficients D(k).
        """
        return self._spectral_coeffs.copy()

    def __repr__(self) -> str:
        """String representation of the operator."""
        return (
            f"OperatorRiesz(domain={self.domain}, "
            f"mu={self.parameters.mu}, beta={self.parameters.beta}, "
            f"lambda={self.parameters.lambda_param})"
        )
