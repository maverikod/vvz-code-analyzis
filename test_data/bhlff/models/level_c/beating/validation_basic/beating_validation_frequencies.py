"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating frequency validation for Level C.

This module implements frequency validation functionality
for beating analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore


class BeatingValidationFrequencies:
    """
    Beating frequency validation for Level C.

    Physical Meaning:
        Provides frequency validation functionality for beating analysis
        in the 7D phase field.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize beating frequency validation."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.frequency_tolerance = 1e-6

        # Physical constraints for 7D phase field theory
        self.min_physical_frequency = 1e-6  # Minimum physically meaningful frequency
        self.max_physical_frequency = 1e15  # Maximum physically meaningful frequency
        self.theoretical_frequency_bounds = {
            "spatial": (1e-3, 1e12),  # Spatial frequency bounds
            "temporal": (1e-6, 1e15),  # Temporal frequency bounds
            "phase": (1e-9, 1e18),  # Phase frequency bounds
        }

    def validate_beating_frequencies_physical(
        self, frequencies: List[float]
    ) -> Dict[str, Any]:
        """
        Physical validation of beating frequencies.

        Physical Meaning:
            Validates beating frequencies according to physical principles
            and theoretical constraints of the 7D phase field theory.

        Mathematical Foundation:
            Validates frequencies against:
            - Physical bounds: f_min ≤ f ≤ f_max
            - Theoretical constraints: spatial, temporal, and phase frequency bounds
            - Physical consistency: frequency relationships and harmonics

        Args:
            frequencies (List[float]): List of beating frequencies.

        Returns:
            Dict[str, Any]: Comprehensive frequency validation results.
        """
        self.logger.info("Starting physical beating frequency validation")

        validation_result = {
            "frequencies_valid": True,
            "frequency_errors": [],
            "frequency_warnings": [],
            "frequency_metrics": {},
            "physical_validation": {},
            "theoretical_validation": {},
        }

        # Basic frequency validation
        if not frequencies:
            validation_result["frequency_errors"].append("Empty frequency list")
            validation_result["frequencies_valid"] = False
            return validation_result

        # Physical validation for each frequency
        physical_errors = []
        theoretical_errors = []

        for i, freq in enumerate(frequencies):
            # Type and basic validation
            if not isinstance(freq, (int, float)):
                validation_result["frequency_errors"].append(
                    f"Invalid frequency type at index {i}"
                )
                validation_result["frequencies_valid"] = False
                continue

            if freq <= 0:
                validation_result["frequency_errors"].append(
                    f"Non-positive frequency at index {i}"
                )
                validation_result["frequencies_valid"] = False
                continue

            # Physical constraints validation
            if not self._is_physically_valid_frequency(freq):
                physical_errors.append(f"Non-physical frequency {freq} at index {i}")
                validation_result["frequency_errors"].append(
                    f"Non-physical frequency: {freq}"
                )
                validation_result["frequencies_valid"] = False

            # Theoretical bounds validation
            if not self._is_within_theoretical_bounds(freq):
                theoretical_errors.append(
                    f"Frequency {freq} outside theoretical bounds at index {i}"
                )
                validation_result["frequency_errors"].append(
                    f"Frequency outside theoretical bounds: {freq}"
                )
                validation_result["frequencies_valid"] = False

        # Physical validation summary
        validation_result["physical_validation"] = {
            "physical_errors": physical_errors,
            "physical_valid": len(physical_errors) == 0,
            "physical_frequency_count": len(
                [f for f in frequencies if self._is_physically_valid_frequency(f)]
            ),
        }

        # Theoretical validation summary
        validation_result["theoretical_validation"] = {
            "theoretical_errors": theoretical_errors,
            "theoretical_valid": len(theoretical_errors) == 0,
            "theoretical_frequency_count": len(
                [f for f in frequencies if self._is_within_theoretical_bounds(f)]
            ),
        }

        # Calculate comprehensive frequency metrics
        if frequencies:
            validation_result["frequency_metrics"] = {
                "mean_frequency": float(np.mean(frequencies)),
                "std_frequency": float(np.std(frequencies)),
                "min_frequency": float(np.min(frequencies)),
                "max_frequency": float(np.max(frequencies)),
                "frequency_count": len(frequencies),
                "physical_frequency_ratio": validation_result["physical_validation"][
                    "physical_frequency_count"
                ]
                / len(frequencies),
                "theoretical_frequency_ratio": validation_result[
                    "theoretical_validation"
                ]["theoretical_frequency_count"]
                / len(frequencies),
            }

        # Check frequency relationships and harmonics
        harmonic_analysis = self._analyze_frequency_harmonics(frequencies)
        validation_result["harmonic_analysis"] = harmonic_analysis

        self.logger.info(
            f"Physical beating frequency validation completed: {'PASSED' if validation_result['frequencies_valid'] else 'FAILED'}"
        )
        return validation_result

    def _is_physically_valid_frequency(self, frequency: float) -> bool:
        """
        Check if frequency is physically valid.

        Physical Meaning:
            Validates that the frequency is within physically meaningful bounds
            according to the 7D phase field theory.

        Args:
            frequency (float): Frequency to validate.

        Returns:
            bool: True if frequency is physically valid.
        """
        return (
            self.min_physical_frequency <= frequency <= self.max_physical_frequency
            and not np.isnan(frequency)
            and not np.isinf(frequency)
        )

    def _is_within_theoretical_bounds(self, frequency: float) -> bool:
        """
        Check if frequency is within theoretical bounds.

        Physical Meaning:
            Validates that the frequency is within theoretical constraints
            for spatial, temporal, and phase frequencies in the 7D theory.

        Args:
            frequency (float): Frequency to validate.

        Returns:
            bool: True if frequency is within theoretical bounds.
        """
        # Check against all theoretical bounds
        for bound_type, (
            min_freq,
            max_freq,
        ) in self.theoretical_frequency_bounds.items():
            if min_freq <= frequency <= max_freq:
                return True
        return False

    def _analyze_frequency_harmonics(self, frequencies: List[float]) -> Dict[str, Any]:
        """
        Analyze frequency harmonics and relationships.

        Physical Meaning:
            Analyzes harmonic relationships between frequencies
            according to the 7D phase field theory.

        Args:
            frequencies (List[float]): List of frequencies to analyze.

        Returns:
            Dict[str, Any]: Harmonic analysis results.
        """
        if len(frequencies) < 2:
            return {"harmonic_relationships": [], "harmonic_valid": True}

        harmonic_relationships = []
        tolerance = self.frequency_tolerance

        # Check for harmonic relationships
        for i, freq1 in enumerate(frequencies):
            for j, freq2 in enumerate(frequencies[i + 1 :], i + 1):
                # Check if frequencies are harmonics
                ratio = freq1 / freq2 if freq2 != 0 else float("inf")
                inverse_ratio = freq2 / freq1 if freq1 != 0 else float("inf")

                # Check for integer harmonic relationships
                for harmonic in [2, 3, 4, 5]:
                    if (
                        abs(ratio - harmonic) < tolerance
                        or abs(inverse_ratio - harmonic) < tolerance
                    ):
                        harmonic_relationships.append(
                            {
                                "frequency_pair": (freq1, freq2),
                                "harmonic_order": harmonic,
                                "ratio": ratio,
                            }
                        )

        return {
            "harmonic_relationships": harmonic_relationships,
            "harmonic_valid": len(harmonic_relationships) > 0,
            "harmonic_count": len(harmonic_relationships),
        }

    def validate_beating_frequencies(self, frequencies: List[float]) -> Dict[str, Any]:
        """
        Legacy method for backward compatibility.

        Physical Meaning:
            Basic frequency validation for backward compatibility.
            For comprehensive validation, use validate_beating_frequencies_physical.

        Args:
            frequencies (List[float]): List of beating frequencies.

        Returns:
            Dict[str, Any]: Basic frequency validation results.
        """
        self.logger.info("Starting basic beating frequency validation (legacy)")

        validation_result = {
            "frequencies_valid": True,
            "frequency_errors": [],
            "frequency_warnings": [],
            "frequency_metrics": {},
        }

        # Basic frequency validation
        if not frequencies:
            validation_result["frequency_errors"].append("Empty frequency list")
            validation_result["frequencies_valid"] = False
            return validation_result

        # Validate each frequency
        for i, freq in enumerate(frequencies):
            if not isinstance(freq, (int, float)):
                validation_result["frequency_errors"].append(
                    f"Invalid frequency type at index {i}"
                )
                validation_result["frequencies_valid"] = False
            elif freq <= 0:
                validation_result["frequency_errors"].append(
                    f"Non-positive frequency at index {i}"
                )
                validation_result["frequencies_valid"] = False

        # Calculate frequency metrics
        if frequencies:
            validation_result["frequency_metrics"] = {
                "mean_frequency": float(np.mean(frequencies)),
                "std_frequency": float(np.std(frequencies)),
                "min_frequency": float(np.min(frequencies)),
                "max_frequency": float(np.max(frequencies)),
                "frequency_count": len(frequencies),
            }

        self.logger.info(
            f"Basic beating frequency validation completed: {'PASSED' if validation_result['frequencies_valid'] else 'FAILED'}"
        )
        return validation_result
