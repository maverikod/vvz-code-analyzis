"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multi-soliton validation and physical properties facade.

This module provides the main interface for multi-soliton validation
and physical properties computation using 7D BVP theory.

Physical Meaning:
    Provides comprehensive multi-soliton validation including shape validation,
    solution quality assessment, and physical properties computation
    using 7D BVP theory principles.

Example:
    >>> validator = MultiSolitonValidation(system, nonlinear_params)
    >>> is_valid = validator.validate_two_soliton_shape(solution, amp1, width1, amp2, width2)
"""

import numpy as np
from typing import Dict, Any
import logging

from .base import SolitonAnalysisBase
from .multi_soliton_validation_core import MultiSolitonValidationCore
from .multi_soliton_physical_properties import MultiSolitonPhysicalProperties


class MultiSolitonValidation(SolitonAnalysisBase):
    """
    Multi-soliton validation and physical properties facade.

    Physical Meaning:
        Provides comprehensive multi-soliton validation including shape validation,
        solution quality assessment, and physical properties computation
        using 7D BVP theory principles.

    Mathematical Foundation:
        Combines validation and physical properties computation components
        for complete multi-soliton analysis.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton validation."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.core = MultiSolitonValidationCore(system, nonlinear_params)
        self.properties = MultiSolitonPhysicalProperties(system, nonlinear_params)

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
        return self.core.validate_two_soliton_shape(
            solution, amp1, width1, amp2, width2
        )

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
        return self.core.validate_three_soliton_shape(
            solution, amp1, width1, amp2, width2, amp3, width3
        )

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
        return self.core.validate_two_soliton_solution_quality(
            solution, amp1, width1, amp2, width2
        )

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
        return self.core.validate_three_soliton_solution_quality(
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
        return self.properties.compute_two_soliton_physical_properties(
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
        return self.properties.compute_three_soliton_physical_properties(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3, solution
        )
