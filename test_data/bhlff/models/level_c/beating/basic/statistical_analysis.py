"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Statistical beating analysis module.

This module implements statistical analysis functionality
for analyzing mode beating in the 7D phase field according to the
theoretical framework.

Physical Meaning:
    Implements statistical analysis of mode beating including
    statistical significance testing and pattern recognition.

Example:
    >>> analyzer = StatisticalBeatingAnalyzer(bvp_core)
    >>> results = analyzer.perform_statistical_analysis(envelope, basic_results)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .statistical_analysis_significance import StatisticalSignificanceTester
from .statistical_analysis_patterns import StatisticalPatternRecognizer
from .statistical_analysis_confidence import StatisticalConfidenceAnalyzer


class StatisticalBeatingAnalyzer:
    """
    Statistical beating analysis for Level C.

    Physical Meaning:
        Performs statistical analysis of mode beating patterns
        to determine significance and reliability of detected
        beating phenomena.

    Mathematical Foundation:
        Implements statistical methods for beating analysis:
        - Statistical significance testing
        - Pattern recognition and classification
        - Confidence interval analysis
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize statistical beating analyzer.

        Physical Meaning:
            Sets up the statistical analysis system with
            appropriate statistical parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Statistical analysis parameters
        self.significance_level = 0.05
        self.confidence_level = 0.95
        self.minimum_samples = 30

        # Initialize analysis components
        self._significance_tester = StatisticalSignificanceTester(bvp_core)
        self._pattern_recognizer = StatisticalPatternRecognizer(bvp_core)
        self._confidence_analyzer = StatisticalConfidenceAnalyzer(bvp_core)

    def perform_statistical_analysis(
        self, envelope: np.ndarray, basic_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform statistical analysis.

        Physical Meaning:
            Performs comprehensive statistical analysis of mode beating
            patterns including significance testing, pattern recognition,
            and confidence analysis.

        Mathematical Foundation:
            Implements statistical methods for beating analysis:
            - Statistical significance testing
            - Pattern recognition and classification
            - Confidence interval analysis

        Args:
            envelope (np.ndarray): 7D envelope field data.
            basic_results (Dict[str, Any]): Basic analysis results.

        Returns:
            Dict[str, Any]: Statistical analysis results including:
                - significance_testing: Statistical significance test results
                - pattern_recognition: Pattern recognition results
                - confidence_analysis: Confidence interval analysis results
        """
        self.logger.info("Starting statistical analysis")

        # Test statistical significance
        significance_testing = self._significance_tester.test_statistical_significance(
            envelope
        )

        # Recognize beating patterns
        pattern_recognition = self._pattern_recognizer.recognize_beating_patterns(
            envelope
        )

        # Analyze confidence intervals
        confidence_analysis = self._confidence_analyzer.analyze_confidence_intervals(
            envelope
        )

        # Combine all results
        statistical_results = {
            "significance_testing": significance_testing,
            "pattern_recognition": pattern_recognition,
            "confidence_analysis": confidence_analysis,
            "analysis_complete": True,
        }

        self.logger.info("Statistical analysis completed")
        return statistical_results
