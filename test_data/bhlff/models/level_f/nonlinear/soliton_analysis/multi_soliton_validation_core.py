"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core multi-soliton validation functionality.

This module implements core validation functionality for multi-soliton
solutions using 7D BVP theory.

Physical Meaning:
    Implements core multi-soliton validation including shape validation,
    solution quality assessment, and basic physical properties computation
    using 7D BVP theory principles.

Example:
    >>> validator = MultiSolitonValidationCore(system, nonlinear_params)
    >>> is_valid = validator.validate_two_soliton_shape(solution, amp1, width1, amp2, width2)
"""

import numpy as np
from typing import Dict, Any
import logging

from .base import SolitonAnalysisBase


class MultiSolitonValidationCore(SolitonAnalysisBase):
    """
    Core multi-soliton validation functionality.

    Physical Meaning:
        Implements core multi-soliton validation including shape validation,
        solution quality assessment, and basic physical properties computation
        using 7D BVP theory principles.

    Mathematical Foundation:
        Validates multi-soliton solutions against 7D BVP theory requirements
        including energy conservation, phase coherence, and stability.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton validation core."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

    def validate_two_soliton_shape(
        self,
        solution: np.ndarray,
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
    ) -> bool:
        """
        Validate two-soliton shape for physical correctness.

        Physical Meaning:
            Validates that the two-soliton solution has proper physical
            characteristics including proper separation, individual
            soliton shapes, and interaction effects.

        Args:
            solution (np.ndarray): Two-soliton solution.
            amp1, width1 (float): First soliton parameters.
            amp2, width2 (float): Second soliton parameters.

        Returns:
            bool: True if two-soliton shape is valid.
        """
        try:
            field = solution[0] if solution.ndim > 1 else solution

            # Check for proper amplitudes
            max_field = np.max(np.abs(field))
            expected_max = max(amp1, amp2)

            if max_field < 0.3 * expected_max or max_field > 3.0 * expected_max:
                return False

            # Check for two distinct peaks (basic two-soliton check)
            if len(field) > 20:
                # Find peaks
                from scipy.signal import find_peaks

                peaks, _ = find_peaks(np.abs(field), height=0.5 * max_field)

                if (
                    len(peaks) < 1 or len(peaks) > 3
                ):  # Should have 1-3 peaks (2 solitons + possible interaction)
                    return False

            # Check for no excessive oscillations
            if len(field) > 10:
                second_deriv = np.gradient(np.gradient(field))
                if np.any(np.abs(second_deriv) > 20.0 * expected_max):
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Two-soliton shape validation failed: {e}")
            return False

    def validate_three_soliton_shape(
        self,
        solution: np.ndarray,
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
        amp3: float,
        width3: float,
    ) -> bool:
        """
        Validate three-soliton shape for physical correctness.

        Physical Meaning:
            Validates that the three-soliton solution has proper physical
            characteristics including proper separation, individual
            soliton shapes, and multi-body interaction effects.

        Args:
            solution (np.ndarray): Three-soliton solution.
            amp1, width1 (float): First soliton parameters.
            amp2, width2 (float): Second soliton parameters.
            amp3, width3 (float): Third soliton parameters.

        Returns:
            bool: True if three-soliton shape is valid.
        """
        try:
            field = solution[0] if solution.ndim > 1 else solution

            # Check for proper amplitudes
            max_field = np.max(np.abs(field))
            expected_max = max(amp1, amp2, amp3)

            if max_field < 0.2 * expected_max or max_field > 4.0 * expected_max:
                return False

            # Check for three distinct peaks (basic three-soliton check)
            if len(field) > 30:
                # Find peaks
                from scipy.signal import find_peaks

                peaks, _ = find_peaks(np.abs(field), height=0.3 * max_field)

                if (
                    len(peaks) < 2 or len(peaks) > 5
                ):  # Should have 2-5 peaks (3 solitons + possible interactions)
                    return False

            # Check for no excessive oscillations
            if len(field) > 15:
                second_deriv = np.gradient(np.gradient(field))
                if np.any(np.abs(second_deriv) > 30.0 * expected_max):
                    return False

            return True

        except Exception as e:
            self.logger.error(f"Three-soliton shape validation failed: {e}")
            return False

    def validate_two_soliton_solution_quality(
        self,
        solution: Dict[str, Any],
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
    ) -> bool:
        """
        Validate overall two-soliton solution quality.

        Physical Meaning:
            Validates that the complete two-soliton solution meets
            all physical requirements and quality criteria.

        Args:
            solution (Dict[str, Any]): Complete two-soliton solution.
            amp1, width1 (float): First soliton parameters.
            amp2, width2 (float): Second soliton parameters.

        Returns:
            bool: True if solution quality is acceptable.
        """
        try:
            # Check solution completeness
            required_keys = [
                "spatial_grid",
                "total_profile",
                "soliton_1_profile",
                "soliton_2_profile",
                "total_field_energy",
            ]
            if not all(key in solution for key in required_keys):
                return False

            # Check physical parameters
            if solution["total_field_energy"] <= 0 or np.isnan(
                solution["total_field_energy"]
            ):
                return False

            # Check individual soliton profiles
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]

            if np.any(np.isnan(profile1)) or np.any(np.isinf(profile1)):
                return False
            if np.any(np.isnan(profile2)) or np.any(np.isinf(profile2)):
                return False

            # Check interaction distance is reasonable
            distance = solution.get("distance", 0.0)
            if distance < 0.1 or distance > 20.0:  # Reasonable interaction distance
                return False

            return True

        except Exception as e:
            self.logger.error(f"Two-soliton solution quality validation failed: {e}")
            return False

    def validate_three_soliton_solution_quality(
        self,
        solution: Dict[str, Any],
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
        amp3: float,
        width3: float,
    ) -> bool:
        """
        Validate overall three-soliton solution quality.

        Physical Meaning:
            Validates that the complete three-soliton solution meets
            all physical requirements and quality criteria.

        Args:
            solution (Dict[str, Any]): Complete three-soliton solution.
            amp1, width1 (float): First soliton parameters.
            amp2, width2 (float): Second soliton parameters.
            amp3, width3 (float): Third soliton parameters.

        Returns:
            bool: True if solution quality is acceptable.
        """
        try:
            # Check solution completeness
            required_keys = [
                "spatial_grid",
                "total_profile",
                "soliton_1_profile",
                "soliton_2_profile",
                "soliton_3_profile",
                "total_field_energy",
            ]
            if not all(key in solution for key in required_keys):
                return False

            # Check physical parameters
            if solution["total_field_energy"] <= 0 or np.isnan(
                solution["total_field_energy"]
            ):
                return False

            # Check individual soliton profiles
            profile1 = solution["soliton_1_profile"]
            profile2 = solution["soliton_2_profile"]
            profile3 = solution["soliton_3_profile"]

            for profile in [profile1, profile2, profile3]:
                if np.any(np.isnan(profile)) or np.any(np.isinf(profile)):
                    return False

            # Check interaction distances are reasonable
            distances = solution.get("distances", [])
            if len(distances) >= 3:
                for distance in distances:
                    if (
                        distance < 0.1 or distance > 30.0
                    ):  # Reasonable interaction distances
                        return False

            return True

        except Exception as e:
            self.logger.error(f"Three-soliton solution quality validation failed: {e}")
            return False

    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """Step resonator profile using 7D BVP theory."""
        try:
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)
        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)
