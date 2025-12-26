"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main soliton analysis solutions facade.

This module provides the main interface for soliton analysis
functionality, combining single and multi-soliton solvers
with interaction analysis.

Physical Meaning:
    Provides comprehensive soliton solution finding and analysis
    using 7D BVP theory with fractional Laplacian equations
    and soliton-soliton interactions.

Example:
    >>> solver = SolitonAnalysisSolutions(system, nonlinear_params)
    >>> solutions = solver.find_soliton_solutions()
"""

import numpy as np
from typing import Dict, Any, List, Optional
import logging

from .base import SolitonAnalysisBase
from .single_soliton import SingleSolitonSolver
from .multi_soliton import MultiSolitonSolver
from .interactions import SolitonInteractionAnalyzer


class SolitonAnalysisSolutions(SolitonAnalysisBase):
    """
    Main soliton analysis solutions facade.

    Physical Meaning:
        Provides comprehensive soliton solution finding and analysis
        using 7D BVP theory with fractional Laplacian equations
        and soliton-soliton interactions.

    Mathematical Foundation:
        Combines single and multi-soliton solvers with complete
        interaction analysis and stability assessment.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """
        Initialize soliton analysis solutions.

        Physical Meaning:
            Sets up the complete soliton analysis system with
            single and multi-soliton solvers and interaction analysis.

        Args:
            system: Physical system configuration.
            nonlinear_params (Dict[str, Any]): Nonlinear parameters including
                μ, β, λ, and interaction strengths.
        """
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize specialized solvers
        self.single_solver = SingleSolitonSolver(system, nonlinear_params)
        self.multi_solver = MultiSolitonSolver(system, nonlinear_params)
        self.interaction_analyzer = SolitonInteractionAnalyzer(system, nonlinear_params)

    def find_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find all soliton solutions using complete 7D BVP theory.

        Physical Meaning:
            Finds comprehensive soliton solutions including single
            and multi-soliton configurations with full interaction
            analysis and stability assessment.

        Returns:
            List[Dict[str, Any]]: Complete soliton solutions with
            full physical parameters and analysis.
        """
        soliton_profiles = []

        try:
            # Find single soliton solution
            single_soliton = self.single_solver.find_single_soliton()
            if single_soliton:
                soliton_profiles.append(single_soliton)

            # Find multi-soliton solutions
            multi_solitons = self.multi_solver.find_multi_soliton_solutions()
            soliton_profiles.extend(multi_solitons)

            # Analyze interactions if multiple solitons exist
            if len(soliton_profiles) > 1:
                interaction_analysis = self.interaction_analyzer.analyze_interactions(
                    multi_solitons
                )
                for soliton in soliton_profiles:
                    soliton["interaction_analysis"] = interaction_analysis

            return soliton_profiles

        except Exception as e:
            self.logger.error(f"Soliton solutions finding failed: {e}")
            return []

    def calculate_solution_quality(
        self, soliton_profiles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate solution quality metrics.

        Physical Meaning:
            Calculates comprehensive quality metrics for soliton solutions
            based on optimization success, energy, and stability.

        Args:
            soliton_profiles (List[Dict[str, Any]]): Soliton profiles.

        Returns:
            Dict[str, Any]: Solution quality metrics.
        """
        if not soliton_profiles:
            return {"quality_score": 0.0, "total_energy": 0.0, "success_rate": 0.0}

        try:
            # Calculate quality metrics
            successful_solutions = sum(
                1 for s in soliton_profiles if s.get("optimization_success", False)
            )
            success_rate = successful_solutions / len(soliton_profiles)

            total_energy = sum(s.get("energy", 0.0) for s in soliton_profiles)
            quality_score = success_rate * (
                1.0 + total_energy / 10.0
            )  # Normalized quality score

            # Stability analysis
            stable_solutions = sum(
                1
                for s in soliton_profiles
                if s.get("interaction_analysis", {}).get("collective_stability", False)
            )
            stability_rate = (
                stable_solutions / len(soliton_profiles) if soliton_profiles else 0
            )

            return {
                "quality_score": quality_score,
                "total_energy": total_energy,
                "success_rate": success_rate,
                "stability_rate": stability_rate,
                "num_solutions": len(soliton_profiles),
                "successful_solutions": successful_solutions,
                "stable_solutions": stable_solutions,
            }

        except Exception as e:
            self.logger.error(f"Solution quality calculation failed: {e}")
            return {"quality_score": 0.0, "total_energy": 0.0, "success_rate": 0.0}
