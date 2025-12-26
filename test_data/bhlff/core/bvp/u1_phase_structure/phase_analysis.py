"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Phase analysis for U(1)³ phase structure postulate.

This module provides phase structure analysis functionality for
the U(1)³ phase structure postulate implementation.

Physical Meaning:
    Analyzes the three U(1) phase components Θ_a (a=1..3) and their
    statistical properties to characterize the U(1)³ structure.

Mathematical Foundation:
    Extracts and analyzes phase components from complex envelope field
    using spatial frequency analysis and statistical measures.

Example:
    >>> analyzer = PhaseAnalysis(domain)
    >>> phase_structure = analyzer.analyze_phase_structure(envelope)
"""

import numpy as np
from typing import Dict, Any, List

from ...domain.domain import Domain


class PhaseAnalysis:
    """
    Phase structure analysis for U(1)³ postulate.

    Physical Meaning:
        Analyzes the three U(1) phase components Θ_a (a=1..3)
        and their statistical properties to characterize
        the U(1)³ structure.

    Mathematical Foundation:
        Uses spatial FFT to decompose total phase into
        three independent U(1) components and analyzes
        their statistical properties.

    Attributes:
        domain (Domain): Computational domain for analysis.
    """

    def __init__(self, domain: Domain) -> None:
        """
        Initialize phase analysis.

        Physical Meaning:
            Sets up the analyzer with domain information
            for phase structure analysis.

        Args:
            domain (Domain): Computational domain for analysis.
        """
        self.domain = domain

    def analyze_phase_structure(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze U(1)³ phase structure of the field.

        Physical Meaning:
            Extracts and analyzes the three phase components Θ_a (a=1..3)
            from the complex envelope field.

        Mathematical Foundation:
            Envelope A = |A|e^(iΘ) where Θ = Σ_a Θ_a represents
            the total phase with three independent components.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Phase structure analysis.
        """
        # Extract phase from complex envelope
        total_phase = np.angle(envelope)

        # Decompose into three U(1) components
        phase_components = self._decompose_phase_components(total_phase)

        # Analyze phase statistics
        phase_stats = self._compute_phase_statistics(phase_components)

        return {
            "total_phase": total_phase,
            "phase_components": phase_components,
            "phase_statistics": phase_stats,
        }

    def _decompose_phase_components(self, total_phase: np.ndarray) -> List[np.ndarray]:
        """
        Decompose total phase into three U(1) components.

        Physical Meaning:
            Separates total phase into three independent U(1)
            phase components using spatial frequency analysis.

        Args:
            total_phase (np.ndarray): Total phase field.

        Returns:
            List[np.ndarray]: Three phase components.
        """
        # Use spatial FFT to decompose phase
        phase_fft = np.fft.fftn(total_phase)

        # Create three frequency bands
        shape = total_phase.shape
        phase_components = []

        for i in range(3):
            # Create frequency mask for each component
            freq_mask = self._create_frequency_mask(shape, i)

            # Extract component in frequency space
            component_fft = phase_fft * freq_mask

            # Transform back to real space
            component = np.fft.ifftn(component_fft).real
            phase_components.append(component)

        return phase_components

    def _create_frequency_mask(self, shape: tuple, component_idx: int) -> np.ndarray:
        """
        Create frequency mask for phase component extraction.

        Physical Meaning:
            Creates frequency domain mask to separate different
            phase components based on spatial frequencies.

        Args:
            shape (tuple): Field shape.
            component_idx (int): Component index (0, 1, 2).

        Returns:
            np.ndarray: Frequency mask.
        """
        # Create frequency axes for all dimensions
        freq_axes = []
        for i, size in enumerate(shape):
            if i < 3:  # Spatial dimensions
                freq_axis = np.fft.fftfreq(size, self.domain.dx)
            elif i < 6:  # Phase dimensions
                freq_axis = np.fft.fftfreq(size, self.domain.dphi)
            else:  # Temporal dimension
                freq_axis = np.fft.fftfreq(size, self.domain.dt)
            freq_axes.append(freq_axis)

        # Create frequency grid
        freq_grid = np.meshgrid(*freq_axes, indexing="ij")
        freq_magnitude = np.sqrt(sum(f**2 for f in freq_grid))

        # Create frequency bands
        max_freq = np.max(freq_magnitude)
        band_width = max_freq / 3

        # Create mask for this component
        freq_mask = np.zeros_like(freq_magnitude)
        lower_bound = component_idx * band_width
        upper_bound = (component_idx + 1) * band_width

        freq_mask[(freq_magnitude >= lower_bound) & (freq_magnitude < upper_bound)] = (
            1.0
        )

        return freq_mask

    def _compute_phase_statistics(
        self, phase_components: List[np.ndarray]
    ) -> Dict[str, Any]:
        """
        Compute statistics for phase components.

        Physical Meaning:
            Calculates statistical properties of each phase
            component to characterize U(1)³ structure.

        Args:
            phase_components (List[np.ndarray]): Three phase components.

        Returns:
            Dict[str, Any]: Phase statistics.
        """
        phase_stats = {}

        for i, component in enumerate(phase_components):
            # Compute component statistics
            mean_phase = np.mean(component)
            std_phase = np.std(component)
            phase_variance = np.var(component)

            # Check phase wrapping
            phase_range = np.max(component) - np.min(component)
            is_wrapped = phase_range > np.pi

            phase_stats[f"component_{i}"] = {
                "mean_phase": mean_phase,
                "std_phase": std_phase,
                "phase_variance": phase_variance,
                "phase_range": phase_range,
                "is_wrapped": is_wrapped,
            }

        return phase_stats

    def __repr__(self) -> str:
        """String representation of phase analysis."""
        return f"PhaseAnalysis(domain={self.domain})"
