"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Soliton analysis module.

This module implements soliton analysis functionality
for Level F models in 7D phase field theory.

Physical Meaning:
    Implements soliton analysis including soliton solutions,
    stability analysis, and soliton interactions.

Example:
    >>> analyzer = SolitonAnalyzer(system, nonlinear_params)
    >>> solitons = analyzer.find_soliton_solutions()
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from ..base.abstract_model import AbstractModel
from .soliton_analysis_initialization import SolitonAnalysisInitialization
from .soliton_analysis_solutions import SolitonAnalysisSolutions


class SolitonAnalyzer(AbstractModel):
    """
    Soliton analysis for nonlinear systems.

    Physical Meaning:
        Analyzes soliton solutions in nonlinear systems,
        including soliton stability and interactions.

    Mathematical Foundation:
        Implements soliton analysis methods:
        - Soliton solution finding
        - Stability analysis
        - Interaction analysis
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """
        Initialize soliton analyzer.

        Physical Meaning:
            Sets up the soliton analysis system with
            nonlinear parameters and analysis methods.

        Args:
            system: Multi-particle system
            nonlinear_params (Dict[str, Any]): Nonlinear parameters
        """
        super().__init__()
        self.system = system
        self.nonlinear_params = nonlinear_params
        self.logger = logging.getLogger(__name__)

        # Initialize analysis components
        self._initialization = SolitonAnalysisInitialization(system, nonlinear_params)
        self._solutions = SolitonAnalysisSolutions(system, nonlinear_params)

    def find_soliton_solutions(self) -> Dict[str, Any]:
        """
        Find soliton solutions.

        Physical Meaning:
            Finds soliton solutions in the nonlinear system
            including single and multi-soliton solutions.

        Mathematical Foundation:
            Finds soliton solutions through optimization:
            - Single soliton solutions
            - Multi-soliton solutions
            - Solution validation

        Returns:
            Dict[str, Any]: Soliton solutions including:
                - single_solitons: Single soliton solutions
                - multi_solitons: Multi-soliton solutions
                - solution_quality: Solution quality metrics
        """
        self.logger.info("Starting soliton solution finding")

        # Find soliton solutions
        solutions = self._solutions.find_soliton_solutions()

        self.logger.info("Soliton solution finding completed")
        return solutions
