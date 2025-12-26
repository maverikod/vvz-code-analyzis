"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data structures for mode beating analysis.

This module contains data structures used in mode beating analysis
for Level C test C4 in 7D phase field theory.

Physical Meaning:
    Defines data structures for mode beating analysis, including
    dual-mode source specification and beating pattern representation.

Example:
    >>> dual_mode = DualModeSource(frequency_1=1.0, frequency_2=1.1)
    >>> pattern = BeatingPattern(magnitude=0.5, direction=np.array([1, 0, 0]))
"""

import numpy as np
from dataclasses import dataclass
from typing import List


@dataclass
class DualModeSource:
    """
    Dual-mode source specification.

    Physical Meaning:
        Defines a dual-mode source for mode beating analysis,
        including frequencies, amplitudes, and spatial profiles.

    Mathematical Foundation:
        Represents a dual-mode source of the form:
        s(x,t) = s₁(x) e^(-iω₁t) + s₂(x) e^(-iω₂t)
        where s₁(x) and s₂(x) are spatial profiles and
        ω₁ and ω₂ are the two frequencies.

    Attributes:
        frequency_1 (float): First frequency ω₁.
        frequency_2 (float): Second frequency ω₂.
        amplitude_1 (float): Amplitude of first mode.
        amplitude_2 (float): Amplitude of second mode.
        spatial_profile_1 (np.ndarray): Spatial profile s₁(x).
        spatial_profile_2 (np.ndarray): Spatial profile s₂(x).
        phase_1 (float): Phase of first mode.
        phase_2 (float): Phase of second mode.
    """

    frequency_1: float
    frequency_2: float
    amplitude_1: float = 1.0
    amplitude_2: float = 1.0
    spatial_profile_1: np.ndarray = None
    spatial_profile_2: np.ndarray = None
    phase_1: float = 0.0
    phase_2: float = 0.0

    def __post_init__(self):
        """Initialize default spatial profiles if not provided."""
        if self.spatial_profile_1 is None:
            self.spatial_profile_1 = np.ones(1)
        if self.spatial_profile_2 is None:
            self.spatial_profile_2 = np.ones(1)

    @property
    def frequency_difference(self) -> float:
        """
        Frequency difference between modes.

        Physical Meaning:
            Computes the frequency difference Δω = |ω₂ - ω₁|,
            which determines the beating frequency.

        Returns:
            float: Frequency difference.
        """
        return abs(self.frequency_2 - self.frequency_1)

    @property
    def beating_frequency(self) -> float:
        """
        Beating frequency.

        Physical Meaning:
            Computes the beating frequency ω_beat = |ω₂ - ω₁|,
            which determines the rate of amplitude modulation.

        Returns:
            float: Beating frequency.
        """
        return self.frequency_difference

    @property
    def average_frequency(self) -> float:
        """
        Average frequency of the two modes.

        Physical Meaning:
            Computes the average frequency (ω₁ + ω₂) / 2,
            which represents the carrier frequency.

        Returns:
            float: Average frequency.
        """
        return (self.frequency_1 + self.frequency_2) / 2.0


@dataclass
class BeatingPattern:
    """
    Beating pattern representation.

    Physical Meaning:
        Represents a beating pattern with magnitude, direction,
        and frequency characteristics.

    Mathematical Foundation:
        Represents a beating pattern with:
        - Magnitude: |A| - amplitude of the beating
        - Direction: n̂ - unit vector indicating pattern direction
        - Frequency: ω - frequency of the beating pattern

    Attributes:
        magnitude (float): Magnitude of the beating pattern.
        direction (np.ndarray): Direction vector of the pattern.
        frequency (float): Frequency of the beating pattern.
    """

    magnitude: float
    direction: np.ndarray
    frequency: float

    def __post_init__(self):
        """Normalize direction vector."""
        if self.direction is not None:
            norm = np.linalg.norm(self.direction)
            if norm > 0:
                self.direction = self.direction / norm

    @property
    def normalized_magnitude(self) -> float:
        """
        Normalized magnitude of the beating pattern.

        Physical Meaning:
            Returns the magnitude normalized by the maximum
            possible magnitude for the given frequency.

        Returns:
            float: Normalized magnitude.
        """
        return self.magnitude / (1.0 + self.frequency)

    @property
    def pattern_energy(self) -> float:
        """
        Energy of the beating pattern.

        Physical Meaning:
            Computes the energy associated with the beating
            pattern, proportional to the square of the magnitude.

        Returns:
            float: Pattern energy.
        """
        return 0.5 * self.magnitude**2

    @property
    def pattern_momentum(self) -> np.ndarray:
        """
        Momentum of the beating pattern.

        Physical Meaning:
            Computes the momentum associated with the beating
            pattern, proportional to the magnitude and direction.

        Returns:
            np.ndarray: Pattern momentum.
        """
        return self.magnitude * self.direction
