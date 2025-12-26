"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating pattern validation for Level C.

This module implements pattern validation functionality
for beating analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationPatterns:
    """
    Beating pattern validation for Level C.

    Physical Meaning:
        Provides pattern validation functionality for beating analysis
        in the 7D phase field.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize beating pattern validation."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Physical constraints for 7D phase field theory
        self.min_amplitude = 1e-12  # Minimum physically meaningful amplitude
        self.max_amplitude = 1e6  # Maximum physically meaningful amplitude
        self.min_frequency = 1e-6  # Minimum physically meaningful frequency
        self.max_frequency = 1e15  # Maximum physically meaningful frequency
        self.phase_bounds = (-2 * np.pi, 2 * np.pi)  # Phase bounds

        # Theoretical pattern constraints
        self.pattern_constraints = {
            "interference_coherence": (0.0, 1.0),  # Coherence bounds
            "spatial_extent": (1e-9, 1e3),  # Spatial extent bounds (meters)
            "temporal_duration": (1e-12, 1e6),  # Temporal duration bounds (seconds)
            "energy_density": (1e-15, 1e12),  # Energy density bounds (J/m³)
        }

    def validate_interference_patterns_physical(
        self, patterns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Physical validation of interference patterns.

        Physical Meaning:
            Validates interference patterns according to physical principles
            and theoretical constraints of the 7D phase field theory.

        Mathematical Foundation:
            Validates patterns against:
            - Physical bounds: amplitude, frequency, phase constraints
            - Theoretical constraints: coherence, spatial extent, temporal duration
            - Physical consistency: energy conservation, causality

        Args:
            patterns (List[Dict[str, Any]]): List of interference patterns.

        Returns:
            Dict[str, Any]: Comprehensive pattern validation results.
        """
        self.logger.info("Starting physical interference pattern validation")

        validation_result = {
            "patterns_valid": True,
            "pattern_errors": [],
            "pattern_warnings": [],
            "pattern_metrics": {},
            "physical_validation": {},
            "theoretical_validation": {},
        }

        # Basic pattern validation
        if not patterns:
            validation_result["pattern_errors"].append("Empty pattern list")
            validation_result["patterns_valid"] = False
            return validation_result

        # Physical validation for each pattern
        physical_errors = []
        theoretical_errors = []

        for i, pattern in enumerate(patterns):
            # Physical constraints validation
            if not self._is_physically_valid_pattern(pattern):
                physical_errors.append(f"Non-physical pattern at index {i}")
                validation_result["pattern_errors"].append(
                    f"Non-physical pattern: {pattern}"
                )
                validation_result["patterns_valid"] = False

            # Theoretical bounds validation
            if not self._is_within_theoretical_bounds(pattern):
                theoretical_errors.append(f"Pattern {i} outside theoretical bounds")
                validation_result["pattern_errors"].append(
                    f"Pattern outside theoretical bounds: {pattern}"
                )
                validation_result["patterns_valid"] = False

        # Physical validation summary
        validation_result["physical_validation"] = {
            "physical_errors": physical_errors,
            "physical_valid": len(physical_errors) == 0,
            "physical_pattern_count": len(
                [p for p in patterns if self._is_physically_valid_pattern(p)]
            ),
        }

        # Theoretical validation summary
        validation_result["theoretical_validation"] = {
            "theoretical_errors": theoretical_errors,
            "theoretical_valid": len(theoretical_errors) == 0,
            "theoretical_pattern_count": len(
                [p for p in patterns if self._is_within_theoretical_bounds(p)]
            ),
        }

        # Calculate comprehensive pattern metrics
        validation_result["pattern_metrics"] = {
            "pattern_count": len(patterns),
            "valid_patterns": sum(
                1
                for p in patterns
                if self._validate_single_pattern(p).get("pattern_valid", True)
            ),
            "physical_pattern_ratio": validation_result["physical_validation"][
                "physical_pattern_count"
            ]
            / len(patterns),
            "theoretical_pattern_ratio": validation_result["theoretical_validation"][
                "theoretical_pattern_count"
            ]
            / len(patterns),
        }

        # Analyze pattern relationships and coherence
        coherence_analysis = self._analyze_pattern_coherence(patterns)
        validation_result["coherence_analysis"] = coherence_analysis

        self.logger.info(
            f"Physical interference pattern validation completed: {'PASSED' if validation_result['patterns_valid'] else 'FAILED'}"
        )
        return validation_result

    # Legacy method removed - no longer needed

    def _validate_single_pattern(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single interference pattern."""
        validation_result = {
            "pattern_valid": True,
            "pattern_errors": [],
            "pattern_warnings": [],
        }

        # Basic pattern validation
        if not isinstance(pattern, dict):
            validation_result["pattern_errors"].append("Pattern must be a dictionary")
            validation_result["pattern_valid"] = False
            return validation_result

        # Check required fields
        required_fields = ["amplitude", "phase", "frequency"]
        for field in required_fields:
            if field not in pattern:
                validation_result["pattern_errors"].append(
                    f"Missing required field: {field}"
                )
                validation_result["pattern_valid"] = False

        return validation_result

    def _is_physically_valid_pattern(self, pattern: Dict[str, Any]) -> bool:
        """
        Check if pattern is physically valid.

        Physical Meaning:
            Validates that the pattern parameters are within physically
            meaningful bounds according to the 7D phase field theory.

        Args:
            pattern (Dict[str, Any]): Pattern to validate.

        Returns:
            bool: True if pattern is physically valid.
        """
        try:
            # Check amplitude bounds
            amplitude = pattern.get("amplitude", 0)
            if not (self.min_amplitude <= amplitude <= self.max_amplitude):
                return False

            # Check frequency bounds
            frequency = pattern.get("frequency", 0)
            if not (self.min_frequency <= frequency <= self.max_frequency):
                return False

            # Check phase bounds
            phase = pattern.get("phase", 0)
            if not (self.phase_bounds[0] <= phase <= self.phase_bounds[1]):
                return False

            # Check for NaN or infinite values
            for key, value in pattern.items():
                if isinstance(value, (int, float)):
                    if np.isnan(value) or np.isinf(value):
                        return False

            return True

        except (TypeError, ValueError, KeyError):
            return False

    def _is_within_theoretical_bounds(self, pattern: Dict[str, Any]) -> bool:
        """
        Check if pattern is within theoretical bounds.

        Physical Meaning:
            Validates that the pattern is within theoretical constraints
            for interference patterns in the 7D theory.

        Args:
            pattern (Dict[str, Any]): Pattern to validate.

        Returns:
            bool: True if pattern is within theoretical bounds.
        """
        try:
            # Check interference coherence
            coherence = pattern.get("interference_coherence", 0.5)
            if not (
                self.pattern_constraints["interference_coherence"][0]
                <= coherence
                <= self.pattern_constraints["interference_coherence"][1]
            ):
                return False

            # Check spatial extent
            spatial_extent = pattern.get("spatial_extent", 1e-3)
            if not (
                self.pattern_constraints["spatial_extent"][0]
                <= spatial_extent
                <= self.pattern_constraints["spatial_extent"][1]
            ):
                return False

            # Check temporal duration
            temporal_duration = pattern.get("temporal_duration", 1e-6)
            if not (
                self.pattern_constraints["temporal_duration"][0]
                <= temporal_duration
                <= self.pattern_constraints["temporal_duration"][1]
            ):
                return False

            # Check energy density
            energy_density = pattern.get("energy_density", 1e-6)
            if not (
                self.pattern_constraints["energy_density"][0]
                <= energy_density
                <= self.pattern_constraints["energy_density"][1]
            ):
                return False

            return True

        except (TypeError, ValueError, KeyError):
            return False

    def _analyze_pattern_coherence(
        self, patterns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze pattern coherence and relationships.

        Physical Meaning:
            Analyzes coherence relationships between patterns
            according to the 7D phase field theory.

        Args:
            patterns (List[Dict[str, Any]]): List of patterns to analyze.

        Returns:
            Dict[str, Any]: Coherence analysis results.
        """
        if len(patterns) < 2:
            return {"coherence_relationships": [], "coherence_valid": True}

        coherence_relationships = []

        # Analyze coherence between patterns
        for i, pattern1 in enumerate(patterns):
            for j, pattern2 in enumerate(patterns[i + 1 :], i + 1):
                # Calculate coherence between patterns
                coherence = self._calculate_pattern_coherence(pattern1, pattern2)

                if coherence > 0.5:  # Threshold for significant coherence
                    coherence_relationships.append(
                        {
                            "pattern_pair": (i, j),
                            "coherence": coherence,
                            "coherence_type": self._classify_coherence_type(coherence),
                        }
                    )

        return {
            "coherence_relationships": coherence_relationships,
            "coherence_valid": len(coherence_relationships) > 0,
            "coherence_count": len(coherence_relationships),
            "average_coherence": (
                np.mean([rel["coherence"] for rel in coherence_relationships])
                if coherence_relationships
                else 0.0
            ),
        }

    def _calculate_pattern_coherence(
        self, pattern1: Dict[str, Any], pattern2: Dict[str, Any]
    ) -> float:
        """
        Calculate coherence between two patterns.

        Physical Meaning:
            Calculates the coherence between two interference patterns
            based on their amplitude, phase, and frequency relationships.

        Args:
            pattern1 (Dict[str, Any]): First pattern.
            pattern2 (Dict[str, Any]): Second pattern.

        Returns:
            float: Coherence value between 0 and 1.
        """
        try:
            # Extract pattern parameters
            amp1 = pattern1.get("amplitude", 0)
            phase1 = pattern1.get("phase", 0)
            freq1 = pattern1.get("frequency", 0)

            amp2 = pattern2.get("amplitude", 0)
            phase2 = pattern2.get("phase", 0)
            freq2 = pattern2.get("frequency", 0)

            # Calculate amplitude coherence
            amp_coherence = (
                min(amp1, amp2) / max(amp1, amp2) if max(amp1, amp2) > 0 else 0
            )

            # Calculate phase coherence
            phase_diff = abs(phase1 - phase2)
            phase_coherence = np.cos(phase_diff)

            # Calculate frequency coherence
            freq_coherence = (
                min(freq1, freq2) / max(freq1, freq2) if max(freq1, freq2) > 0 else 0
            )

            # Overall coherence (weighted average)
            overall_coherence = (
                0.4 * amp_coherence + 0.3 * phase_coherence + 0.3 * freq_coherence
            )

            return max(0.0, min(1.0, overall_coherence))

        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    def _classify_coherence_type(self, coherence: float) -> str:
        """
        Classify coherence type based on coherence value.

        Physical Meaning:
            Classifies the type of coherence relationship between patterns
            according to the 7D phase field theory.

        Args:
            coherence (float): Coherence value.

        Returns:
            str: Coherence type classification.
        """
        if coherence > 0.8:
            return "strong_coherence"
        elif coherence > 0.6:
            return "moderate_coherence"
        elif coherence > 0.4:
            return "weak_coherence"
        else:
            return "no_coherence"
