"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Field projectors for different interaction windows.

This module provides EM, Strong, and Weak projectors.
"""

import numpy as np
from typing import Dict, Any, Tuple


class EMProjector:
    """Electromagnetic field projector."""

    def __init__(self, params: Dict[str, Any]):
        """Initialize EM projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [0.1, 1.0])
        self.amplitude_threshold = params.get("amplitude_threshold", 0.1)
        self.filter_type = params.get("filter_type", "bandpass")

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto EM window."""
        # FFT transform
        fft_field = np.fft.fftn(field)

        # Create EM filter
        em_filter = self._create_em_filter(fft_field.shape)

        # Apply filter
        em_field_fft = fft_field * em_filter

        # Inverse FFT
        em_field = np.fft.ifftn(em_field_fft)

        return em_field.real

    def _create_em_filter(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create EM window filter."""
        # Create frequency grid
        frequencies = self._create_frequency_grid(shape)

        # Create bandpass filter
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]

        em_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )

        return em_filter

    def _create_frequency_grid(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid for filtering."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)

        return frequencies


class StrongProjector:
    """Strong interaction field projector."""

    def __init__(self, params: Dict[str, Any]):
        """Initialize strong projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [1.0, 10.0])
        self.q_threshold = params.get("q_threshold", 100)
        self.filter_type = params.get("filter_type", "high_q")

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto strong window."""
        # FFT transform
        fft_field = np.fft.fftn(field)

        # Create strong filter
        strong_filter = self._create_strong_filter(fft_field.shape)

        # Apply filter
        strong_field_fft = fft_field * strong_filter

        # Inverse FFT
        strong_field = np.fft.ifftn(strong_field_fft)

        return strong_field.real

    def _create_strong_filter(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create strong window filter."""
        # Create frequency grid
        frequencies = self._create_frequency_grid(shape)

        # Create high-frequency filter
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]

        strong_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )

        # Apply Q-factor filtering
        q_factor = self.q_threshold
        strong_filter *= self._apply_q_factor_filter(frequencies, q_factor)

        return strong_filter

    def _create_frequency_grid(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid for filtering."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)

        return frequencies

    def _apply_q_factor_filter(
        self, frequencies: np.ndarray, q_factor: float
    ) -> np.ndarray:
        """Apply Q-factor filtering using step resonator model."""
        # Step resonator Q-factor filter
        q_filter = self._step_q_factor_filter(frequencies, q_factor)
        return q_filter

    def _step_q_factor_filter(
        self, frequencies: np.ndarray, q_factor: float
    ) -> np.ndarray:
        """
        Step function Q-factor filter.
        
        Physical Meaning:
            Implements step resonator model for Q-factor filtering instead of
            exponential decay. This follows 7D BVP theory principles where
            filtering occurs through semi-transparent boundaries.
        """
        # Step resonator parameters
        cutoff_frequency = q_factor
        filter_strength = 1.0

        # Step function filter: 1.0 below cutoff, 0.0 above
        return filter_strength * np.where(frequencies < cutoff_frequency, 1.0, 0.0)


class WeakProjector:
    """Weak interaction field projector."""

    def __init__(self, params: Dict[str, Any]):
        """Initialize weak projector."""
        self.params = params
        self.frequency_range = params.get("frequency_range", [0.01, 0.1])
        self.q_threshold = params.get("q_threshold", 10)
        self.filter_type = params.get("filter_type", "chiral")

    def project(self, field: np.ndarray) -> np.ndarray:
        """Project field onto weak window."""
        # FFT transform
        fft_field = np.fft.fftn(field)

        # Create weak filter
        weak_filter = self._create_weak_filter(fft_field.shape)

        # Apply filter
        weak_field_fft = fft_field * weak_filter

        # Inverse FFT
        weak_field = np.fft.ifftn(weak_field_fft)

        return weak_field.real

    def _create_weak_filter(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create weak window filter."""
        # Create frequency grid
        frequencies = self._create_frequency_grid(shape)

        # Create low-frequency filter
        filter_low = self.frequency_range[0]
        filter_high = self.frequency_range[1]

        weak_filter = np.where(
            (frequencies >= filter_low) & (frequencies <= filter_high), 1.0, 0.0
        )

        # Apply chiral filtering
        chiral_factor = self.params.get("chiral_threshold", 0.1)
        weak_filter *= self._apply_chiral_filter(chiral_factor)

        return weak_filter

    def _create_frequency_grid(self, shape: Tuple[int, ...]) -> np.ndarray:
        """Create frequency grid for filtering."""
        if len(shape) == 3:
            kx = np.fft.fftfreq(shape[0])
            ky = np.fft.fftfreq(shape[1])
            kz = np.fft.fftfreq(shape[2])
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            frequencies = np.sqrt(KX**2 + KY**2 + KZ**2)
        else:
            frequencies = np.ones(shape)

        return frequencies

    def _apply_chiral_filter(self, chiral_factor: float) -> np.ndarray:
        """Apply chiral filtering."""
        # Simple chiral filter
        chiral_filter = (
            np.ones_like(chiral_factor)
            if np.isscalar(chiral_factor)
            else np.ones(chiral_factor.shape)
        )
        return chiral_filter

