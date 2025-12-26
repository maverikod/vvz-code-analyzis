"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Data structures for boundary analysis.

This module contains data structures used in boundary analysis
for Level C test C1 in 7D phase field theory.

Physical Meaning:
    Defines data structures for boundary analysis, including
    boundary geometry, admittance spectrum, and radial profile.

Example:
    >>> boundary = BoundaryGeometry(center=np.array([0, 0, 0]), radius=1.0, thickness=0.1)
    >>> spectrum = AdmittanceSpectrum(frequencies=np.array([1.0, 2.0]), admittances=np.array([1.0, 2.0]))
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class BoundaryGeometry:
    """
    Boundary geometry specification.

    Physical Meaning:
        Defines the geometry of a boundary in the 7D phase field,
        including position, shape, and material properties.

    Mathematical Foundation:
        Represents a boundary geometry with:
        - Center position: x₀ = (x₀, y₀, z₀)
        - Radius: r for spherical boundaries
        - Thickness: Δr for boundary layer thickness
        - Contrast: η for material contrast

    Attributes:
        center (np.ndarray): Center position of the boundary.
        radius (float): Radius of the boundary.
        thickness (float): Thickness of the boundary layer.
        contrast (float): Material contrast parameter.
        geometry_type (str): Type of boundary geometry.
    """

    center: np.ndarray
    radius: float
    thickness: float
    contrast: float
    geometry_type: str = "spherical"

    @property
    def volume(self) -> float:
        """
        Volume of the boundary.

        Physical Meaning:
            Computes the volume of the boundary geometry,
            which determines its influence on the field.

        Returns:
            float: Boundary volume.
        """
        if self.geometry_type == "spherical":
            return (4.0 / 3.0) * np.pi * self.radius**3
        else:
            return 0.0

    @property
    def surface_area(self) -> float:
        """
        Surface area of the boundary.

        Physical Meaning:
            Computes the surface area of the boundary,
            which determines the boundary effects.

        Returns:
            float: Boundary surface area.
        """
        if self.geometry_type == "spherical":
            return 4.0 * np.pi * self.radius**2
        else:
            return 0.0

    @property
    def boundary_strength(self) -> float:
        """
        Boundary strength parameter.

        Physical Meaning:
            Computes the strength of the boundary effects
            based on contrast and geometry.

        Returns:
            float: Boundary strength.
        """
        return self.contrast * self.surface_area


@dataclass
class AdmittanceSpectrum:
    """
    Admittance spectrum specification.

    Physical Meaning:
        Represents the complex admittance spectrum Y(ω)
        over a frequency range, revealing resonance
        frequencies and system response characteristics.

    Mathematical Foundation:
        Represents the admittance spectrum:
        Y(ω) = I(ω)/V(ω) = ∫_Ω a*(x) s(x) dV / ∫_Ω |a(x)|² dV
        where I(ω) is the current and V(ω) is the voltage.

    Attributes:
        frequencies (np.ndarray): Frequency values ω.
        admittances (np.ndarray): Complex admittance values Y(ω).
        magnitude (np.ndarray): Magnitude of admittance |Y(ω)|.
        phase (np.ndarray): Phase of admittance arg(Y(ω)).
    """

    frequencies: np.ndarray
    admittances: np.ndarray
    magnitude: np.ndarray = None
    phase: np.ndarray = None

    def __post_init__(self):
        """Initialize magnitude and phase if not provided."""
        if self.magnitude is None:
            self.magnitude = np.abs(self.admittances)
        if self.phase is None:
            self.phase = np.angle(self.admittances)

    @property
    def max_magnitude(self) -> float:
        """
        Maximum magnitude of admittance.

        Physical Meaning:
            Returns the maximum magnitude of the admittance
            spectrum, indicating the strongest resonance.

        Returns:
            float: Maximum magnitude.
        """
        return np.max(self.magnitude)

    @property
    def resonance_frequencies(self) -> List[float]:
        """
        Resonance frequencies.

        Physical Meaning:
            Identifies frequencies where the admittance
            magnitude is maximum, indicating resonances.

        Returns:
            List[float]: Resonance frequencies.
        """
        # Simplified resonance detection
        # In practice, this would involve proper peak finding
        threshold = 0.8 * self.max_magnitude
        resonance_indices = np.where(self.magnitude > threshold)[0]
        return [self.frequencies[i] for i in resonance_indices]

    @property
    def quality_factor(self) -> float:
        """
        Quality factor of the spectrum.

        Physical Meaning:
            Computes the quality factor Q = ω / (2 * Δω)
            for the admittance spectrum.

        Returns:
            float: Quality factor.
        """
        if len(self.frequencies) < 2:
            return 0.0

        # Simplified quality factor computation
        # In practice, this would involve proper Q-factor analysis
        frequency_range = np.max(self.frequencies) - np.min(self.frequencies)
        return np.mean(self.frequencies) / (2.0 * frequency_range)


@dataclass
class RadialProfile:
    """
    Radial profile specification.

    Physical Meaning:
        Represents the radial profile of field amplitude
        A(r) around a boundary, revealing field distribution
        and concentration patterns.

    Mathematical Foundation:
        Represents the radial profile:
        A(r) = (1/4π) ∫_S(r) |a(x)|² dS
        where S(r) is the spherical surface at radius r.

    Attributes:
        radii (np.ndarray): Radial distances r.
        amplitudes (np.ndarray): Field amplitudes A(r).
        local_maxima (List[Tuple[float, float]]): Local maxima (radius, amplitude).
    """

    radii: np.ndarray
    amplitudes: np.ndarray
    local_maxima: List[Tuple[float, float]] = None

    def __post_init__(self):
        """Initialize local maxima if not provided."""
        if self.local_maxima is None:
            self.local_maxima = self._find_local_maxima()

    def _find_local_maxima(self) -> List[Tuple[float, float]]:
        """
        Find local maxima in radial profile.

        Physical Meaning:
            Identifies local maxima in the radial amplitude profile,
            indicating regions of field concentration.

        Returns:
            List[Tuple[float, float]]: Local maxima (radius, amplitude).
        """
        maxima = []

        for i in range(1, len(self.amplitudes) - 1):
            if (
                self.amplitudes[i] > self.amplitudes[i - 1]
                and self.amplitudes[i] > self.amplitudes[i + 1]
            ):
                maxima.append((self.radii[i], self.amplitudes[i]))

        return maxima

    @property
    def max_amplitude(self) -> float:
        """
        Maximum amplitude in the profile.

        Physical Meaning:
            Returns the maximum amplitude in the radial
            profile, indicating the strongest field concentration.

        Returns:
            float: Maximum amplitude.
        """
        return np.max(self.amplitudes)

    @property
    def peak_radius(self) -> float:
        """
        Radius of maximum amplitude.

        Physical Meaning:
            Returns the radius where the amplitude is maximum,
            indicating the location of strongest field concentration.

        Returns:
            float: Peak radius.
        """
        max_idx = np.argmax(self.amplitudes)
        return self.radii[max_idx]

    @property
    def profile_width(self) -> float:
        """
        Width of the profile.

        Physical Meaning:
            Computes the width of the radial profile,
            indicating the spatial extent of field concentration.

        Returns:
            float: Profile width.
        """
        if len(self.radii) < 2:
            return 0.0

        return np.max(self.radii) - np.min(self.radii)

    @property
    def profile_energy(self) -> float:
        """
        Energy of the profile.

        Physical Meaning:
            Computes the energy associated with the radial
            profile, proportional to the square of amplitudes.

        Returns:
            float: Profile energy.
        """
        return np.trapz(self.amplitudes**2, self.radii)
