"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base initialization for spectral derivatives implementation.
"""

from typing import Any

from ..spectral_derivatives_base import SpectralDerivativesBase


class SpectralDerivativesImplBase(SpectralDerivativesBase):
    """
    Base class for spectral derivatives implementation initialization.

    Physical Meaning:
        Provides base initialization for spectral derivative operations
        with the computational domain and numerical precision.
    """

    def __init__(self, domain: Any, precision: str = "float64"):
        """
        Initialize spectral derivatives.

        Physical Meaning:
            Sets up the spectral derivative operations with the computational
            domain and numerical precision, pre-computing wave vectors
            for efficient derivative calculations.

        Args:
            domain (Domain): Computational domain for derivative operations.
            precision (str): Numerical precision for computations.
        """
        # Accept either Domain or an FFT backend carrying a domain
        backend = domain
        actual_domain = getattr(domain, "domain", domain)
        super().__init__(actual_domain, precision)
        # Preserve legacy API expected by tests
        self.fft_backend = backend

        self._wave_vectors = None
        self._k_magnitude_squared = None
        # If domain has shape, precompute; otherwise defer until first call
        if hasattr(actual_domain, "shape"):
            from .spectral_derivatives_impl_wave_vectors import SpectralDerivativesImplWaveVectors

            wave_vectors_computer = SpectralDerivativesImplWaveVectors(actual_domain)
            self._wave_vectors = wave_vectors_computer.compute_wave_vectors()
            self._k_magnitude_squared = wave_vectors_computer.compute_k_magnitude_squared(
                self._wave_vectors
            )
            self.logger.info(
                f"SpectralDerivatives initialized for domain {actual_domain.shape}"
            )
        else:
            self.logger.info(
                "SpectralDerivatives initialized without domain.shape (deferred setup)"
            )

