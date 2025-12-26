"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core beating validation for Level C.

This module implements the core validation functionality
for beating analysis in the 7D phase field.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore
from .beating_validation_statistics import BeatingValidationStatistics
from .beating_validation_comparison import BeatingValidationComparison


class BeatingValidationCore:
    """
    Core beating validation for Level C analysis.

    Physical Meaning:
        Provides core validation functionality for beating analysis,
        coordinating specialized validation modules.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating validation analyzer.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Validation parameters
        self.statistical_significance = 0.05
        self.comparison_tolerance = 1e-3
        self.optimization_tolerance = 1e-6
        self.max_optimization_iterations = 100

        # Initialize specialized modules
        self.statistics = BeatingValidationStatistics(bvp_core)
        self.comparison = BeatingValidationComparison(bvp_core)
        self.consistency = BeatingValidationConsistency(bvp_core)

    def validate_with_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate beating analysis results with statistical analysis.

        Physical Meaning:
            Performs comprehensive statistical validation of beating
            analysis results to ensure their reliability and accuracy.

        Args:
            results (Dict[str, Any]): Beating analysis results to validate.

        Returns:
            Dict[str, Any]: Statistical validation results.
        """
        self.logger.info("Starting statistical validation")

        validation_results = {}

        # Validate beating frequencies
        if "beating_frequencies" in results:
            freq_validation = self._validate_beating_frequencies(
                results["beating_frequencies"]
            )
            validation_results["frequency_validation"] = freq_validation

        # Validate interference patterns
        if "interference_patterns" in results:
            pattern_validation = self._validate_interference_patterns(
                results["interference_patterns"]
            )
            validation_results["pattern_validation"] = pattern_validation

        # Validate mode coupling
        if "mode_coupling" in results:
            coupling_validation = self._validate_mode_coupling(results["mode_coupling"])
            validation_results["coupling_validation"] = coupling_validation

        # Compute overall statistical validation
        overall_validation = self.statistics.compute_overall_statistical_validation(
            validation_results
        )
        validation_results["overall_validation"] = overall_validation

        self.logger.info("Statistical validation completed")
        return validation_results

    def compare_analysis_results(
        self, results1: Dict[str, Any], results2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare two sets of beating analysis results.

        Physical Meaning:
            Compares two sets of beating analysis results to
            identify differences, similarities, and consistency.

        Args:
            results1 (Dict[str, Any]): First set of analysis results.
            results2 (Dict[str, Any]): Second set of analysis results.

        Returns:
            Dict[str, Any]: Comparison results.
        """
        self.logger.info("Starting analysis results comparison")

        comparison_results = self.comparison.compare_results(results1, results2)

        self.logger.info("Analysis results comparison completed")
        return comparison_results

    def validate_analysis_consistency(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate consistency of beating analysis results.

        Physical Meaning:
            Validates the internal consistency of beating analysis
            results to ensure they are physically reasonable.

        Args:
            results (Dict[str, Any]): Beating analysis results to validate.

        Returns:
            Dict[str, Any]: Consistency validation results.
        """
        self.logger.info("Starting analysis consistency validation")

        consistency_results = self.consistency.validate_consistency(results)

        self.logger.info("Analysis consistency validation completed")
        return consistency_results

    def _validate_beating_frequencies(self, frequencies: List[float]) -> Dict[str, Any]:
        """
        Validate beating frequencies.

        Physical Meaning:
            Validates beating frequencies for physical reasonableness
            and statistical significance.

        Args:
            frequencies (List[float]): List of beating frequencies.

        Returns:
            Dict[str, Any]: Frequency validation results.
        """
        if not frequencies:
            return {
                "valid": False,
                "reason": "No frequencies provided",
                "confidence": 0.0,
            }

        # Check physical reasonableness
        physically_reasonable = self._check_frequency_physical_reasonableness(
            frequencies
        )

        # Check statistical properties
        frequencies_array = np.array(frequencies)
        mean_freq = np.mean(frequencies_array)
        std_freq = np.std(frequencies_array)

        # Validation criteria
        valid = (
            physically_reasonable and std_freq < mean_freq * 0.5
        )  # Reasonable variation
        confidence = min(1.0, mean_freq / 10.0) if mean_freq > 0 else 0.0

        return {
            "valid": valid,
            "physically_reasonable": physically_reasonable,
            "mean_frequency": mean_freq,
            "frequency_std": std_freq,
            "confidence": confidence,
            "frequency_count": len(frequencies),
        }

    def _validate_interference_patterns(
        self, patterns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate interference patterns.

        Physical Meaning:
            Validates interference patterns for physical reasonableness
            and consistency.

        Args:
            patterns (List[Dict[str, Any]]): List of interference patterns.

        Returns:
            Dict[str, Any]: Pattern validation results.
        """
        if not patterns:
            return {"valid": False, "reason": "No patterns provided", "confidence": 0.0}

        # Validate each pattern
        valid_patterns = 0
        total_strength = 0.0

        for pattern in patterns:
            strength = pattern.get("strength", 0.0)
            if strength > 0.0:  # Basic validation
                valid_patterns += 1
                total_strength += strength

        # Validation criteria
        valid = valid_patterns > 0 and total_strength > 0.0
        confidence = valid_patterns / len(patterns) if patterns else 0.0

        return {
            "valid": valid,
            "valid_patterns": valid_patterns,
            "total_patterns": len(patterns),
            "total_strength": total_strength,
            "confidence": confidence,
        }

    def _validate_mode_coupling(self, coupling: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate mode coupling analysis.

        Physical Meaning:
            Validates mode coupling analysis for physical reasonableness
            and consistency.

        Args:
            coupling (Dict[str, Any]): Mode coupling analysis results.

        Returns:
            Dict[str, Any]: Coupling validation results.
        """
        if not coupling:
            return {
                "valid": False,
                "reason": "No coupling data provided",
                "confidence": 0.0,
            }

        # Extract coupling parameters
        coupling_strength = coupling.get("coupling_strength", 0.0)
        coupling_efficiency = coupling.get("coupling_efficiency", 0.0)
        coupling_type = coupling.get("coupling_type", "unknown")

        # Validation criteria
        strength_valid = 0.0 <= coupling_strength <= 1.0
        efficiency_valid = 0.0 <= coupling_efficiency <= 1.0
        type_valid = coupling_type in ["weak", "moderate", "strong"]

        valid = strength_valid and efficiency_valid and type_valid
        confidence = (coupling_strength + coupling_efficiency) / 2 if valid else 0.0

        return {
            "valid": valid,
            "strength_valid": strength_valid,
            "efficiency_valid": efficiency_valid,
            "type_valid": type_valid,
            "coupling_strength": coupling_strength,
            "coupling_efficiency": coupling_efficiency,
            "coupling_type": coupling_type,
            "confidence": confidence,
        }

    def _check_frequency_physical_reasonableness(
        self, frequencies: List[float]
    ) -> bool:
        """
        Check if frequencies are physically reasonable.

        Physical Meaning:
            Checks if beating frequencies are within physically
            reasonable ranges for the system.

        Args:
            frequencies (List[float]): List of frequencies to check.

        Returns:
            bool: True if frequencies are physically reasonable.
        """
        if not frequencies:
            return False

        frequencies_array = np.array(frequencies)

        # Check for positive frequencies
        if np.any(frequencies_array <= 0):
            return False

        # Check for reasonable frequency range (0.1 to 1000 Hz)
        if np.any(frequencies_array < 0.1) or np.any(frequencies_array > 1000.0):
            return False

        # Check for reasonable frequency distribution
        mean_freq = np.mean(frequencies_array)
        std_freq = np.std(frequencies_array)

        # Coefficient of variation should be reasonable
        if mean_freq > 0:
            cv = std_freq / mean_freq
            if cv > 2.0:  # Too much variation
                return False

        return True
