"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Multi-soliton analysis and optimization facade.

This module provides the main interface for multi-soliton analysis
functionality, combining core multi-soliton operations with
solution finding and optimization.

Physical Meaning:
    Provides comprehensive multi-soliton analysis including two and three
    soliton configurations with complete interaction analysis
    and stability properties using 7D phase field theory.

Example:
    >>> solver = MultiSolitonSolver(system, nonlinear_params)
    >>> solutions = solver.find_multi_soliton_solutions()
"""

import numpy as np
from typing import Dict, Any, List
import logging

from .base import SolitonAnalysisBase
from .multi_soliton_core import MultiSolitonCore
from .multi_soliton_solutions import MultiSolitonSolutions


class MultiSolitonSolver(SolitonAnalysisBase):
    """
    Multi-soliton analysis facade.

    Physical Meaning:
        Provides comprehensive multi-soliton analysis including two and three
        soliton configurations with complete interaction analysis
        and stability properties using 7D phase field theory.

    Mathematical Foundation:
        Combines core multi-soliton operations with solution finding
        and optimization using 7D BVP theory.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize multi-soliton solver."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized components
        self.core = MultiSolitonCore(system, nonlinear_params)
        self.solutions = MultiSolitonSolutions(system, nonlinear_params)

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
        return self.solutions.find_multi_soliton_solutions()

    def find_two_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find two-soliton solutions using full 7D BVP theory.

        Physical Meaning:
            Finds two-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and soliton-soliton
            interaction potentials.

        Returns:
            List[Dict[str, Any]]: Two-soliton solutions with interaction
            analysis and full physical parameters.
        """
        return self.solutions.find_two_soliton_solutions()

    def find_three_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find three-soliton solutions using full 7D BVP theory.

        Physical Meaning:
            Finds three-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and multi-soliton
            interaction potentials.

        Returns:
            List[Dict[str, Any]]: Three-soliton solutions with full
            interaction analysis and stability properties.
        """
        return self.solutions.find_three_soliton_solutions()

    # Delegate core functionality to specialized components
    def _compute_7d_two_soliton_ode(
        self,
        x: np.ndarray,
        y: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> np.ndarray:
        """Delegate to core component."""
        return self.core.compute_7d_two_soliton_ode(
            x, y, amp1, width1, pos1, amp2, width2, pos2
        )

    def _compute_7d_three_soliton_ode(
        self,
        x: np.ndarray,
        y: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> np.ndarray:
        """Delegate to core component."""
        return self.core.compute_7d_three_soliton_ode(
            x, y, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def _compute_two_soliton_energy(
        self,
        solution: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """Delegate to core component."""
        return self.core.compute_two_soliton_energy(
            solution, amp1, width1, pos1, amp2, width2, pos2
        )

    def _compute_three_soliton_energy(
        self,
        solution: np.ndarray,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
        amp3: float,
        width3: float,
        pos3: float,
    ) -> float:
        """Delegate to core component."""
        return self.core.compute_three_soliton_energy(
            solution, amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def _compute_final_two_soliton_solution(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> Dict[str, Any]:
        """Delegate to solutions component."""
        return self.solutions._compute_final_two_soliton_solution(
            amp1, width1, pos1, amp2, width2, pos2
        )

    def _compute_final_three_soliton_solution(
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
    ) -> Dict[str, Any]:
        """Delegate to solutions component."""
        return self.solutions._compute_final_three_soliton_solution(
            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
        )

    def compute_soliton_energy(
        self, solution: np.ndarray, amplitude: float, width: float
    ) -> float:
        """Delegate to core component."""
        return self.core.compute_soliton_energy(solution, amplitude, width)

    def compute_soliton_interaction_strength(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> float:
        """Delegate to core component."""
        return self.core.compute_soliton_interaction_strength(
            amp1, width1, pos1, amp2, width2, pos2
        )

    def _step_resonator_interaction(
        self, distance: float, interaction_range: float
    ) -> float:
        """Delegate to core component."""
        return self.core._step_resonator_interaction(distance, interaction_range)
