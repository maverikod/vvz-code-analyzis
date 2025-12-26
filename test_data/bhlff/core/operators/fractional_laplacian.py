"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Fractional Laplacian implementation.

This module implements the fractional Laplacian operator for the 7D phase
field theory, providing the core fractional derivative operator.

Physical Meaning:
    The fractional Laplacian (-Δ)^β represents the fractional derivative
    operator that governs non-local interactions in phase field configurations.

Mathematical Foundation:
    Implements the fractional Laplacian (-Δ)^β in spectral space:
    (-Δ)^β a = FFT^{-1}(|k|^(2β) * FFT(a))
    where |k| is the magnitude of the wave vector.

Example:
    >>> laplacian = FractionalLaplacian(domain, beta=1.5)
    >>> result = laplacian.apply(field)
"""

# flake8: noqa: E501

import numpy as np
import logging
from typing import Union

# No additional typing imports needed

from ..domain import Domain
from ..fft.unified_spectral_operations import UnifiedSpectralOperations


class FractionalLaplacian:
    """
    Fractional Laplacian operator for 7D phase field theory.

    Physical Meaning:
        Implements the fractional Laplacian (-Δ)^β that represents
        non-local interactions in phase field configurations.

    Mathematical Foundation:
        The fractional Laplacian (-Δ)^β is defined in spectral space as:
        (-Δ)^β a = FFT^{-1}(|k|^(2β) * FFT(a))
        where |k| is the magnitude of the wave vector and β ∈ (0,2).

    Attributes:
        domain (Domain): Computational domain.
        beta (float): Fractional order β ∈ (0,2).
        _spectral_coeffs (np.ndarray): Pre-computed spectral coefficients.
    """

    def __init__(self, domain: Domain, beta, lambda_param: float = 0.0) -> None:
        """
        Initialize fractional Laplacian operator.

        Physical Meaning:
            Sets up the fractional Laplacian with the specified fractional
            order β for non-local phase field interactions.

        Args:
            domain (Domain): Computational domain for the operator.
            beta (Union[float, Parameters]): Fractional order β ∈ (0,2) or parameters object.
            lambda_param (float): Damping parameter.

        Raises:
            ValueError: If beta is not in valid range (0,2).
        """
        # Handle both float and Parameters object
        if hasattr(beta, "beta"):
            # Parameters object
            self.beta = beta.beta
            # Use lambda_param from parameters object only if not explicitly provided
            if lambda_param == 0.0:  # Default value, use from parameters
                self.lambda_param = getattr(beta, "lambda_param", 0.0)
            else:  # Explicitly provided, use it
                self.lambda_param = lambda_param
        else:
            # Direct float value
            self.beta = beta
            self.lambda_param = lambda_param

        # Validate parameters
        if not (0 < self.beta < 2):
            raise ValueError("Fractional order beta must be in (0,2)")

        self.domain = domain
        self.logger = logging.getLogger(__name__)
        
        # Extract use_cuda from parameters if available
        use_cuda_flag = True  # Default to CUDA
        if hasattr(beta, "use_cuda"):
            use_cuda_flag = beta.use_cuda
        elif isinstance(beta, dict) and "use_cuda" in beta:
            use_cuda_flag = beta["use_cuda"]
        
        # Unified spectral backend (CPU/CUDA with consistent normalization)
        # CRITICAL: Pass use_cuda flag to ensure CUDA is used when available
        self._spectral_ops = UnifiedSpectralOperations(
            domain, 
            precision="float64",
            use_cuda=use_cuda_flag
        )
        self._spectral_coeffs: np.ndarray
        self._setup_spectral_coefficients()

    def _setup_spectral_coefficients(self) -> None:
        """
        Setup spectral coefficients for fractional Laplacian.

        Physical Meaning:
            Pre-computes the spectral representation |k|^(2β) of the
            fractional Laplacian for efficient application.

        Mathematical Foundation:
            Computes |k|^(2β) where |k| is the magnitude of the wave vector.
        """
        # Compute 7D wave vector magnitude using domain grids
        k_magnitude = self._compute_k_magnitude()

        # Compute spectral coefficients strictly for (-Δ)^β: D(k)=|k|^(2β), D(0)=0
        k_zero_mask = k_magnitude == 0
        coeffs = np.zeros_like(k_magnitude)
        nonzero = ~k_zero_mask
        if np.any(nonzero):
            coeffs[nonzero] = k_magnitude[nonzero] ** (2 * self.beta)
        # Zero mode remains zero for pure fractional Laplacian
        self._spectral_coeffs = coeffs

    def apply(self, field: np.ndarray) -> np.ndarray:
        """
        Apply fractional Laplacian to field.

        Physical Meaning:
            Applies the fractional Laplacian (-Δ)^β to the field,
            computing the non-local fractional derivative.

        Mathematical Foundation:
            Computes (-Δ)^β a using spectral methods:
            (-Δ)^β a = FFT^{-1}(|k|^(2β) * FFT(a))

        Args:
            field (np.ndarray): Input field a(x).

        Returns:
            np.ndarray: Result of fractional Laplacian application (-Δ)^β a(x).

        Raises:
            ValueError: If field shape is incompatible with domain.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with "
                f"domain shape {self.domain.shape}"
            )

        # Use UnifiedSpectralOperations for consistent normalization ("ortho")
        # This ensures proper FFT normalization matching solver expectations
        field_spectral = self._spectral_ops.forward_fft(field, normalization="ortho")
        result_spectral = self._spectral_coeffs * field_spectral
        result = self._spectral_ops.inverse_fft(result_spectral, normalization="ortho")
        
        # For real input fields, return real part (within numerical precision)
        # For complex input fields, preserve complex result
        if np.isrealobj(field):
            return result.real
        return result

    def get_spectral_coefficients(self) -> np.ndarray:
        """
        Get spectral coefficients of the fractional Laplacian.

        Physical Meaning:
            Returns the pre-computed spectral coefficients |k|^(2β) for
            the fractional Laplacian.

        Returns:
            np.ndarray: Spectral coefficients |k|^(2β).
        """
        coeffs = self._spectral_coeffs.copy()
        # For inversion use-cases, allow λ to regularize the zero mode if provided
        if getattr(self, "lambda_param", 0.0) > 0:
            zero_mask = coeffs == 0
            if np.any(zero_mask):
                coeffs[zero_mask] = self.lambda_param
        return coeffs

    def get_fractional_order(self) -> float:
        """
        Get the fractional order of the Laplacian.

        Physical Meaning:
            Returns the fractional order β that determines the degree
            of non-locality in the operator.

        Returns:
            float: Fractional order β.
        """
        return self.beta

    def _compute_k_magnitude(self) -> np.ndarray:
        """Compute 7D wave vector magnitude |k| for the domain grids."""
        # Support both legacy Domain and Domain7DBVP APIs
        if hasattr(self.domain, "N_spatial"):
            # New 7D BVP domain
            dx = self.domain.L_spatial / self.domain.N_spatial
            kx = 2 * np.pi * np.fft.fftfreq(self.domain.N_spatial, d=dx)
            ky = 2 * np.pi * np.fft.fftfreq(self.domain.N_spatial, d=dx)
            kz = 2 * np.pi * np.fft.fftfreq(self.domain.N_spatial, d=dx)

            dphi = 2 * np.pi / self.domain.N_phase
            kphi1 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phase, d=dphi)
            kphi2 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phase, d=dphi)
            kphi3 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phase, d=dphi)

            dt = self.domain.T / self.domain.N_t
            kt = 2 * np.pi * np.fft.fftfreq(self.domain.N_t, d=dt)
        else:
            # Legacy domain
            kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
            ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
            kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
            kphi1 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
            kphi2 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
            kphi3 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
            kt = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)

        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
        )
        k_magnitude = np.sqrt(
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )
        return k_magnitude

    def __repr__(self) -> str:
        """String representation of the fractional Laplacian."""
        return f"FractionalLaplacian(domain={self.domain}, beta={self.beta})"
