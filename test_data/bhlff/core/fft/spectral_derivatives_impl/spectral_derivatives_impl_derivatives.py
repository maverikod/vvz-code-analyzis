"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Derivative computation methods for spectral derivatives.
"""

import numpy as np
from typing import Tuple


class SpectralDerivativesImplDerivatives:
    """
    Derivative computation methods for spectral derivatives.

    Physical Meaning:
        Provides methods to compute derivatives along axes and
        mixed derivatives in spectral space.
    """

    def __init__(self, domain, precision: str, wave_vectors: Tuple[np.ndarray, ...]):
        """
        Initialize derivative computer.

        Args:
            domain: Computational domain.
            precision (str): Numerical precision.
            wave_vectors (Tuple[np.ndarray, ...]): Wave vectors for each dimension.
        """
        self.domain = domain
        self.precision = precision
        self._wave_vectors = wave_vectors

    def compute_derivative(
        self, field: np.ndarray, axis: int, order: int = 1
    ) -> np.ndarray:
        """
        Compute nth derivative along a given axis using spectral method.

        Physical Meaning:
            Computes the nth-order derivative of the field along a specified axis
            in spectral space, representing spatial or phase variations.

        Args:
            field (np.ndarray): Field to differentiate.
            axis (int): Axis along which to compute derivative.
            order (int): Order of derivative.

        Returns:
            np.ndarray: Derivative of the field.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for derivative computation")
        if order < 1:
            raise ValueError("Order must be >= 1")
        if axis < 0 or axis >= len(self._wave_vectors):
            raise ValueError("Invalid axis for derivative computation")
        # Forward FFT (fallback allowed). Ensure input shape matches domain
        if hasattr(self.domain, "shape") and field.shape != tuple(self.domain.shape):
            raise ValueError("Field shape does not match domain shape")
        # Forward FFT
        try:
            from ...fft.unified_spectral_operations import (
                UnifiedSpectralOperations,
            )

            spectral_ops = UnifiedSpectralOperations(
                self.domain, precision=self.precision
            )
            field_spectral = spectral_ops.forward_fft(field, normalization="physics")
        except Exception:
            # Ensure broadcasting shapes are handled
            field_spectral = np.fft.fftn(np.array(field, copy=False))
        # Apply (ik_axis)^order multiplier
        k_vec = self._wave_vectors[axis]
        deriv_spectral = (1j * k_vec) ** order * field_spectral
        # Inverse FFT
        try:
            result = spectral_ops.inverse_fft(deriv_spectral, normalization="physics")  # type: ignore[name-defined]
        except Exception:
            result = np.fft.ifftn(deriv_spectral)
        return result.real.astype(self.precision)

    def compute_mixed_derivative(
        self, field: np.ndarray, axes: Tuple[int, int], orders: Tuple[int, int]
    ) -> np.ndarray:
        """
        Compute mixed derivative along two axes.

        Physical Meaning:
            Computes the mixed derivative of the field along two specified axes
            in spectral space, representing combined spatial or phase variations.

        Args:
            field (np.ndarray): Field to differentiate.
            axes (Tuple[int, int]): Axes along which to compute derivative.
            orders (Tuple[int, int]): Orders of derivative for each axis.

        Returns:
            np.ndarray: Mixed derivative of the field.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for mixed derivative computation")
        ax1, ax2 = axes
        ord1, ord2 = orders
        if (
            ax1 < 0
            or ax1 >= len(self._wave_vectors)
            or ax2 < 0
            or ax2 >= len(self._wave_vectors)
        ):
            raise IndexError("axes out of range for wave vectors")
        # Forward FFT
        try:
            from ...fft.unified_spectral_operations import (
                UnifiedSpectralOperations,
            )

            spectral_ops = UnifiedSpectralOperations(
                self.domain, precision=self.precision
            )
            field_spectral = spectral_ops.forward_fft(field, normalization="physics")
        except Exception:
            field_spectral = np.fft.fftn(field)
        # Apply multipliers
        k1 = self._wave_vectors[ax1]
        k2 = self._wave_vectors[ax2]
        deriv_spectral = (1j * k1) ** ord1 * (1j * k2) ** ord2 * field_spectral
        try:
            result = spectral_ops.inverse_fft(deriv_spectral, normalization="physics")  # type: ignore[name-defined]
        except Exception:
            result = np.fft.ifftn(deriv_spectral)
        return result.real.astype(self.precision)

    def _validate_field(self, field: np.ndarray) -> bool:
        """Validate field for derivative computation."""
        return field is not None and field.size > 0

