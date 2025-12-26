"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Basic beating core analysis module.

This module implements core analysis functionality for comprehensive beating analysis
in Level C of 7D phase field theory.

Physical Meaning:
    Performs core analysis of mode beating including comprehensive analysis,
    statistical analysis, and comparison of different analyses.

Example:
    >>> analyzer = BeatingCoreAnalysis(bvp_core)
    >>> results = analyzer.analyze_beating_comprehensive(envelope)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .core_analysis import CoreBeatingAnalyzer
from .statistical_analysis import StatisticalBeatingAnalyzer
from .comparison import BeatingComparator


class BeatingCoreAnalysis:
    """
    Core beating analysis for Level C.

    Physical Meaning:
        Performs core analysis of mode beating according to the 7D phase field
        theory, including interference patterns, mode coupling, and phase coherence.

    Mathematical Foundation:
        Analyzes beating through mode interference:
        I(t) = |A₁e^(iω₁t) + A₂e^(iω₂t)|²
        where A₁, A₂ are mode amplitudes and ω₁, ω₂ are frequencies.
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize core beating analysis.

        Physical Meaning:
            Sets up the core beating analysis system with
            theoretical parameters and specialized analysis modules.

        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Theoretical analysis parameters
        self.statistical_analysis_enabled = True
        self.phase_coherence_analysis_enabled = True

        # Theoretical thresholds based on 7D phase field theory
        self.interference_threshold = 1e-12  # Minimum interference strength
        self.coupling_threshold = 1e-10  # Minimum coupling strength
        self.phase_coherence_threshold = 0.01  # Minimum phase coherence
        self.statistical_significance = 0.05

        # Initialize specialized modules
        self.core_analyzer = CoreBeatingAnalyzer(bvp_core)
        self.statistical_analyzer = StatisticalBeatingAnalyzer(bvp_core)
        self.comparator = BeatingComparator(bvp_core)

    def analyze_beating_comprehensive(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Comprehensive beating analysis according to theoretical framework.

        Physical Meaning:
            Performs full theoretical analysis of mode beating
            according to the 7D phase field theory, including
            interference patterns, mode coupling, and phase coherence.

        Mathematical Foundation:
            Analyzes beating through mode interference:
            I(t) = |A₁e^(iω₁t) + A₂e^(iω₂t)|²
            where A₁, A₂ are mode amplitudes and ω₁, ω₂ are frequencies.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Comprehensive analysis results including:
                - interference_patterns: Detected interference patterns
                - mode_coupling: Mode coupling analysis
                - phase_coherence: Phase coherence analysis
                - beating_frequencies: Theoretical beating frequencies
        """
        self.logger.info("Starting comprehensive beating analysis")

        # Core analysis
        core_results = self.core_analyzer.analyze_beating_comprehensive(envelope)

        # Statistical analysis
        if self.statistical_analysis_enabled:
            statistical_results = (
                self.statistical_analyzer.perform_statistical_analysis(
                    envelope, core_results.get("basic_analysis", {})
                )
            )
        else:
            statistical_results = {}

        # Combine all results
        comprehensive_results = {
            "core_analysis": core_results,
            "statistical_analysis": statistical_results,
            "analysis_complete": True,
        }

        self.logger.info("Comprehensive beating analysis completed")
        return comprehensive_results

    def analyze_beating_statistical(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Statistical beating analysis.

        Physical Meaning:
            Analyzes mode beating using statistical methods
            for comprehensive understanding of beating patterns.

        Args:
            envelope (np.ndarray): 7D envelope field data.

        Returns:
            Dict[str, Any]: Statistical analysis results.
        """
        self.logger.info("Starting statistical beating analysis")

        # Basic analysis
        basic_results = self.core_analyzer.analyze_beating_comprehensive(envelope)

        # Statistical analysis
        statistical_results = self.statistical_analyzer.perform_statistical_analysis(
            envelope, basic_results.get("basic_analysis", {})
        )

        self.logger.info("Statistical beating analysis completed")
        return statistical_results

    def compare_beating_analyses(
        self, results1: Dict[str, Any], results2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare different beating analyses.

        Physical Meaning:
            Compares different beating analyses to identify
            similarities, differences, and consistency.

        Args:
            results1 (Dict[str, Any]): First analysis results.
            results2 (Dict[str, Any]): Second analysis results.

        Returns:
            Dict[str, Any]: Comparison results.
        """
        self.logger.info("Starting beating analyses comparison")

        # Compare analyses
        comparison_results = self.comparator.compare_analyses(results1, results2)

        self.logger.info("Beating analyses comparison completed")
        return comparison_results
