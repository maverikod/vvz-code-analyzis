"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multimode superposition analysis for Level D models.

This module implements multimode superposition analysis, including
frame stability analysis using Jaccard index and frequency stability
analysis for testing the robustness of phase field topology.

Physical Meaning:
    Multimode superposition represents the complex structure of the
    unified phase field through the superposition of different
    frequency components, where each mode corresponds to different
    physical excitations or envelope functions.

Mathematical Foundation:
    - Multimode field: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
    - Frame stability: Jaccard index between frame maps before/after
    - Frequency stability: Analysis of spectral peak shifts

Example:
    >>> from bhlff.models.level_d.superposition import MultiModeModel
    >>> model = MultiModeModel(domain, parameters)
    >>> results = model.analyze_frame_stability(field_before, field_after)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from bhlff.models.base.abstract_models import AbstractLevelModels


class MultiModeModel:
    """
    Multi-mode superposition model for frame stability analysis.

    Physical Meaning:
        Represents the superposition of multiple frequency modes
        on a stable frame structure, testing the robustness of
        the phase field topology under mode additions.

    Mathematical Foundation:
        Implements the multi-mode superposition:
        a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
        and analyzes frame stability using Jaccard index.

    Attributes:
        domain (Domain): Computational domain
        parameters (Dict): Model parameters
        _frame_extractor (FrameExtractor): Tool for extracting frame structure
        _stability_analyzer (StabilityAnalyzer): Tool for stability analysis
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """
        Initialize multi-mode model.

        Physical Meaning:
            Sets up the multi-mode superposition model with
            the base field and mode parameters for testing
            frame stability.

        Args:
            domain (Domain): Computational domain
            parameters (Dict): Parameters for mode addition
        """
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize analysis tools
        self._frame_extractor = FrameExtractor(domain)
        self._stability_analyzer = StabilityAnalyzer(domain)

        self.logger.info("Multi-mode model initialized")

    def create_multi_mode_field(
        self, base_field: np.ndarray, modes: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Create multi-mode field from base field and additional modes.

        Physical Meaning:
            Constructs a multi-mode phase field by superposing
            different frequency components, representing the
            complex structure of the unified field.

        Mathematical Foundation:
            Multi-mode field: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
            where A_m are mode amplitudes, φ_m are spatial modes,
            and ω_m are mode frequencies.

        Args:
            base_field (np.ndarray): Base field structure
            modes (List[Dict]): List of mode parameters with keys:
                - frequency: Mode frequency
                - amplitude: Mode amplitude
                - phase: Mode phase
                - spatial_mode: Spatial mode type

        Returns:
            np.ndarray: Multi-mode field
        """
        self.logger.info(f"Creating multi-mode field with {len(modes)} modes")

        # Start with base field
        multi_mode_field = base_field.copy()

        # Add each mode
        for mode in modes:
            frequency = mode.get("frequency", 1.0)
            amplitude = mode.get("amplitude", 1.0)
            phase = mode.get("phase", 0.0)
            spatial_mode = mode.get("spatial_mode", "bvp_envelope_modulation")

            # Create mode field
            mode_field = self._create_single_mode_field(
                frequency, amplitude, phase, spatial_mode
            )

            # Add to multi-mode field
            multi_mode_field += mode_field

        self.logger.info("Multi-mode field created successfully")
        return multi_mode_field

    def analyze_frame_stability(
        self, before: np.ndarray, after: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze frame stability using Jaccard index.

        Physical Meaning:
            Computes the Jaccard index between frame structures
            before and after mode addition to quantify stability.

        Mathematical Foundation:
            Jaccard index: J(A,B) = |A ∩ B| / |A ∪ B|
            where A and B are frame maps before and after mode addition.

        Args:
            before (np.ndarray): Frame before mode addition
            after (np.ndarray): Frame after mode addition

        Returns:
            Dict: Stability analysis results including:
                - jaccard_index: Jaccard index (0-1, higher is more stable)
                - frame_overlap: Overlap between frames
                - stability_metrics: Additional stability metrics
        """
        self.logger.info("Analyzing frame stability")

        # Extract frame structures
        frame_before = self._frame_extractor.extract_frame(before)
        frame_after = self._frame_extractor.extract_frame(after)

        # Compute Jaccard index
        jaccard_index = self.compute_jaccard_index(frame_before, frame_after)

        # Compute additional stability metrics
        stability_metrics = self._stability_analyzer.compute_stability_metrics(
            frame_before, frame_after
        )

        # Check if stability criteria are met
        jaccard_threshold = self.parameters.get("jaccard_threshold", 0.8)
        passed = jaccard_index >= jaccard_threshold

        results = {
            "jaccard_index": float(jaccard_index),
            "frame_before": frame_before,
            "frame_after": frame_after,
            "stability_metrics": stability_metrics,
            "passed": passed,
            "threshold": jaccard_threshold,
        }

        self.logger.info(
            f"Frame stability analysis completed: Jaccard index = {jaccard_index:.3f}"
        )
        return results

    def compute_jaccard_index(self, map1: np.ndarray, map2: np.ndarray) -> float:
        """
        Compute Jaccard index for frame comparison.

        Physical Meaning:
            Measures the similarity between two frame maps
            using the Jaccard index, which quantifies the
            overlap of non-zero regions.

        Mathematical Foundation:
            Jaccard index: J(A,B) = |A ∩ B| / |A ∪ B|
            where A and B are binary frame maps.

        Args:
            map1 (np.ndarray): First frame map
            map2 (np.ndarray): Second frame map

        Returns:
            float: Jaccard index (0-1)
        """
        # Convert to binary maps
        binary_map1 = (map1 > 0).astype(int)
        binary_map2 = (map2 > 0).astype(int)

        # Compute intersection and union
        intersection = np.sum(binary_map1 * binary_map2)
        union = np.sum(np.maximum(binary_map1, binary_map2))

        # Avoid division by zero
        if union == 0:
            return 0.0

        jaccard_index = intersection / union
        return float(jaccard_index)

    def _create_single_mode_field(
        self, frequency: float, amplitude: float, phase: float, spatial_mode: str
    ) -> np.ndarray:
        """
        Create single mode field.

        Physical Meaning:
            Creates a single frequency mode with specified
            amplitude, phase, and spatial structure.

        Args:
            frequency (float): Mode frequency
            amplitude (float): Mode amplitude
            phase (float): Mode phase
            spatial_mode (str): Spatial mode type

        Returns:
            np.ndarray: Single mode field
        """
        # Create coordinate grids
        coords = self._create_coordinate_grids()

        # Create spatial mode
        if spatial_mode == "bvp_envelope_modulation":
            spatial_field = self._create_bvp_envelope_modulation(coords, frequency)
        else:
            spatial_field = self._create_default_spatial_mode(coords, frequency)

        # Apply amplitude and phase
        mode_field = amplitude * np.exp(1j * phase) * spatial_field

        return mode_field.real

    def _create_coordinate_grids(self) -> List[np.ndarray]:
        """Create coordinate grids for the domain."""
        coords = []
        for i, size in enumerate(self.domain.shape):
            coord = np.linspace(0, self.domain.L, size)
            coords.append(coord)
        return coords

    def _create_bvp_envelope_modulation(
        self, coords: List[np.ndarray], frequency: float
    ) -> np.ndarray:
        """Create BVP envelope modulation spatial mode."""
        # Create simple spatial field for 7D
        spatial_field = np.ones(self.domain.shape)
        return spatial_field

    def _create_default_spatial_mode(
        self, coords: List[np.ndarray], frequency: float
    ) -> np.ndarray:
        """Create default spatial mode."""
        # Create simple spatial field for 7D
        spatial_field = np.ones(self.domain.shape)
        return spatial_field


class SuperpositionAnalyzer:
    """
    Analyzer for multimode superposition patterns.

    Physical Meaning:
        Analyzes the superposition of multiple frequency modes
        in the phase field, identifying dominant modes and
        their interactions.

    Mathematical Foundation:
        Uses FFT analysis to decompose the field into
        frequency components and analyzes their superposition.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize superposition analyzer."""
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

    def analyze_superposition(
        self, field: np.ndarray, threshold: float = 0.1
    ) -> Dict[str, Any]:
        """
        Analyze multimode superposition patterns.

        Physical Meaning:
            Performs FFT analysis to decompose the field into
            its constituent modes and identifies dominant frequency
            components and their amplitudes.

        Mathematical Foundation:
            Uses FFT decomposition: a(x) = Σ A_k e^(ik·x)
            where A_k are the mode amplitudes and k are wave vectors.

        Args:
            field (np.ndarray): Input field
            threshold (float): Threshold for dominant mode detection

        Returns:
            Dict: Superposition analysis results
        """
        self.logger.info("Analyzing multimode superposition")

        # Perform FFT analysis
        fft_field = np.fft.fftn(field)
        power_spectrum = np.abs(fft_field) ** 2

        # Find dominant modes
        max_power = np.max(power_spectrum)
        dominant_mask = power_spectrum > threshold * max_power
        dominant_modes = np.where(dominant_mask)

        # Analyze mode characteristics
        mode_count = len(dominant_modes[0])
        dominant_frequencies = self._extract_dominant_frequencies(
            fft_field, dominant_mask
        )
        mode_amplitudes = self._extract_mode_amplitudes(fft_field, dominant_mask)
        mode_phases = self._extract_mode_phases(fft_field, dominant_mask)

        # Compute superposition quality
        superposition_quality = self._compute_superposition_quality(
            power_spectrum, dominant_mask
        )

        results = {
            "mode_count": mode_count,
            "dominant_frequencies": dominant_frequencies,
            "mode_amplitudes": mode_amplitudes,
            "mode_phases": mode_phases,
            "superposition_quality": superposition_quality,
            "threshold": threshold,
        }

        self.logger.info(
            f"Superposition analysis completed: {mode_count} dominant modes found"
        )
        return results

    def analyze_mode_superposition(
        self, field: np.ndarray, new_modes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze mode superposition on the frame.

        Physical Meaning:
            Tests the stability of the phase field frame when
            adding new modes, ensuring topological robustness.

        Args:
            field (np.ndarray): Base field
            new_modes (List[Dict]): New modes to add

        Returns:
            Dict: Analysis results
        """
        # Create multi-mode model
        multimode_model = MultiModeModel(self.domain, self.parameters)

        # Create multi-mode field
        multi_mode_field = multimode_model.create_multi_mode_field(field, new_modes)

        # Analyze frame stability
        stability_results = multimode_model.analyze_frame_stability(
            field, multi_mode_field
        )

        return stability_results

    def _extract_dominant_frequencies(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract dominant frequencies from FFT field."""
        frequencies = []
        for i in range(len(fft_field.shape)):
            freq_coords = np.where(mask)[i]
            if len(freq_coords) > 0:
                frequencies.extend(freq_coords.tolist())
        return frequencies

    def _extract_mode_amplitudes(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract mode amplitudes from FFT field."""
        amplitudes = np.abs(fft_field[mask])
        return amplitudes.tolist()

    def _extract_mode_phases(
        self, fft_field: np.ndarray, mask: np.ndarray
    ) -> List[float]:
        """Extract mode phases from FFT field."""
        phases = np.angle(fft_field[mask])
        return phases.tolist()

    def _compute_superposition_quality(
        self, power_spectrum: np.ndarray, mask: np.ndarray
    ) -> float:
        """Compute superposition quality metric."""
        total_power = np.sum(power_spectrum)
        dominant_power = np.sum(power_spectrum[mask])
        quality = dominant_power / total_power if total_power > 0 else 0.0
        return float(quality)


class FrameExtractor:
    """Extract frame structure from field."""

    def __init__(self, domain: "Domain"):
        """Initialize frame extractor."""
        self.domain = domain

    def extract_frame(self, field: np.ndarray) -> np.ndarray:
        """Extract frame structure from field."""
        # Use hot zones method to extract frame
        threshold = np.percentile(np.abs(field), 80)
        frame = (np.abs(field) > threshold).astype(float)
        return frame


class StabilityAnalyzer:
    """Analyze frame stability metrics."""

    def __init__(self, domain: "Domain"):
        """Initialize stability analyzer."""
        self.domain = domain

    def compute_stability_metrics(
        self, frame_before: np.ndarray, frame_after: np.ndarray
    ) -> Dict[str, Any]:
        """Compute additional stability metrics."""
        # Compute frame overlap
        overlap = np.sum(frame_before * frame_after)

        # Compute frame changes
        changes = np.sum(np.abs(frame_after - frame_before))

        # Compute stability ratio
        stability_ratio = (
            overlap / (overlap + changes) if (overlap + changes) > 0 else 0.0
        )

        return {
            "overlap": float(overlap),
            "changes": float(changes),
            "stability_ratio": float(stability_ratio),
        }
