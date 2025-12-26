"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Admittance analysis module for boundary effects.

This module implements admittance analysis functionality
for Level C test C1 in 7D phase field theory.

Physical Meaning:
    Analyzes admittance spectrum for boundary effects,
    including resonance detection and quality factor analysis.

Example:
    >>> analyzer = AdmittanceAnalyzer(bvp_core)
    >>> results = analyzer.analyze_admittance_spectrum(domain, boundary, frequency_range)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, AdmittanceSpectrum
from .admittance_analysis_core import AdmittanceAnalysisCore
from .admittance_analysis_resonance import AdmittanceResonanceAnalyzer


class AdmittanceAnalyzer:
    """
    Admittance analysis for boundary effects.

    Physical Meaning:
        Analyzes admittance spectrum for boundary effects,
        including resonance detection and quality factor analysis.

    Mathematical Foundation:
        Implements admittance analysis:
        - Admittance calculation: Y(ω) = I(ω)/V(ω)
        - Resonance detection: peaks in |Y(ω)| spectrum
        - Quality factor analysis: Q = ω / (2 * Δω)
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize admittance analyzer.

        Physical Meaning:
            Sets up the admittance analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize analysis components
        self._core_analyzer = AdmittanceAnalysisCore(bvp_core)
        self._resonance_analyzer = AdmittanceResonanceAnalyzer(bvp_core)

    def analyze_admittance_spectrum(
        self,
        domain: Dict[str, Any],
        boundary: BoundaryGeometry,
        frequency_range: Tuple[float, float],
    ) -> AdmittanceSpectrum:
        """
        Analyze admittance spectrum.

        Physical Meaning:
            Analyzes admittance spectrum for boundary effects
            including resonance detection and quality factor analysis.

        Mathematical Foundation:
            Admittance calculation: Y(ω) = I(ω)/V(ω)
            Resonance detection: peaks in |Y(ω)| spectrum
            Quality factor analysis: Q = ω / (2 * Δω)

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            frequency_range (Tuple[float, float]): Frequency range for analysis.

        Returns:
            AdmittanceSpectrum: Admittance spectrum analysis results.
        """
        return self._core_analyzer.analyze_admittance_spectrum(
            domain, boundary, frequency_range
        )

    def detect_resonances(
        self, spectrum: AdmittanceSpectrum, threshold: float = 8.0
    ) -> List[Dict[str, Any]]:
        """
        Detect resonances in admittance spectrum.

        Physical Meaning:
            Detects resonances in admittance spectrum
            based on peak analysis and quality factor.

        Mathematical Foundation:
            Resonance detection: peaks in |Y(ω)| spectrum
            Quality factor analysis: Q = ω / (2 * Δω)

        Args:
            spectrum (AdmittanceSpectrum): Admittance spectrum.
            threshold (float): Detection threshold.

        Returns:
            List[Dict[str, Any]]: Detected resonances.
        """
        return self._resonance_analyzer.detect_resonances(spectrum, threshold)
