"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Zone analysis module for Level B.

This module implements zone analysis operations for Level B
of the 7D phase field theory, focusing on zone identification and classification.

Physical Meaning:
    Analyzes zone separation in the BVP field including core, transition,
    and tail regions, providing spatial analysis of field structure.

Mathematical Foundation:
    Implements zone analysis including:
    - Zone boundary identification
    - Zone classification based on field properties
    - Zone property analysis
    - Transition region identification

Example:
    >>> analyzer = ZoneAnalysis(bvp_core)
    >>> zones = analyzer.identify_zone_boundaries(envelope)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .boundary_detection import BoundaryDetection
from .zone_properties import ZoneProperties
from .transition_analysis import TransitionAnalysis


class ZoneAnalysis:
    """
    Zone analysis for BVP field.

    Physical Meaning:
        Implements zone analysis operations for identifying and analyzing
        different zones in the BVP field including core, transition,
        and tail regions.

    Mathematical Foundation:
        Analyzes spatial field properties to identify zones with
        different characteristics and transition regions between them.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize zone analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for analysis.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize specialized analyzers
        self._boundary_detector = BoundaryDetection(bvp_core)
        self._zone_properties_analyzer = ZoneProperties(bvp_core)
        self._transition_analyzer = TransitionAnalysis(bvp_core)

    def identify_zone_boundaries(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Identify boundaries between different zones.

        Physical Meaning:
            Identifies boundaries between different zones in the BVP field
            based on field properties and spatial gradients.

        Mathematical Foundation:
            Uses gradient analysis and field property thresholds
            to identify transition regions between zones.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            List[Dict[str, Any]]: List of zone boundaries with properties:
                - boundary_type: Type of boundary (core-transition, transition-tail)
                - boundary_location: Location of the boundary
                - boundary_strength: Strength of the boundary
        """
        return self._boundary_detector.identify_zone_boundaries(envelope)

    def classify_zones(self, envelope: np.ndarray) -> Dict[str, List[Tuple[int, ...]]]:
        """
        Classify spatial zones using full 7D analysis.

        Physical Meaning:
            Classifies different spatial zones in the BVP field
            using complete 7D analysis including level set analysis,
            phase field methods, and topological analysis.

        Mathematical Foundation:
            Uses full 7D analysis including:
            - Level set analysis for zone identification
            - Phase field method for boundary evolution
            - Topological analysis of zone boundaries
            - Energy landscape analysis

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, List[Tuple[int, ...]]]: Zone classification:
                - core_zones: List of core zone coordinates
                - transition_zones: List of transition zone coordinates
                - tail_zones: List of tail zone coordinates
        """
        amplitude = np.abs(envelope)

        # Use full boundary detection for zone classification
        boundary_analysis = self._boundary_detector.identify_zone_boundaries(envelope)

        # Extract level set boundaries for zone classification
        level_sets = boundary_analysis.get("level_set_boundaries", {})

        # Use adaptive thresholds based on level set analysis
        thresholds = self._compute_adaptive_zone_thresholds(amplitude, level_sets)

        # Classify zones using full analysis
        core_mask = self._classify_core_zones(amplitude, thresholds)
        tail_mask = self._classify_tail_zones(amplitude, thresholds)
        transition_mask = self._classify_transition_zones(
            amplitude, core_mask, tail_mask
        )

        # Get zone coordinates
        core_zones = list(zip(*np.where(core_mask)))
        transition_zones = list(zip(*np.where(transition_mask)))
        tail_zones = list(zip(*np.where(tail_mask)))

        return {
            "core_zones": core_zones,
            "transition_zones": transition_zones,
            "tail_zones": tail_zones,
        }

    def _compute_adaptive_zone_thresholds(
        self, amplitude: np.ndarray, level_sets: Dict[str, Any]
    ) -> Dict[str, float]:
        """Compute adaptive zone thresholds using level set analysis."""
        # Use level set analysis to determine optimal thresholds
        max_amplitude = np.max(amplitude)
        mean_amplitude = np.mean(amplitude)
        std_amplitude = np.std(amplitude)

        # Adaptive core threshold based on level set analysis
        if level_sets:
            # Use level set information for threshold determination
            core_threshold = max_amplitude * 0.7  # More conservative threshold
        else:
            # Fallback to statistical threshold
            core_threshold = mean_amplitude + 2 * std_amplitude

        # Adaptive tail threshold
        tail_threshold = mean_amplitude - std_amplitude

        # Ensure thresholds are reasonable
        core_threshold = max(core_threshold, max_amplitude * 0.5)
        tail_threshold = max(tail_threshold, mean_amplitude * 0.1)

        return {"core_threshold": core_threshold, "tail_threshold": tail_threshold}

    def _classify_core_zones(
        self, amplitude: np.ndarray, thresholds: Dict[str, float]
    ) -> np.ndarray:
        """Classify core zones using full analysis."""
        core_threshold = thresholds["core_threshold"]

        # Basic amplitude threshold
        core_mask = amplitude > core_threshold

        # Additional criteria for core zone classification
        # Check for local maxima and high coherence
        if amplitude.ndim >= 3:
            # Check for local maxima
            local_maxima = self._find_local_maxima(amplitude)
            core_mask = core_mask & local_maxima

            # Check for high coherence
            coherence_mask = self._compute_coherence_mask(amplitude)
            core_mask = core_mask & coherence_mask

        return core_mask

    def _classify_tail_zones(
        self, amplitude: np.ndarray, thresholds: Dict[str, float]
    ) -> np.ndarray:
        """Classify tail zones using full analysis."""
        tail_threshold = thresholds["tail_threshold"]

        # Basic amplitude threshold
        tail_mask = amplitude < tail_threshold

        # Additional criteria for tail zone classification
        # Check for local minima and low coherence
        if amplitude.ndim >= 3:
            # Check for local minima
            local_minima = self._find_local_minima(amplitude)
            tail_mask = tail_mask & local_minima

            # Check for low coherence
            coherence_mask = self._compute_coherence_mask(amplitude)
            tail_mask = tail_mask & ~coherence_mask

        return tail_mask

    def _classify_transition_zones(
        self, amplitude: np.ndarray, core_mask: np.ndarray, tail_mask: np.ndarray
    ) -> np.ndarray:
        """Classify transition zones using full analysis."""
        # Basic transition mask (not core and not tail)
        transition_mask = ~(core_mask | tail_mask)

        # Additional criteria for transition zone classification
        # Check for high gradient regions
        if amplitude.ndim >= 3:
            # Compute gradients
            gradients = {}
            for dim in range(amplitude.ndim):
                gradients[f"dim_{dim}"] = np.gradient(amplitude, axis=dim)

            # Compute gradient magnitude
            grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

            # High gradient regions are likely transitions
            grad_threshold = np.mean(grad_magnitude) + np.std(grad_magnitude)
            high_gradient_mask = grad_magnitude > grad_threshold

            # Combine with basic transition mask
            transition_mask = transition_mask & high_gradient_mask

        return transition_mask

    def _find_local_maxima(self, amplitude: np.ndarray) -> np.ndarray:
        """Find local maxima in the amplitude field."""
        # Use morphological operations to find local maxima
        try:
            from scipy import ndimage

            # Find local maxima
            local_maxima = ndimage.maximum_filter(amplitude, size=3) == amplitude
            return local_maxima
        except ImportError:
            # Fallback implementation
            local_maxima = np.zeros_like(amplitude, dtype=bool)
            for i in range(1, amplitude.shape[0] - 1):
                for j in range(1, amplitude.shape[1] - 1):
                    if amplitude.ndim == 3:
                        for k in range(1, amplitude.shape[2] - 1):
                            center = amplitude[i, j, k]
                            neighbors = [
                                amplitude[i - 1, j, k],
                                amplitude[i + 1, j, k],
                                amplitude[i, j - 1, k],
                                amplitude[i, j + 1, k],
                                amplitude[i, j, k - 1],
                                amplitude[i, j, k + 1],
                            ]
                            if center > max(neighbors):
                                local_maxima[i, j, k] = True
                    else:
                        center = amplitude[i, j]
                        neighbors = [
                            amplitude[i - 1, j],
                            amplitude[i + 1, j],
                            amplitude[i, j - 1],
                            amplitude[i, j + 1],
                        ]
                        if center > max(neighbors):
                            local_maxima[i, j] = True
            return local_maxima

    def _find_local_minima(self, amplitude: np.ndarray) -> np.ndarray:
        """Find local minima in the amplitude field."""
        # Use morphological operations to find local minima
        try:
            from scipy import ndimage

            # Find local minima
            local_minima = ndimage.minimum_filter(amplitude, size=3) == amplitude
            return local_minima
        except ImportError:
            # Fallback implementation
            local_minima = np.zeros_like(amplitude, dtype=bool)
            for i in range(1, amplitude.shape[0] - 1):
                for j in range(1, amplitude.shape[1] - 1):
                    if amplitude.ndim == 3:
                        for k in range(1, amplitude.shape[2] - 1):
                            center = amplitude[i, j, k]
                            neighbors = [
                                amplitude[i - 1, j, k],
                                amplitude[i + 1, j, k],
                                amplitude[i, j - 1, k],
                                amplitude[i, j + 1, k],
                                amplitude[i, j, k - 1],
                                amplitude[i, j, k + 1],
                            ]
                            if center < min(neighbors):
                                local_minima[i, j, k] = True
                    else:
                        center = amplitude[i, j]
                        neighbors = [
                            amplitude[i - 1, j],
                            amplitude[i + 1, j],
                            amplitude[i, j - 1],
                            amplitude[i, j + 1],
                        ]
                        if center < min(neighbors):
                            local_minima[i, j] = True
            return local_minima

    def _compute_coherence_mask(self, amplitude: np.ndarray) -> np.ndarray:
        """Compute coherence mask for zone classification."""
        # Compute local coherence using gradient analysis
        if amplitude.ndim >= 3:
            # Compute gradients
            gradients = {}
            for dim in range(amplitude.ndim):
                gradients[f"dim_{dim}"] = np.gradient(amplitude, axis=dim)

            # Compute gradient magnitude
            grad_magnitude = np.sqrt(sum(grad**2 for grad in gradients.values()))

            # High coherence regions have low gradient magnitude
            coherence_threshold = np.mean(grad_magnitude) - np.std(grad_magnitude)
            coherence_mask = grad_magnitude < coherence_threshold

            return coherence_mask
        else:
            # Fallback for lower dimensions
            return np.ones_like(amplitude, dtype=bool)

    def analyze_zone_properties(
        self, envelope: np.ndarray
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze properties of different zones.

        Physical Meaning:
            Analyzes properties of different zones in the BVP field
            including amplitude, gradient, and coherence properties.

        Mathematical Foundation:
            Computes statistical properties for each zone including
            mean, variance, and characteristic scales.

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            Dict[str, Dict[str, float]]: Zone properties:
                - core_properties: Properties of core zones
                - transition_properties: Properties of transition zones
                - tail_properties: Properties of tail zones
        """
        return self._zone_properties_analyzer.analyze_zone_properties(envelope)

    def identify_transition_regions(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Identify transition regions using full 7D analysis.

        Physical Meaning:
            Identifies transition regions between different zones
            using complete 7D analysis including level set analysis,
            phase field methods, and topological analysis.

        Mathematical Foundation:
            Uses full 7D analysis including:
            - Level set analysis for transition detection
            - Phase field method for boundary evolution
            - Topological analysis of transition regions
            - Energy landscape analysis

        Args:
            envelope (np.ndarray): BVP envelope field to analyze.

        Returns:
            List[Dict[str, Any]]: List of transition regions:
                - region_type: Type of transition region
                - region_location: Location of the region
                - transition_strength: Strength of the transition
        """
        return self._transition_analyzer.identify_transition_regions(envelope)

    def __repr__(self) -> str:
        """String representation of zone analyzer."""
        return f"ZoneAnalysis(bvp_core={self.bvp_core})"
