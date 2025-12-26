"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Spectral filtering implementation for 7D BHLFF Framework.

This module provides spectral filtering operations for the 7D phase field theory,
including low-pass, high-pass, band-pass filters and noise reduction with
optimized performance for 7D computations.

Physical Meaning:
    Spectral filtering implements mathematical filtering operations in frequency
    space, providing efficient noise reduction and signal processing for
    7D phase field calculations with U(1)³ phase structure.

Mathematical Foundation:
    Implements spectral filtering using transfer functions in frequency space:
    - Low-pass: H(k) = 1/(1 + (|k|/k_c)²ⁿ)
    - High-pass: H(k) = (|k|/k_c)²ⁿ/(1 + (|k|/k_c)²ⁿ)
    - Band-pass: H(k) = 1/(1 + ((|k|-k_0)/Δk)²ⁿ)
    - Gaussian: H(k) = exp(-(|k|/σ)²)

Example:
    >>> filt = SpectralFiltering(domain, precision="float64")
    >>> filtered_field = filt.apply_low_pass_filter(field, cutoff_frequency=0.1)
    >>> denoised_field = filt.apply_gaussian_filter(field, sigma=0.05)
"""

import numpy as np
from typing import Any, Tuple, Dict, Optional
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import Domain


class SpectralFiltering:
    """
    Spectral filtering for 7D phase field calculations.

    Physical Meaning:
        Implements mathematical filtering operations in 7D frequency space,
        providing efficient noise reduction and signal processing for
        7D phase field calculations with U(1)³ phase structure.

    Mathematical Foundation:
        Uses transfer functions in frequency space to filter field components
        based on their spatial and temporal frequencies.

    Attributes:
        domain (Domain): Computational domain for the simulation.
        precision (str): Numerical precision for computations.
        _k_magnitude (np.ndarray): Pre-computed wave vector magnitudes.
    """

    def __init__(self, domain: "Domain", precision: str = "float64"):
        """
        Initialize spectral filtering.

        Physical Meaning:
            Sets up the spectral filtering calculator with the computational
            domain and numerical precision, pre-computing wave vector magnitudes
            for efficient filtering operations.

        Args:
            domain (Domain): Computational domain with grid information.
            precision (str): Numerical precision ('float64' or 'float32').
        """
        self.domain = domain
        self.precision = precision
        self.logger = logging.getLogger(__name__)

        # Pre-compute wave vector magnitudes
        self._k_magnitude = self._compute_k_magnitude()

        self.logger.info(f"SpectralFiltering initialized for domain {domain.shape}")

    def apply_low_pass_filter(
        self, field: np.ndarray, cutoff_frequency: float, order: int = 2
    ) -> np.ndarray:
        """
        Apply low-pass filter to field in spectral space.

        Physical Meaning:
            Applies a low-pass filter to remove high-frequency components
            from the phase field, representing smoothing of the field
            configuration while preserving large-scale structures.

        Mathematical Foundation:
            Transfer function: H(k) = 1/(1 + (|k|/k_c)²ⁿ)
            where k_c is the cutoff frequency and n is the filter order.

        Args:
            field (np.ndarray): Field to filter.
            cutoff_frequency (float): Cutoff frequency k_c.
            order (int): Filter order n (default: 2).

        Returns:
            np.ndarray: Filtered field.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)

        # Compute transfer function
        transfer_function = 1.0 / (
            1.0 + (self._k_magnitude / cutoff_frequency) ** (2 * order)
        )

        # Apply filter
        filtered_spectral = transfer_function * field_spectral

        # Transform back to real space
        filtered_field = np.fft.ifftn(filtered_spectral)
        return filtered_field.real.astype(self.precision)

    def apply_high_pass_filter(
        self, field: np.ndarray, cutoff_frequency: float, order: int = 2
    ) -> np.ndarray:
        """
        Apply high-pass filter to field in spectral space.

        Physical Meaning:
            Applies a high-pass filter to remove low-frequency components
            from the phase field, representing enhancement of small-scale
            structures and details.

        Mathematical Foundation:
            Transfer function: H(k) = (|k|/k_c)²ⁿ/(1 + (|k|/k_c)²ⁿ)
            where k_c is the cutoff frequency and n is the filter order.

        Args:
            field (np.ndarray): Field to filter.
            cutoff_frequency (float): Cutoff frequency k_c.
            order (int): Filter order n (default: 2).

        Returns:
            np.ndarray: Filtered field.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)

        # Compute transfer function
        ratio = self._k_magnitude / cutoff_frequency
        transfer_function = (ratio ** (2 * order)) / (1.0 + ratio ** (2 * order))

        # Apply filter
        filtered_spectral = transfer_function * field_spectral

        # Transform back to real space
        filtered_field = np.fft.ifftn(filtered_spectral)
        return filtered_field.real.astype(self.precision)

    def apply_band_pass_filter(
        self,
        field: np.ndarray,
        center_frequency: float,
        bandwidth: float,
        order: int = 2,
    ) -> np.ndarray:
        """
        Apply band-pass filter to field in spectral space.

        Physical Meaning:
            Applies a band-pass filter to preserve components within a
            specific frequency range, representing selective enhancement
            of structures at particular scales.

        Mathematical Foundation:
            Transfer function: H(k) = 1/(1 + ((|k|-k_0)/Δk)²ⁿ)
            where k_0 is the center frequency, Δk is the bandwidth, and n is the order.

        Args:
            field (np.ndarray): Field to filter.
            center_frequency (float): Center frequency k_0.
            bandwidth (float): Bandwidth Δk.
            order (int): Filter order n (default: 2).

        Returns:
            np.ndarray: Filtered field.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)

        # Compute transfer function
        frequency_deviation = (self._k_magnitude - center_frequency) / bandwidth
        transfer_function = 1.0 / (1.0 + frequency_deviation ** (2 * order))

        # Apply filter
        filtered_spectral = transfer_function * field_spectral

        # Transform back to real space
        filtered_field = np.fft.ifftn(filtered_spectral)
        return filtered_field.real.astype(self.precision)

    def apply_gaussian_filter(self, field: np.ndarray, sigma: float) -> np.ndarray:
        """
        Apply Gaussian filter to field in spectral space.

        Physical Meaning:
            Applies a Gaussian filter for smooth noise reduction,
            representing convolution with a Gaussian kernel in real space.

        Mathematical Foundation:
            Transfer function: H(k) = exp(-(|k|/σ)²)
            where σ is the standard deviation of the Gaussian.

        Args:
            field (np.ndarray): Field to filter.
            sigma (float): Standard deviation σ of the Gaussian.

        Returns:
            np.ndarray: Filtered field.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"Field shape {field.shape} incompatible with domain {self.domain.shape}"
            )

        # Transform to spectral space
        field_spectral = np.fft.fftn(field)

        # Compute transfer function
        transfer_function = self._step_resonator_transfer_function(
            self._k_magnitude, sigma
        )

        # Apply filter
        filtered_spectral = transfer_function * field_spectral

        # Transform back to real space
        filtered_field = np.fft.ifftn(filtered_spectral)
        return filtered_field.real.astype(self.precision)

    def apply_spectral_filter(
        self, field: np.ndarray, filter_type: str, **kwargs
    ) -> np.ndarray:
        """
        Apply spectral filter of specified type.

        Physical Meaning:
            Applies a spectral filter of the specified type to the field,
            providing a unified interface for different filtering operations.

        Args:
            field (np.ndarray): Field to filter.
            filter_type (str): Type of filter ('low_pass', 'high_pass', 'band_pass', 'gaussian').
            **kwargs: Additional arguments for the specific filter type.

        Returns:
            np.ndarray: Filtered field.
        """
        if filter_type == "low_pass":
            return self.apply_low_pass_filter(field, **kwargs)
        elif filter_type == "high_pass":
            return self.apply_high_pass_filter(field, **kwargs)
        elif filter_type == "band_pass":
            return self.apply_band_pass_filter(field, **kwargs)
        elif filter_type == "gaussian":
            return self.apply_gaussian_filter(field, **kwargs)
        else:
            raise ValueError(f"Unknown filter type: {filter_type}")

    def apply_noise_reduction(
        self, field: np.ndarray, noise_level: float = 0.1, method: str = "gaussian"
    ) -> np.ndarray:
        """
        Apply noise reduction to field.

        Physical Meaning:
            Applies noise reduction to the phase field, representing
            removal of high-frequency noise while preserving signal content.

        Args:
            field (np.ndarray): Field to denoise.
            noise_level (float): Estimated noise level.
            method (str): Denoising method ('gaussian', 'low_pass').

        Returns:
            np.ndarray: Denoised field.
        """
        if method == "gaussian":
            # Use Gaussian filter with sigma based on noise level
            sigma = noise_level * np.max(self._k_magnitude)
            return self.apply_gaussian_filter(field, sigma)
        elif method == "low_pass":
            # Use low-pass filter with cutoff based on noise level
            cutoff = noise_level * np.max(self._k_magnitude)
            return self.apply_low_pass_filter(field, cutoff)
        else:
            raise ValueError(f"Unknown denoising method: {method}")

    def _compute_k_magnitude(self) -> np.ndarray:
        """
        Compute magnitude of wave vectors.

        Physical Meaning:
            Computes the magnitude |k| of the wave vectors, representing
            the spatial frequency of the field components.

        Mathematical Foundation:
            |k|² = k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²

        Returns:
            np.ndarray: Wave vector magnitudes.
        """
        if hasattr(self.domain, "N_spatial"):
            # New Domain7DBVP structure
            # Compute wave vectors for all dimensions
            k_magnitude_squared = np.zeros(self.domain.shape)

            # Spatial dimensions (x, y, z)
            for i in range(3):
                k = np.fft.fftfreq(
                    self.domain.N_spatial, self.domain.L_spatial / self.domain.N_spatial
                )
                k = k * 2 * np.pi / self.domain.L_spatial
                k = np.broadcast_to(k.reshape(-1, 1, 1, 1, 1, 1, 1), self.domain.shape)
                k_magnitude_squared += k**2

            # Phase dimensions (φ₁, φ₂, φ₃)
            for i in range(3):
                k = np.fft.fftfreq(self.domain.N_phase, 2 * np.pi / self.domain.N_phase)
                k = k * 2 * np.pi / (2 * np.pi)
                k = np.broadcast_to(k.reshape(1, 1, 1, -1, 1, 1, 1), self.domain.shape)
                k_magnitude_squared += k**2

            # Time dimension (t)
            k = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)
            k = k * 2 * np.pi / self.domain.T
            k = np.broadcast_to(k.reshape(1, 1, 1, 1, 1, 1, -1), self.domain.shape)
            k_magnitude_squared += k**2

            return np.sqrt(k_magnitude_squared)

    def _step_resonator_transfer_function(
        self, k_magnitude: np.ndarray, sigma: float
    ) -> np.ndarray:
        """
        Step resonator transfer function according to 7D BVP theory.

        Physical Meaning:
            Implements step function transfer function instead of exponential decay
            according to 7D BVP theory principles.
        """
        cutoff_frequency = sigma * 0.8  # 80% of sigma
        return np.where(k_magnitude < cutoff_frequency, 1.0, 0.0)

        # Old Domain structure
        # Compute wave vectors for all dimensions
        k_magnitude_squared = np.zeros(self.domain.shape)

        # Spatial dimensions (x, y, z)
        for i in range(3):
            k = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
            k = k * 2 * np.pi / self.domain.L
            k = np.broadcast_to(k.reshape(-1, 1, 1, 1, 1, 1, 1), self.domain.shape)
            k_magnitude_squared += k**2

        # Phase dimensions (φ₁, φ₂, φ₃)
        for i in range(3):
            k = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
            k = k * 2 * np.pi / (2 * np.pi)
            k = np.broadcast_to(k.reshape(1, 1, 1, -1, 1, 1, 1), self.domain.shape)
            k_magnitude_squared += k**2

        # Time dimension (t)
        k = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)
        k = k * 2 * np.pi / self.domain.T
        k = np.broadcast_to(k.reshape(1, 1, 1, 1, 1, 1, -1), self.domain.shape)
        k_magnitude_squared += k**2

        return np.sqrt(k_magnitude_squared)

    def _step_resonator_transfer_function(
        self, k_magnitude: np.ndarray, sigma: float
    ) -> np.ndarray:
        """
        Step resonator transfer function according to 7D BVP theory.

        Physical Meaning:
            Implements step function transfer function instead of exponential decay
            according to 7D BVP theory principles.
        """
        cutoff_frequency = sigma * 0.8  # 80% of sigma
        return np.where(k_magnitude < cutoff_frequency, 1.0, 0.0)
