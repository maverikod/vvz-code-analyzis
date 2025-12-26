"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core analysis validation for beating.
"""

import numpy as np
from typing import Dict, Any

from .beating_basic_core_validation_quality import BeatingCoreValidationQuality


class BeatingCoreValidationCore:
    """
    Core analysis validation for beating.

    Physical Meaning:
        Validates the core analysis results to ensure
        they meet quality criteria.
    """

    def __init__(self):
        """Initialize core validation."""
        self._quality_assessor = BeatingCoreValidationQuality()

    def validate_core_analysis(self, core_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate core analysis results.

        Physical Meaning:
            Validates the core analysis results to ensure
            they meet quality criteria.

        Args:
            core_results (Dict[str, Any]): Core analysis results.

        Returns:
            Dict[str, Any]: Core validation results.
        """
        # Check if core analysis is complete
        is_complete = core_results.get("analysis_complete", False)

        # Check basic analysis quality
        basic_analysis = core_results.get("basic_analysis", {})
        basic_quality = self._quality_assessor.assess_basic_analysis_quality(basic_analysis)

        # Check interference analysis quality
        interference_analysis = core_results.get("interference_patterns", {})
        interference_quality = self._quality_assessor.assess_interference_analysis_quality(
            interference_analysis
        )

        # Check mode coupling analysis quality
        coupling_analysis = core_results.get("mode_coupling", {})
        coupling_quality = self._quality_assessor.assess_coupling_analysis_quality(coupling_analysis)

        # Check phase coherence analysis quality
        phase_analysis = core_results.get("phase_coherence", {})
        phase_quality = self._quality_assessor.assess_phase_analysis_quality(phase_analysis)

        # Calculate overall quality
        overall_quality = np.mean(
            [basic_quality, interference_quality, coupling_quality, phase_quality]
        )

        return {
            "is_complete": is_complete,
            "basic_quality": basic_quality,
            "interference_quality": interference_quality,
            "coupling_quality": coupling_quality,
            "phase_quality": phase_quality,
            "overall_quality": overall_quality,
        }

