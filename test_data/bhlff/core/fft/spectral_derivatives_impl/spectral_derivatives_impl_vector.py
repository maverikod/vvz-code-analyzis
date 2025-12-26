"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vector operations for spectral derivatives.
"""

import numpy as np
from typing import Tuple


class SpectralDerivativesImplVector:
    """
    Vector operations for spectral derivatives.

    Physical Meaning:
        Provides methods to compute gradient, divergence, and curl
        of vector fields in spectral space.
    """

    def __init__(self, domain, precision: str, wave_vectors: Tuple[np.ndarray, ...]):
        """
        Initialize vector operations computer.

        Args:
            domain: Computational domain.
            precision (str): Numerical precision.
            wave_vectors (Tuple[np.ndarray, ...]): Wave vectors for each dimension.
        """
        self.domain = domain
        self.precision = precision
        self._wave_vectors = wave_vectors

    def compute_gradient(self, field: np.ndarray) -> Tuple[np.ndarray, ...]:
        """
        Compute gradient of field in spectral space.

        Physical Meaning:
            Computes the gradient ∇a of the phase field in 7D space-time,
            representing the spatial and phase variations of the field.

        Mathematical Foundation:
            Gradient in spectral space: ∇a → ik * â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            Tuple[np.ndarray, ...]: Gradient components in each dimension.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for gradient computation")

        # Transform to spectral space (fallback to np.fft if unified backend not applicable)
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

        # Compute gradient components
        gradient_components = []
        for i, k_vec in enumerate(self._wave_vectors):
            gradient_spectral = 1j * k_vec * field_spectral
            try:
                gradient_component = spectral_ops.inverse_fft(gradient_spectral, normalization="physics")  # type: ignore[name-defined]
            except Exception:
                gradient_component = np.fft.ifftn(gradient_spectral)
            gradient_components.append(gradient_component.real.astype(self.precision))

        return tuple(gradient_components)

    def compute_divergence(self, field: np.ndarray) -> np.ndarray:
        """
        Compute divergence of vector field in spectral space.

        Physical Meaning:
            Computes the divergence ∇·a of the vector field in 7D space-time,
            representing the net flux of the field.

        Mathematical Foundation:
            Divergence in spectral space: ∇·a → ik · â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Vector field to differentiate.

        Returns:
            np.ndarray: Divergence of the field.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for divergence computation")

        # For scalar field, divergence is zero
        if len(field.shape) == len(self.domain.shape):
            return np.zeros_like(field)

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

        # Compute divergence
        divergence_spectral = np.zeros_like(field_spectral)
        for i, k_vec in enumerate(self._wave_vectors):
            if i < field.shape[-1]:  # Check if we have enough components
                divergence_spectral += 1j * k_vec * field_spectral[..., i]

        # Transform back to real space
        try:
            divergence = spectral_ops.inverse_fft(divergence_spectral, normalization="physics")  # type: ignore[name-defined]
        except Exception:
            divergence = np.fft.ifftn(divergence_spectral)
        return divergence.real.astype(self.precision)

    def compute_curl(self, field: np.ndarray) -> Tuple[np.ndarray, ...]:
        """
        Compute curl of vector field in spectral space.

        Physical Meaning:
            Computes the curl ∇×a of the vector field in 7D space-time,
            representing the rotational component of the field.

        Mathematical Foundation:
            Curl in spectral space: ∇×a → ik × â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Vector field to differentiate.

        Returns:
            Tuple[np.ndarray, ...]: Curl components in each dimension.
        """
        if not self._validate_field(field):
            raise ValueError("Invalid field for curl computation")

        # For scalar field, curl is zero
        if len(field.shape) == len(self.domain.shape):
            return tuple(np.zeros_like(field) for _ in range(len(self.domain.shape)))

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

        # Compute curl components
        curl_components = []
        for i in range(len(self.domain.shape)):
            curl_spectral = np.zeros_like(field_spectral[..., 0])

            # Compute curl using cross product in spectral space
            for j in range(len(self.domain.shape)):
                for k in range(len(self.domain.shape)):
                    if i != j and j != k and k != i:
                        # Levi-Civita symbol: ε_ijk
                        epsilon = (
                            1 if (i, j, k) in [(0, 1, 2), (1, 2, 0), (2, 0, 1)] else -1
                        )
                        if epsilon != 0 and k < field.shape[-1]:
                            curl_spectral += (
                                epsilon
                                * 1j
                                * self._wave_vectors[j]
                                * field_spectral[..., k]
                            )

            try:
                curl_component = spectral_ops.inverse_fft(curl_spectral, normalization="physics")  # type: ignore[name-defined]
            except Exception:
                curl_component = np.fft.ifftn(curl_spectral)
            curl_components.append(curl_component.real.astype(self.precision))

        return tuple(curl_components)

    def _validate_field(self, field: np.ndarray) -> bool:
        """Validate field for vector operations."""
        return field is not None and field.size > 0

