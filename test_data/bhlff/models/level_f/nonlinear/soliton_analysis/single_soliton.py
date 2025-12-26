"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Single soliton analysis and optimization facade.

This module provides the main interface for single soliton solution finding
and analysis using complete 7D BVP theory with fractional Laplacian equations.

Physical Meaning:
    Provides comprehensive single soliton analysis including optimization,
    validation, and physical properties computation using 7D BVP theory.

Example:
    >>> solver = SingleSolitonSolver(system, nonlinear_params)
    >>> solution = solver.find_single_soliton()
"""

import numpy as np
from typing import Dict, Any, Optional
import logging

from .base import SolitonAnalysisBase
from .single_soliton_optimization import SingleSolitonOptimization
from .single_soliton_validation import SingleSolitonValidation


class SingleSolitonSolver(SolitonAnalysisBase):
    """
    Single soliton solution finder and analyzer facade.

    Physical Meaning:
        Provides comprehensive single soliton analysis including optimization,
        validation, and physical properties computation using 7D BVP theory.

    Mathematical Foundation:
        Combines optimization, validation, and analysis components
        for complete single soliton solution finding and analysis.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize single soliton solver."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.optimizer = SingleSolitonOptimization(system, nonlinear_params)
        self.validator = SingleSolitonValidation(system, nonlinear_params)

    def find_single_soliton(self) -> Optional[Dict[str, Any]]:
        """
        Find single soliton solution using full 7D BVP theory.

        Physical Meaning:
            Finds single soliton solution through complete optimization
            using 7D fractional Laplacian equations and boundary value
            problem solving with full 7D BVP theory implementation.

        Returns:
            Optional[Dict[str, Any]]: Single soliton solution with full
            physical parameters and optimization results.
        """
        return self.optimizer.find_single_soliton()

    def validate_soliton_solution(
        self, solution: Dict[str, Any], amplitude: float, width: float
    ) -> bool:
        """
        Validate soliton solution quality.

        Physical Meaning:
            Validates that the complete soliton solution meets
            all physical requirements and quality criteria.

        Args:
            solution (Dict[str, Any]): Complete soliton solution.
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.

        Returns:
            bool: True if solution quality is acceptable.
        """
        return self.validator.validate_solution_quality(solution, amplitude, width)

    def compute_soliton_physical_properties(
        self, amplitude: float, width: float, position: float, solution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute comprehensive soliton physical properties.

        Physical Meaning:
            Computes all relevant physical properties of the soliton
            including energy, momentum, topological charge, and stability
            metrics using 7D BVP theory.

        Args:
            amplitude (float): Soliton amplitude.
            width (float): Soliton width.
            position (float): Soliton position.
            solution (Dict[str, Any]): Soliton solution.

        Returns:
            Dict[str, Any]: Complete physical properties.
        """
        return self.validator.compute_soliton_physical_properties(
            amplitude, width, position, solution
        )
