"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multi-soliton solutions and optimization facade.

This module provides the main interface for multi-soliton solution finding
and optimization using complete 7D BVP theory with soliton-soliton interactions.

Physical Meaning:
    Provides comprehensive multi-soliton analysis including optimization,
    validation, and physical properties computation using 7D BVP theory.

Example:
    >>> solver = MultiSolitonSolutions(system, nonlinear_params)
    >>> solutions = solver.find_multi_soliton_solutions()
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .base import SolitonAnalysisBase
from .multi_soliton_optimization import MultiSolitonOptimization
from .multi_soliton_validation import MultiSolitonValidation


class MultiSolitonSolutions(SolitonAnalysisBase):
    """
    Multi-soliton solution finder and optimizer facade.

    Physical Meaning:
        Provides comprehensive multi-soliton analysis including optimization,
        validation, and physical properties computation using 7D BVP theory.

    Mathematical Foundation:
        Combines optimization, validation, and analysis components
        for complete multi-soliton solution finding and analysis.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton solutions."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.optimizer = MultiSolitonOptimization(system, nonlinear_params)
        self.validator = MultiSolitonValidation(system, nonlinear_params)

    def find_multi_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find multi-soliton solutions using full 7D BVP theory.

        Physical Meaning:
            Finds multi-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and interaction
            potentials between solitons.

        Returns:
            List[Dict[str, Any]]: Multi-soliton solutions with full
            physical parameters and interaction analysis.
        """
        return self.optimizer.find_multi_soliton_solutions()

    def find_two_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find two-soliton solutions using full 7D BVP theory.

        Physical Meaning:
            Finds two-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and soliton-soliton
            interaction potentials with full 7D BVP theory implementation.

        Returns:
            List[Dict[str, Any]]: Two-soliton solutions with interaction
            analysis and full physical parameters.
        """
        return self.optimizer.find_two_soliton_solutions()

    def find_three_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find three-soliton solutions using full 7D BVP theory.

        Physical Meaning:
            Finds three-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and multi-soliton
            interaction potentials with full 7D BVP theory implementation.

        Returns:
            List[Dict[str, Any]]: Three-soliton solutions with full
            interaction analysis and stability properties.
        """
        return self.optimizer.find_three_soliton_solutions()

    def validate_two_soliton_solution(
        self,
        solution: Dict[str, Any],
        amp1: float,
        width1: float,
        amp2: float,
        width2: float,
    ) -> bool:
        """
        Validate two-soliton solution quality.

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
        return self.validator.validate_two_soliton_solution_quality(
            solution, amp1, width1, amp2, width2
        )

    def validate_three_soliton_solution(
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
        Validate three-soliton solution quality.

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
        return self.validator.validate_three_soliton_solution_quality(
            solution, amp1, width1, amp2, width2, amp3, width3
        )

    def compute_two_soliton_physical_properties(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        solution: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute comprehensive two-soliton physical properties.

        Physical Meaning:
            Computes all relevant physical properties of the two-soliton
            system including individual energies, interaction energy,
            stability metrics, and 7D BVP specific properties.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            solution (Dict[str, Any]): Two-soliton solution.

        Returns:
            Dict[str, Any]: Complete physical properties.
        """
        return self.validator.compute_two_soliton_physical_properties(
            amp1, width1, pos1, amp2, width2, pos2, solution
        )

    def compute_three_soliton_physical_properties(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
        solution: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute comprehensive three-soliton physical properties.

        Physical Meaning:
            Computes all relevant physical properties of the three-soliton
            system including individual energies, pairwise interactions,
            three-body interactions, stability metrics, and 7D BVP specific properties.

        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.
            solution (Dict[str, Any]): Three-soliton solution.

        Returns:
            Dict[str, Any]: Complete physical properties.
        """
        return self.validator.compute_three_soliton_physical_properties(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3, solution
        )
