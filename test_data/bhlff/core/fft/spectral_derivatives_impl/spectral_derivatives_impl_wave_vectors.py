"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Wave vectors computation for spectral derivatives.
"""

import numpy as np
from typing import Tuple, Any


class SpectralDerivativesImplWaveVectors:
    """
    Wave vectors computation for spectral derivatives.

    Physical Meaning:
        Computes the wave vectors k for each dimension of the domain,
        representing the frequency components in spectral space.
    """

    def __init__(self, domain: Any):
        """
        Initialize wave vectors computer.

        Args:
            domain (Any): Computational domain.
        """
        self.domain = domain

    def compute_wave_vectors(self) -> Tuple[np.ndarray, ...]:
        """
        Compute wave vectors for the domain.

        Physical Meaning:
            Computes the wave vectors k for each dimension of the domain,
            representing the frequency components in spectral space.

        Returns:
            Tuple[np.ndarray, ...]: Wave vectors for each dimension.
        """
        wave_vectors = []

        num_dims = len(self.domain.shape)
        for axis, axis_size in enumerate(self.domain.shape):
            # Determine physical spacing per axis (Domain7DBVP-aware)
            if hasattr(self.domain, "N_spatial") and num_dims == 7:
                if axis < 3:  # spatial x,y,z
                    N_axis = self.domain.N_spatial
                    d_axis = self.domain.L_spatial / self.domain.N_spatial
                elif axis < 6:  # phase φ1,φ2,φ3 (period 2π)
                    N_axis = self.domain.N_phase
                    d_axis = 2 * np.pi / self.domain.N_phase
                else:  # time t
                    N_axis = self.domain.N_t
                    d_axis = self.domain.T / self.domain.N_t
            else:
                # Legacy fallback: assume first 3 spatial (L,N), next 3 phase (2π,N_phi), last time (T,N_t)
                if axis < 3 and hasattr(self.domain, "N") and hasattr(self.domain, "L"):
                    N_axis = getattr(self.domain, "N", axis_size)
                    d_axis = getattr(self.domain, "L", float(axis_size)) / max(
                        1, N_axis
                    )
                elif axis < 6 and hasattr(self.domain, "N_phi"):
                    N_axis = getattr(self.domain, "N_phi", axis_size)
                    d_axis = 2 * np.pi / max(1, N_axis)
                elif hasattr(self.domain, "N_t") and hasattr(self.domain, "T"):
                    N_axis = getattr(self.domain, "N_t", axis_size)
                    d_axis = getattr(self.domain, "T", float(axis_size)) / max(
                        1, N_axis
                    )
                else:
                    # As a last resort, assume unit spacing scaled to axis length
                    N_axis = axis_size
                    d_axis = 1.0

            # Compute 1D wave vector with physical scaling (radians per unit)
            k_1d = 2 * np.pi * np.fft.fftfreq(N_axis, d=d_axis)

            # Reshape for broadcasting across the full domain shape
            reshape_pattern = [1] * num_dims
            reshape_pattern[axis] = axis_size
            # If N_axis differs from axis_size (defensive), interpolate or trim/pad
            if N_axis != axis_size:
                # Simple safe handling: resample via slicing or padding zeros
                if N_axis > axis_size:
                    k_1d = k_1d[:axis_size]
                else:
                    pad = axis_size - N_axis
                    k_1d = np.pad(k_1d, (0, pad), mode="constant")
            k_axis = k_1d.reshape(reshape_pattern)

            wave_vectors.append(k_axis)

        return tuple(wave_vectors)

    def compute_k_magnitude_squared(self, wave_vectors: Tuple[np.ndarray, ...]) -> np.ndarray:
        """
        Compute squared magnitude of wave vectors.

        Physical Meaning:
            Computes |k|² for each point in the domain, representing
            the squared magnitude of the wave vector in spectral space.

        Args:
            wave_vectors (Tuple[np.ndarray, ...]): Wave vectors for each dimension.

        Returns:
            np.ndarray: Squared magnitude of wave vectors.
        """
        k_magnitude_squared = np.zeros(self.domain.shape)

        for k_vec in wave_vectors:
            k_magnitude_squared += k_vec**2  # broadcasting-safe

        return k_magnitude_squared

