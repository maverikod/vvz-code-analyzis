"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for spectral derivatives implementation.
"""

from typing import Any, Tuple

from .spectral_derivatives_impl_base import SpectralDerivativesImplBase
from .spectral_derivatives_impl_derivatives import SpectralDerivativesImplDerivatives
from .spectral_derivatives_impl_vector import SpectralDerivativesImplVector
from .spectral_derivatives_impl_laplacian import SpectralDerivativesImplLaplacian
from .spectral_derivatives_impl_wave_vectors import SpectralDerivativesImplWaveVectors


class SpectralDerivatives(SpectralDerivativesImplBase):
    """
    Spectral derivatives for 7D phase field calculations.

    Physical Meaning:
        Implements mathematical differentiation operations in 7D frequency space,
        providing efficient computation of derivatives for 7D phase field
        calculations with U(1)³ phase structure.

    Mathematical Foundation:
        Uses the property that differentiation in real space corresponds to
        multiplication by ik in frequency space for efficient computation.
    """

    def __init__(self, domain: Any, precision: str = "float64"):
        """Initialize spectral derivatives."""
        super().__init__(domain, precision)
        self._setup_computers()

    def _setup_computers(self):
        """Setup computation modules."""
        if self._wave_vectors is not None and self._k_magnitude_squared is not None:
            self._derivatives_computer = SpectralDerivativesImplDerivatives(
                self.domain, self.precision, self._wave_vectors
            )
            self._vector_computer = SpectralDerivativesImplVector(
                self.domain, self.precision, self._wave_vectors
            )
            self._laplacian_computer = SpectralDerivativesImplLaplacian(
                self.domain, self.precision, self._k_magnitude_squared
            )
        else:
            self._derivatives_computer = None
            self._vector_computer = None
            self._laplacian_computer = None

    def _ensure_wave_vectors(self):
        """Ensure wave vectors are computed."""
        if self._wave_vectors is None or self._k_magnitude_squared is None:
            if hasattr(self.domain, "shape"):
                wave_vectors_computer = SpectralDerivativesImplWaveVectors(self.domain)
                self._wave_vectors = wave_vectors_computer.compute_wave_vectors()
                self._k_magnitude_squared = wave_vectors_computer.compute_k_magnitude_squared(
                    self._wave_vectors
                )
                self._setup_computers()
            else:
                raise ValueError("Domain shape is required for spectral derivatives")

    def compute_derivative(
        self, field, axis: int, order: int = 1
    ):
        """Compute nth derivative along a given axis using spectral method."""
        self._ensure_wave_vectors()
        return self._derivatives_computer.compute_derivative(field, axis, order)

    def compute_mixed_derivative(
        self, field, axes: Tuple[int, int], orders: Tuple[int, int]
    ):
        """Compute mixed derivative along two axes."""
        self._ensure_wave_vectors()
        return self._derivatives_computer.compute_mixed_derivative(field, axes, orders)

    def compute_gradient(self, field):
        """Compute gradient of field in spectral space."""
        self._ensure_wave_vectors()
        return self._vector_computer.compute_gradient(field)

    def compute_divergence(self, field):
        """Compute divergence of vector field in spectral space."""
        self._ensure_wave_vectors()
        return self._vector_computer.compute_divergence(field)

    def compute_curl(self, field):
        """Compute curl of vector field in spectral space."""
        self._ensure_wave_vectors()
        return self._vector_computer.compute_curl(field)

    def compute_laplacian(self, field):
        """Compute Laplacian of field in spectral space."""
        self._ensure_wave_vectors()
        return self._laplacian_computer.compute_laplacian(field)

    def compute_bi_laplacian(self, field):
        """Compute bi-Laplacian (fourth-order derivative) of field."""
        self._ensure_wave_vectors()
        return self._laplacian_computer.compute_bi_laplacian(field)

    def __repr__(self) -> str:
        """String representation of spectral derivatives."""
        return f"{self.__class__.__name__}(domain={self.domain.shape}, precision={self.precision})"

