"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Laplacian operations for spectral derivatives.
"""

import numpy as np


class SpectralDerivativesImplLaplacian:
    """
    Laplacian operations for spectral derivatives.

    Physical Meaning:
        Provides methods to compute Laplacian and bi-Laplacian
        of fields in spectral space.
    """

    def __init__(self, domain, precision: str, k_magnitude_squared: np.ndarray):
        """
        Initialize Laplacian computer.

        Args:
            domain: Computational domain.
            precision (str): Numerical precision.
            k_magnitude_squared (np.ndarray): Squared magnitude of wave vectors.
        """
        self.domain = domain
        self.precision = precision
        self._k_magnitude_squared = k_magnitude_squared

    def compute_laplacian(self, field: np.ndarray) -> np.ndarray:
        """
        Compute Laplacian of field in spectral space.

        Physical Meaning:
            Computes the Laplacian Δa of the phase field in 7D space-time,
            representing the second-order spatial variations of the field.

        Mathematical Foundation:
            Laplacian in spectral space: Δa → -|k|² * â(k)
            where |k|² is the squared magnitude of the wave vector.

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            np.ndarray: Laplacian of the field.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for Laplacian computation")

        # Transform to spectral space (fallback allowed)
        try:
            from ...fft.unified_spectral_operations import (
                UnifiedSpectralOperations,
            )

            if hasattr(self, "domain") and hasattr(self.domain, "shape"):
                spectral_ops = UnifiedSpectralOperations(
                    self.domain, precision=self.precision
                )
                field_spectral = spectral_ops.forward_fft(
                    field, normalization="physics"
                )
            else:
                raise Exception("No domain for unified backend")
        except Exception:
            field_spectral = np.fft.fftn(field)

        # Compute Laplacian
        laplacian_spectral = -self._k_magnitude_squared * field_spectral

        # Transform back to real space
        try:
            laplacian = spectral_ops.inverse_fft(laplacian_spectral, normalization="physics")  # type: ignore[name-defined]
        except Exception:
            laplacian = np.fft.ifftn(laplacian_spectral)
        return laplacian.real.astype(self.precision)

    def compute_bi_laplacian(self, field: np.ndarray) -> np.ndarray:
        """
        Compute bi-Laplacian (fourth-order derivative) of field.

        Physical Meaning:
            Computes the bi-Laplacian Δ²a of the phase field, representing
            fourth-order spatial variations of the field.

        Mathematical Foundation:
            Bi-Laplacian in spectral space: Δ²a → |k|⁴ * â(k)

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            np.ndarray: Bi-Laplacian of the field.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for bi-Laplacian computation")

        # Transform to spectral space (fallback allowed)
        try:
            from ...fft.unified_spectral_operations import (
                UnifiedSpectralOperations,
            )

            if hasattr(self, "domain") and hasattr(self.domain, "shape"):
                spectral_ops = UnifiedSpectralOperations(
                    self.domain, precision=self.precision
                )
                field_spectral = spectral_ops.forward_fft(
                    field, normalization="physics"
                )
            else:
                raise Exception("No domain for unified backend")
        except Exception:
            field_spectral = np.fft.fftn(field)

        # Compute bi-Laplacian
        bi_laplacian_spectral = (self._k_magnitude_squared**2) * field_spectral

        # Transform back to real space
        try:
            bi_laplacian = spectral_ops.inverse_fft(bi_laplacian_spectral, normalization="physics")  # type: ignore[name-defined]
        except Exception:
            bi_laplacian = np.fft.ifftn(bi_laplacian_spectral)
        return bi_laplacian.real.astype(self.precision)

    def _validate_field(self, field: np.ndarray) -> bool:
        """Validate field for Laplacian operations."""
        return field is not None and field.size > 0

