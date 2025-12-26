"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field class for BHLFF phase field representation.

This module implements the phase field representation for 7D phase field
theory simulations, providing field operations, transformations, and
analysis capabilities.

Physical Meaning:
    The phase field represents the fundamental field configuration in
    7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, describing the spatial and
    temporal evolution of phase values.

Mathematical Foundation:
    The phase field a(x,t) is a complex-valued function that satisfies
    the fractional Riesz equation and related evolution equations
    governing phase field dynamics.
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass

from ..domain import Domain


@dataclass
class Field:
    """
    Phase field representation for 7D phase field theory.

    Physical Meaning:
        Represents a phase field configuration in 7D space-time,
        providing the fundamental field values and operations for
        phase field simulations.

    Mathematical Foundation:
        The field a(x,t) is a complex-valued function that satisfies
        the fractional Riesz equation and related evolution equations.

    Attributes:
        data (np.ndarray): Field data array.
        domain (Domain): Computational domain.
        time (float): Current time value.
        metadata (Dict[str, Any]): Additional field metadata.
    """

    data: np.ndarray
    domain: Domain
    time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """
        Initialize field after object creation.

        Physical Meaning:
            Validates field data and sets up metadata for
            phase field operations.
        """
        if self.metadata is None:
            self.metadata = {}

        self._validate_field()

    def _validate_field(self) -> None:
        """
        Validate field data.

        Physical Meaning:
            Ensures field data has correct shape and properties
            for the computational domain.

        Raises:
            ValueError: If field data is invalid.
        """
        if self.data.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {self.data.shape} incompatible with "
                f"domain shape {self.domain.shape}"
            )

    def get_amplitude(self) -> np.ndarray:
        """
        Get field amplitude |a(x)|.

        Physical Meaning:
            Computes the amplitude of the phase field, representing
            the magnitude of the field at each spatial point.

        Mathematical Foundation:
            Amplitude is |a(x)| = √(a_real² + a_imag²).

        Returns:
            np.ndarray: Field amplitude |a(x)|.
        """
        return np.abs(self.data)

    def get_phase(self) -> np.ndarray:
        """
        Get field phase arg(a(x)).

        Physical Meaning:
            Computes the phase of the phase field, representing
            the phase angle at each spatial point.

        Mathematical Foundation:
            Phase is arg(a(x)) = arctan2(a_imag, a_real).

        Returns:
            np.ndarray: Field phase arg(a(x)).
        """
        return np.angle(self.data)

    def get_gradient(self) -> Tuple[np.ndarray, ...]:
        """
        Get field gradient ∇a(x).

        Physical Meaning:
            Computes the spatial gradient of the phase field,
            representing the rate of change of the field in space.

        Mathematical Foundation:
            Gradient is ∇a = (∂a/∂x, ∂a/∂y, ∂a/∂z).

        Returns:
            Tuple[np.ndarray, ...]: Field gradient components.
        """
        if self.domain.dimensions == 1:
            return (np.gradient(self.data, self.domain.dx),)
        elif self.domain.dimensions == 2:
            grad_x, grad_y = np.gradient(self.data, self.domain.dx, self.domain.dx)
            return (grad_x, grad_y)
        else:  # 3D
            grad_x, grad_y, grad_z = np.gradient(
                self.data, self.domain.dx, self.domain.dx, self.domain.dx
            )
            return (grad_x, grad_y, grad_z)

    def get_laplacian(self) -> np.ndarray:
        """
        Get field Laplacian Δa(x).

        Physical Meaning:
            Computes the Laplacian of the phase field, representing
            the second-order spatial derivatives.

        Mathematical Foundation:
            Laplacian is Δa = ∂²a/∂x² + ∂²a/∂y² + ∂²a/∂z².

        Returns:
            np.ndarray: Field Laplacian Δa(x).
        """
        gradient = self.get_gradient()

        if self.domain.dimensions == 1:
            return np.gradient(gradient[0], self.domain.dx)
        elif self.domain.dimensions == 2:
            grad_x, grad_y = gradient
            return np.gradient(grad_x, self.domain.dx, axis=0) + np.gradient(
                grad_y, self.domain.dx, axis=1
            )
        else:  # 3D
            grad_x, grad_y, grad_z = gradient
            return (
                np.gradient(grad_x, self.domain.dx, axis=0)
                + np.gradient(grad_y, self.domain.dx, axis=1)
                + np.gradient(grad_z, self.domain.dx, axis=2)
            )

    def get_energy_density(self) -> np.ndarray:
        """
        Get field energy density.

        Physical Meaning:
            Computes the local energy density of the phase field,
            representing the energy content per unit volume.

        Mathematical Foundation:
            Energy density is proportional to |∇a|² + |a|².

        Returns:
            np.ndarray: Field energy density.
        """
        gradient = self.get_gradient()
        gradient_magnitude_squared = sum(g**2 for g in gradient)
        amplitude_squared = self.get_amplitude() ** 2

        return gradient_magnitude_squared + amplitude_squared

    def get_total_energy(self) -> float:
        """
        Get total field energy.

        Physical Meaning:
            Computes the total energy of the phase field configuration,
            representing the integrated energy content over the domain.

        Mathematical Foundation:
            Total energy is ∫ energy_density dV over the domain.

        Returns:
            float: Total field energy.
        """
        energy_density = self.get_energy_density()
        volume_element = self.domain.dx**self.domain.dimensions

        return float(np.sum(energy_density) * volume_element)

    def fft(self) -> np.ndarray:
        """
        Compute FFT of the field.

        Physical Meaning:
            Transforms the field to frequency space for spectral
            analysis and operations.

        Mathematical Foundation:
            FFT transforms a(x) → â(k) in frequency space.

        Returns:
            np.ndarray: Field in frequency space â(k).
        """
        return np.fft.fftn(self.data)

    def ifft(self, spectral_data: np.ndarray) -> "Field":
        """
        Compute inverse FFT of spectral data.

        Physical Meaning:
            Transforms spectral data back to real space.

        Mathematical Foundation:
            IFFT transforms â(k) → a(x) in real space.

        Args:
            spectral_data (np.ndarray): Spectral field data.

        Returns:
            Field: Field in real space.
        """
        real_data = np.fft.ifftn(spectral_data)
        return Field(real_data, self.domain, self.time, self.metadata)

    def copy(self) -> "Field":
        """
        Create a copy of the field.

        Physical Meaning:
            Creates an independent copy of the field for
            manipulation without affecting the original.

        Returns:
            Field: Copy of the field.
        """
        return Field(
            self.data.copy(),
            self.domain,
            self.time,
            self.metadata.copy() if self.metadata is not None else {},
        )

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Set field metadata.

        Physical Meaning:
            Stores additional information about the field
            for analysis and visualization.

        Args:
            key (str): Metadata key.
            value (Any): Metadata value.
        """
        if self.metadata is not None:
            self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get field metadata.

        Physical Meaning:
            Retrieves additional information about the field.

        Args:
            key (str): Metadata key.
            default (Any): Default value if key not found.

        Returns:
            Any: Metadata value.
        """
        if self.metadata is not None:
            return self.metadata.get(key, default)
        return default

    def __repr__(self) -> str:
        """String representation of the field."""
        return (
            f"Field(shape={self.data.shape}, time={self.time}, "
            f"domain={self.domain})"
        )
