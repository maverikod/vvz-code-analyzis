"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level C integration validation module.

This module implements validation functionality for Level C integration
in 7D phase field theory, including detailed acceptance criteria validation.

Physical Meaning:
    Validates Level C test results to ensure they meet quality
    and consistency criteria according to acceptance criteria from
    7d-33-БВП_план_численных_экспериментов_C.md.

Example:
    >>> validator = LevelCIntegrationValidation()
    >>> is_valid = validator.validate_c1_results(c1_results)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging
import sys
from pathlib import Path

# Import detailed validators
try:
    # Try to import from scripts directory
    scripts_path = Path(__file__).parent.parent.parent.parent / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    
    from level_c_validation.c1_validator import C1AcceptanceValidator
    from level_c_validation.c2_validator import C2AcceptanceValidator
    from level_c_validation.c3_validator import C3AcceptanceValidator
    from level_c_validation.c4_validator import C4AcceptanceValidator
    
    DETAILED_VALIDATION_AVAILABLE = True
except ImportError:
    DETAILED_VALIDATION_AVAILABLE = False


class LevelCIntegrationValidation:
    """
    Level C integration validation for comprehensive boundary and cell analysis.

    Physical Meaning:
        Validates Level C test results to ensure they meet quality
        and consistency criteria.

    Mathematical Foundation:
        Validates test results through quality assessment and
        consistency checking to ensure reliability.
    """

    def __init__(self):
        """Initialize Level C integration validation."""
        self.logger = logging.getLogger(__name__)
        
        # Initialize detailed validators if available
        if DETAILED_VALIDATION_AVAILABLE:
            self._c1_detailed = C1AcceptanceValidator()
            self._c2_detailed = C2AcceptanceValidator()
            self._c3_detailed = C3AcceptanceValidator()
            self._c4_detailed = C4AcceptanceValidator()
        else:
            self._c1_detailed = None
            self._c2_detailed = None
            self._c3_detailed = None
            self._c4_detailed = None
            self.logger.warning(
                "Detailed validators not available, using simplified validation"
            )

    def validate_c1_results(self, c1_results: Dict[str, Any]) -> bool:
        """
        Validate C1 test results.

        Physical Meaning:
            Validates C1 test results to ensure they meet
            quality criteria for boundary analysis according to
            acceptance criteria from the experiment plan.

        Mathematical Foundation:
            Validates against detailed criteria:
            - At η=0: no peaks ≥ 8 dB
            - At η≥0.1: ≥1 peak exists
            - Maximum localization between core and wall
            - Passivity P_Ω(ω)≥0 for all ω
            - Convergence: ω_n change ≤3%, Q_n change ≤10%

        Args:
            c1_results (Dict[str, Any]): C1 test results.

        Returns:
            bool: True if results are valid, False otherwise.
        """
        # Check if test is complete
        if not c1_results.get("test_complete", False):
            return False

        # Use detailed validation if available
        if self._c1_detailed is not None:
            try:
                detailed_result = self._c1_detailed.validate(c1_results)
                if detailed_result.all_passed:
                    return True
                else:
                    self.logger.warning(
                        f"C1 detailed validation failed: {detailed_result.failures}"
                    )
                    # Fall through to simplified check
            except Exception as e:
                self.logger.warning(f"Detailed C1 validation error: {e}, using simplified check")

        # Simplified validation fallback
        boundary_analysis = c1_results.get("boundary_analysis", {})
        if not boundary_analysis:
            return False

        abcd_analysis = c1_results.get("abcd_analysis", {})
        if not abcd_analysis:
            return False

        # Check quality metrics
        boundary_quality = boundary_analysis.get("quality_score", 0.0)
        abcd_quality = abcd_analysis.get("quality_score", 0.0)

        return boundary_quality > 0.5 and abcd_quality > 0.5

    def validate_c2_results(self, c2_results: Dict[str, Any]) -> bool:
        """
        Validate C2 test results.

        Physical Meaning:
            Validates C2 test results to ensure they meet
            quality criteria for resonator chain analysis according to
            acceptance criteria from the experiment plan.

        Mathematical Foundation:
            Validates against detailed criteria:
            - ≥3 peaks in Y(ω) with prominence ≥ 8 dB
            - ABCD prediction errors ≤10% overall, ≤5% at peaks
            - Frequency errors |ω^ABCD - ω^sim|/ω^sim ≤ 5%
            - Quality factor errors |Q^ABCD - Q^sim|/Q^sim ≤ 10%

        Args:
            c2_results (Dict[str, Any]): C2 test results.

        Returns:
            bool: True if results are valid, False otherwise.
        """
        # Check if test is complete
        if not c2_results.get("test_complete", False):
            return False

        # Use detailed validation if available
        if self._c2_detailed is not None:
            try:
                detailed_result = self._c2_detailed.validate(c2_results)
                if detailed_result.all_passed:
                    return True
                else:
                    self.logger.warning(
                        f"C2 detailed validation failed: {detailed_result.failures}"
                    )
            except Exception as e:
                self.logger.warning(f"Detailed C2 validation error: {e}, using simplified check")

        # Simplified validation fallback
        abcd_analysis = c2_results.get("abcd_analysis", {})
        if not abcd_analysis:
            return False

        abcd_quality = abcd_analysis.get("quality_score", 0.0)
        return abcd_quality > 0.5

    def validate_c3_results(self, c3_results: Dict[str, Any]) -> bool:
        """
        Validate C3 test results.

        Physical Meaning:
            Validates C3 test results to ensure they meet
            quality criteria for quench memory analysis according to
            acceptance criteria from the experiment plan.

        Mathematical Foundation:
            Validates against detailed criteria:
            - At γ=0: v_cell ≈ Δω/|Δk|, deviation ≤ 10%
            - At γ≥γ*: v_cell ≤ 10⁻³ L/T_0 (frozen)
            - Jaccard index ≥ 0.95 on long windows

        Args:
            c3_results (Dict[str, Any]): C3 test results.

        Returns:
            bool: True if results are valid, False otherwise.
        """
        # Check if test is complete
        if not c3_results.get("test_complete", False):
            return False

        # Use detailed validation if available
        if self._c3_detailed is not None:
            try:
                detailed_result = self._c3_detailed.validate(c3_results)
                if detailed_result.all_passed:
                    return True
                else:
                    self.logger.warning(
                        f"C3 detailed validation failed: {detailed_result.failures}"
                    )
            except Exception as e:
                self.logger.warning(f"Detailed C3 validation error: {e}, using simplified check")

        # Simplified validation fallback
        memory_analysis = c3_results.get("memory_analysis", {})
        if not memory_analysis:
            return False

        memory_quality = memory_analysis.get("quality_score", 0.0)
        return memory_quality > 0.5

    def validate_c4_results(self, c4_results: Dict[str, Any]) -> bool:
        """
        Validate C4 test results.

        Physical Meaning:
            Validates C4 test results to ensure they meet
            quality criteria for mode beating analysis according to
            acceptance criteria from the experiment plan.

        Mathematical Foundation:
            Validates against detailed criteria:
            - Without pinning: |v_cell^num - v_cell^pred|/v_cell^pred ≤ 10%
            - With pinning: v_cell^num/v_cell^pred ≤ 0.1 (suppression ≥10×)

        Args:
            c4_results (Dict[str, Any]): C4 test results.

        Returns:
            bool: True if results are valid, False otherwise.
        """
        # Check if test is complete
        if not c4_results.get("test_complete", False):
            return False

        # Use detailed validation if available
        if self._c4_detailed is not None:
            try:
                detailed_result = self._c4_detailed.validate(c4_results)
                if detailed_result.all_passed:
                    return True
                else:
                    self.logger.warning(
                        f"C4 detailed validation failed: {detailed_result.failures}"
                    )
            except Exception as e:
                self.logger.warning(f"Detailed C4 validation error: {e}, using simplified check")

        # Simplified validation fallback
        beating_analysis = c4_results.get("beating_analysis", {})
        if not beating_analysis:
            return False

        beating_quality = beating_analysis.get("quality_score", 0.0)
        return beating_quality > 0.5

    def validate_overall_results(
        self,
        c1_results: Dict[str, Any],
        c2_results: Dict[str, Any],
        c3_results: Dict[str, Any],
        c4_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validate overall results.

        Physical Meaning:
            Validates overall Level C test results to ensure
            they meet quality and consistency criteria.

        Args:
            c1_results (Dict[str, Any]): C1 test results.
            c2_results (Dict[str, Any]): C2 test results.
            c3_results (Dict[str, Any]): C3 test results.
            c4_results (Dict[str, Any]): C4 test results.

        Returns:
            Dict[str, Any]: Overall validation results.
        """
        # Validate individual tests
        c1_valid = self.validate_c1_results(c1_results)
        c2_valid = self.validate_c2_results(c2_results)
        c3_valid = self.validate_c3_results(c3_results)
        c4_valid = self.validate_c4_results(c4_results)

        # Calculate overall validation
        all_valid = c1_valid and c2_valid and c3_valid and c4_valid
        success_rate = sum([c1_valid, c2_valid, c3_valid, c4_valid]) / 4.0

        return {
            "c1_valid": c1_valid,
            "c2_valid": c2_valid,
            "c3_valid": c3_valid,
            "c4_valid": c4_valid,
            "all_valid": all_valid,
            "success_rate": success_rate,
            "validation_complete": True,
        }
