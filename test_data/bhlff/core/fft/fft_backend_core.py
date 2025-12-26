"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

FFT backend core implementation.

This module provides the core FFT backend for efficient spectral operations
in the 7D phase field theory.

Physical Meaning:
    FFT backend implements the computational engine for spectral methods,
    providing efficient transformation between real and frequency space
    for phase field calculations.

Mathematical Foundation:
    Implements Fast Fourier Transform operations for efficient computation
    of spectral methods in phase field equations.

Example:
    >>> backend = FFTBackend(domain, plan_type="MEASURE")
    >>> spectral_data = backend.fft(real_data)
    >>> real_data = backend.ifft(spectral_data)
"""

import numpy as np
from typing import Tuple, Dict, Any

from ..domain import Domain
from .fft_plan_manager import FFTPlanManager
from .fft_twiddle_computer import FFTTwiddleComputer
from .fft_butterfly_computer import FFTButterflyComputer
from .unified_spectral_operations import UnifiedSpectralOperations


class FFTBackend:
    """
    FFT backend for spectral operations.

    Physical Meaning:
        Provides the computational backend for Fast Fourier Transform
        operations, enabling efficient spectral methods for phase field
        calculations.

    Mathematical Foundation:
        Implements FFT operations for transforming between real space
        and frequency space, enabling efficient computation of spectral
        methods in phase field equations.

    Attributes:
        domain (Domain): Computational domain.
        plan_type (str): FFT planning strategy.
        _fft_plans (Dict): Pre-computed FFT plans.
    """

    def __init__(
        self,
        domain: Domain,
        plan_type: str = "MEASURE",
        precision: str = "float64",
    ) -> None:
        """
        Initialize FFT backend.

        Physical Meaning:
            Sets up the FFT backend with specified planning strategy
            and precision for efficient spectral operations.

        Args:
            domain (Domain): Computational domain for FFT operations.
            plan_type (str): FFT planning strategy ("ESTIMATE", "MEASURE",
                "PATIENT", "EXHAUSTIVE").
            precision (str): Numerical precision ("float32", "float64").

        Raises:
            ValueError: If plan_type or precision is not supported.
        """
        self.domain = domain
        self.plan_type = plan_type
        self.precision = precision

        # Add convenience attributes for domain properties
        self.N = domain.N
        self.N_phi = domain.N_phi
        self.N_t = domain.N_t
        self.dimensions = domain.dimensions

        # Initialize component managers
        self._plan_manager = FFTPlanManager(domain, plan_type, precision)
        self._twiddle_computer = FFTTwiddleComputer(domain, precision)
        self._butterfly_computer = FFTButterflyComputer(domain)

        # Setup FFT plans and pre-compute factors
        self._plan_manager.setup_fft_plans()
        self._twiddle_computer.precompute_twiddle_factors()

        # Setup memory pools for efficient allocation
        self._setup_memory_pools()

        # Initialize unified spectral operations for delegation
        self._unified_ops = UnifiedSpectralOperations(domain, precision)

    def _setup_memory_pools(self) -> None:
        """
        Setup memory pools for efficient allocation.

        Physical Meaning:
            Creates memory pools for efficient allocation and deallocation
            of temporary arrays during FFT operations.
        """
        self._memory_pools = {
            "temp_arrays": [],
            "workspace_arrays": [],
            "cache_size": 10,  # Number of arrays to keep in cache
        }

    def fft(self, real_data: np.ndarray) -> np.ndarray:
        """
        Compute forward FFT using unified spectral operations.

        Physical Meaning:
            Transforms real space data to frequency space using Fast
            Fourier Transform with proper normalization.

        Mathematical Foundation:
            Computes FFT: â(k) = FFT(a(x)) where a(x) is real space data
            and â(k) is frequency space data.

        Args:
            real_data (np.ndarray): Real space data a(x).

        Returns:
            np.ndarray: Frequency space data â(k).

        Raises:
            ValueError: If data shape is incompatible with domain.
        """
        # Delegate to unified spectral operations for better normalization support
        return self._unified_ops.forward_fft(real_data, "ortho")

    def ifft(self, spectral_data: np.ndarray) -> np.ndarray:
        """
        Compute inverse FFT using unified spectral operations.

        Physical Meaning:
            Transforms frequency space data back to real space using
            inverse Fast Fourier Transform with proper normalization.

        Mathematical Foundation:
            Computes IFFT: a(x) = IFFT(â(k)) where â(k) is frequency space
            data and a(x) is real space data.

        Args:
            spectral_data (np.ndarray): Frequency space data â(k).

        Returns:
            np.ndarray: Real space data a(x).

        Raises:
            ValueError: If data shape is incompatible with domain.
        """
        # Delegate to unified spectral operations for better normalization support
        return self._unified_ops.inverse_fft(spectral_data, "ortho")

    def fft_shift(self, spectral_data: np.ndarray) -> np.ndarray:
        """
        Shift FFT data to center zero frequency.

        Physical Meaning:
            Shifts the FFT data so that zero frequency is at the center
            of the array, which is useful for visualization and analysis.

        Mathematical Foundation:
            Applies fftshift to move zero frequency to the center:
            â_shifted(k) = fftshift(â(k))

        Args:
            spectral_data (np.ndarray): Frequency space data â(k).

        Returns:
            np.ndarray: Shifted frequency space data â_shifted(k).
        """
        # For 7D BVP theory, shift all 7 dimensions
        return np.fft.fftshift(spectral_data, axes=(0, 1, 2, 3, 4, 5, 6))

    def ifft_shift(self, spectral_data: np.ndarray) -> np.ndarray:
        """
        Inverse shift FFT data.

        Physical Meaning:
            Applies inverse fftshift to restore the original frequency
            ordering of the FFT data.

        Mathematical Foundation:
            Applies ifftshift to restore original frequency ordering:
            â(k) = ifftshift(â_shifted(k))

        Args:
            spectral_data (np.ndarray): Shifted frequency space data â_shifted(k).

        Returns:
            np.ndarray: Original frequency space data â(k).
        """
        # For 7D BVP theory, inverse shift all 7 dimensions
        return np.fft.ifftshift(spectral_data, axes=(0, 1, 2, 3, 4, 5, 6))

    def get_frequency_arrays(self) -> Tuple[np.ndarray, ...]:
        """
        Get frequency arrays for the domain.

        Physical Meaning:
            Returns the frequency arrays corresponding to the computational
            domain for spectral analysis.

        Mathematical Foundation:
            Computes frequency arrays using fftfreq:
            k = 2π * fftfreq(N, dx)

        Returns:
            Tuple[np.ndarray, ...]: Frequency arrays for each dimension.
        """
        dx = self.domain.dx

        # For 7D BVP theory, we need frequency arrays for all 7 dimensions
        # Spatial frequencies (3D)
        kx = 2 * np.pi * np.fft.fftfreq(self.domain.N, dx)
        ky = 2 * np.pi * np.fft.fftfreq(self.domain.N, dx)
        kz = 2 * np.pi * np.fft.fftfreq(self.domain.N, dx)

        # Phase frequencies (3D)
        kphi1 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phi, self.domain.dphi)
        kphi2 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phi, self.domain.dphi)
        kphi3 = 2 * np.pi * np.fft.fftfreq(self.domain.N_phi, self.domain.dphi)

        # Temporal frequency (1D)
        kt = 2 * np.pi * np.fft.fftfreq(self.domain.N_t, self.domain.dt)

        return (kx, ky, kz, kphi1, kphi2, kphi3, kt)

    def get_wave_vector_magnitude(self) -> np.ndarray:
        """
        Get wave vector magnitude for 7D BVP theory.

        Physical Meaning:
            Computes the magnitude of the 7D wave vector |k| = √(kx² + ky² + kz² + kφ₁² + kφ₂² + kφ₃² + kt²)
            for spectral operations in 7D space-time.

        Mathematical Foundation:
            |k| = √(∑ᵢ kᵢ²) where i runs over all 7 dimensions

        Returns:
            np.ndarray: 7D array of wave vector magnitudes with shape (N, N, N, N_phi, N_phi, N_phi, N_t)
        """
        kx, ky, kz, kphi1, kphi2, kphi3, kt = self.get_frequency_arrays()

        # Create 7D meshgrids
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
        )

        # Compute 7D wave vector magnitude
        k_magnitude = np.sqrt(
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )

        return k_magnitude

    def get_plan_type(self) -> str:
        """
        Get the FFT plan type.

        Physical Meaning:
            Returns the FFT planning strategy being used.

        Returns:
            str: FFT plan type.
        """
        return self._plan_manager.get_plan_type()

    def get_precision(self) -> str:
        """
        Get the numerical precision.

        Physical Meaning:
            Returns the numerical precision being used for FFT operations.

        Returns:
            str: Numerical precision.
        """
        return self._plan_manager.get_precision()

    def forward_transform(self, real_data: np.ndarray) -> np.ndarray:
        """
        Alias for fft() method.

        Args:
            real_data (np.ndarray): Real space data.

        Returns:
            np.ndarray: Frequency space data.
        """
        return self.fft(real_data)

    def inverse_transform(self, spectral_data: np.ndarray) -> np.ndarray:
        """
        Alias for ifft() method.

        Args:
            spectral_data (np.ndarray): Frequency space data.

        Returns:
            np.ndarray: Real space data.
        """
        return self.ifft(spectral_data)

    def get_wave_vectors(self, dim: int) -> np.ndarray:
        """
        Get wave vector for specific dimension.

        Args:
            dim (int): Dimension index (0-6 for 7D).

        Returns:
            np.ndarray: Wave vector for the specified dimension.
        """
        frequency_arrays = self.get_frequency_arrays()
        if 0 <= dim < len(frequency_arrays):
            return frequency_arrays[dim]
        else:
            raise ValueError(f"Dimension {dim} out of range for 7D BVP theory")

    def __repr__(self) -> str:
        """String representation of the FFT backend."""
        return (
            f"FFTBackend(domain={self.domain}, "
            f"plan_type={self.plan_type}, precision={self.precision})"
        )
