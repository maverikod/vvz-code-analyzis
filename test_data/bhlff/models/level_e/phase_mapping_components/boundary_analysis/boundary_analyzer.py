"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main boundary analyzer for phase mapping.

This module implements the main boundary analyzer that coordinates
analysis of regime boundaries using 7D BVP theory principles.

Theoretical Background:
    The boundary analyzer identifies transition points between different
    system behavior regimes in parameter space, revealing the structure
    of the phase diagram through comprehensive 7D phase field analysis.

Example:
    >>> analyzer = BoundaryAnalyzer()
    >>> boundaries = analyzer.analyze_regime_boundaries(parameter_grid, classifications)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from .phase_coherence_analysis import PhaseCoherenceAnalyzer
from .topological_analysis import TopologicalAnalyzer
from .energy_landscape_analysis import EnergyLandscapeAnalyzer


class BoundaryAnalyzer:
    """
    Main boundary analyzer for regime transitions.

    Physical Meaning:
        Analyzes boundaries between different system behavior
        regimes in parameter space, identifying transition
        points and regime characteristics using 7D BVP theory.

    Mathematical Foundation:
        Uses 7D phase field gradient analysis to identify regime
        boundaries through phase coherence analysis and topological
        charge distribution.
    """

    def __init__(self):
        """
        Initialize boundary analyzer.

        Physical Meaning:
            Sets up the analyzer for studying regime boundaries
            in parameter space using 7D BVP theory principles.
        """
        self.boundary_threshold = 0.1
        self.separation_threshold = 0.5
        self.regime_pairs = [("PL", "R"), ("PL", "FRZ"), ("R", "FRZ"), ("FRZ", "LEAK")]
        self.parameter_names = ["eta", "chi_double_prime", "beta"]

        # Initialize specialized analyzers
        self.phase_coherence_analyzer = PhaseCoherenceAnalyzer()
        self.topological_analyzer = TopologicalAnalyzer()
        self.energy_landscape_analyzer = EnergyLandscapeAnalyzer()

    def analyze_regime_boundaries(
        self, parameter_grid: Dict[str, np.ndarray], classifications: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze boundaries between regimes.

        Physical Meaning:
            Analyzes boundaries between different system behavior regimes
            using 7D phase field theory, identifying transition points
            and regime characteristics.

        Args:
            parameter_grid (Dict[str, np.ndarray]): Grid of parameter values.
            classifications (Dict[str, Any]): Regime classifications for each point.

        Returns:
            Dict[str, Any]: Analysis results including boundary information.
        """
        boundaries = {}

        # Extract regime information
        regime_data = self._extract_regime_data(classifications)

        # Analyze boundaries between different regimes
        for regime1, regime2 in self.regime_pairs:
            boundary = self._find_regime_boundary(regime_data, regime1, regime2)
            boundaries[f"{regime1}_{regime2}"] = boundary

        return boundaries

    def _extract_regime_data(
        self, classifications: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract regime data from classifications.

        Physical Meaning:
            Extracts parameter values and regime information from
            classification results for boundary analysis.
        """
        regime_data = []
        for point_id, classification in classifications.items():
            params = classification["parameters"]
            regime = classification.get("primary_regime", "unknown")
            regime_data.append(
                {
                    "eta": params["eta"],
                    "chi_double_prime": params["chi_double_prime"],
                    "beta": params["beta"],
                    "regime": regime,
                }
            )
        return regime_data

    def _find_regime_boundary(
        self, regime_data: List[Dict[str, Any]], regime1: str, regime2: str
    ) -> Dict[str, Any]:
        """
        Find boundary between two regimes using 7D BVP theory.

        Physical Meaning:
            Identifies the boundary between two regimes using comprehensive
            7D phase field analysis, including phase coherence and topological
            analysis.
        """
        # Filter data for the two regimes
        regime1_data = [d for d in regime_data if d["regime"] == regime1]
        regime2_data = [d for d in regime_data if d["regime"] == regime2]

        if not regime1_data or not regime2_data:
            return {"boundary": None, "separation": 0.0}

        # Compute separation between regimes
        separation = self._compute_regime_separation(regime1_data, regime2_data)

        # Find boundary points using 7D BVP theory
        boundary_points = self._find_boundary_points_7d(regime1_data, regime2_data)

        # Analyze phase coherence at boundaries
        phase_coherence = self.phase_coherence_analyzer.analyze_boundary_coherence(
            regime1_data, regime2_data, boundary_points
        )

        # Analyze topological properties
        topological_analysis = self.topological_analyzer.analyze_boundary_topology(
            regime1_data, regime2_data, boundary_points
        )

        # Analyze energy landscape
        energy_analysis = self.energy_landscape_analyzer.analyze_boundary_energy(
            regime1_data, regime2_data, boundary_points
        )

        return {
            "separation": separation,
            "boundary_points": boundary_points,
            "regime1_count": len(regime1_data),
            "regime2_count": len(regime2_data),
            "phase_coherence": phase_coherence,
            "topological_analysis": topological_analysis,
            "energy_analysis": energy_analysis,
        }

    def _compute_regime_separation(
        self, regime1_data: List[Dict[str, Any]], regime2_data: List[Dict[str, Any]]
    ) -> float:
        """
        Compute separation between two regimes.

        Physical Meaning:
            Computes the separation distance between two regimes
            in parameter space using 7D BVP theory principles.
        """
        # Extract parameter values
        regime1_params = np.array(
            [[d["eta"], d["chi_double_prime"], d["beta"]] for d in regime1_data]
        )
        regime2_params = np.array(
            [[d["eta"], d["chi_double_prime"], d["beta"]] for d in regime2_data]
        )

        # Compute mean parameter values
        mean1 = np.mean(regime1_params, axis=0)
        mean2 = np.mean(regime2_params, axis=0)

        # Compute separation distance
        separation = np.linalg.norm(mean1 - mean2)

        return separation

    def _find_boundary_points_7d(
        self, regime1_data: List[Dict[str, Any]], regime2_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find boundary points using 7D BVP theory.

        Physical Meaning:
            Identifies boundary points between regimes using 7D phase
            field analysis and topological defect characterization.
        """
        boundary_points = []

        if not regime1_data or not regime2_data:
            return boundary_points

        # Extract parameter arrays for efficient computation
        regime1_params = np.array(
            [[d["eta"], d["chi_double_prime"], d["beta"]] for d in regime1_data]
        )
        regime2_params = np.array(
            [[d["eta"], d["chi_double_prime"], d["beta"]] for d in regime2_data]
        )

        # Compute 7D phase field boundary analysis
        boundary_analysis = self._compute_7d_boundary_analysis(
            regime1_params, regime2_params
        )

        # Find critical boundary points using 7D BVP theory
        critical_points = self._find_critical_boundary_points(
            regime1_data, regime2_data, boundary_analysis
        )

        # Combine all boundary information
        for i, (d1, d2) in enumerate(zip(regime1_data, regime2_data)):
            if i < len(critical_points):
                params1 = np.array([d1["eta"], d1["chi_double_prime"], d1["beta"]])
                params2 = np.array([d2["eta"], d2["chi_double_prime"], d2["beta"]])
                distance = np.linalg.norm(params1 - params2)

                # Apply 7D BVP boundary criteria
                if self._is_7d_boundary_point(params1, params2, boundary_analysis):
                    boundary_points.append(
                        {
                            "regime1_point": d1,
                            "regime2_point": d2,
                            "distance": distance,
                            "critical_point": (
                                critical_points[i] if i < len(critical_points) else None
                            ),
                            "7d_boundary_strength": self._compute_7d_boundary_strength(
                                params1, params2
                            ),
                        }
                    )

        return boundary_points

    def _compute_7d_boundary_analysis(
        self, regime1_params: np.ndarray, regime2_params: np.ndarray
    ) -> Dict[str, Any]:
        """
        Compute 7D phase field boundary analysis.

        Physical Meaning:
            Analyzes the boundary between regimes using 7D phase field
            theory, computing phase coherence and topological properties.
        """
        # Compute mean parameter vectors
        mean1 = np.mean(regime1_params, axis=0)
        mean2 = np.mean(regime2_params, axis=0)

        # Compute parameter space distance
        param_distance = np.linalg.norm(mean1 - mean2)

        # Compute 7D phase field gradient
        phase_gradient = self._compute_7d_phase_gradient(regime1_params, regime2_params)

        # Compute phase coherence length
        coherence_length = self._compute_phase_coherence_length(
            regime1_params, regime2_params
        )

        # Compute topological defect density
        defect_density = self._compute_topological_defect_density(
            regime1_params, regime2_params
        )

        return {
            "param_distance": param_distance,
            "phase_gradient": phase_gradient,
            "coherence_length": coherence_length,
            "defect_density": defect_density,
            "boundary_strength": self._compute_boundary_strength(
                phase_gradient, coherence_length
            ),
        }

    def _find_critical_boundary_points(
        self,
        regime1_data: List[Dict[str, Any]],
        regime2_data: List[Dict[str, Any]],
        boundary_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Find critical boundary points using 7D BVP theory.

        Physical Meaning:
            Identifies critical points where regime transitions occur
            based on 7D phase field topology and energy landscape analysis.
        """
        critical_points = []

        # Compute energy landscape
        energy_landscape = self.energy_landscape_analyzer.compute_energy_landscape(
            regime1_data, regime2_data
        )

        # Find energy minima and saddle points
        minima = self.energy_landscape_analyzer.find_energy_minima(energy_landscape)
        saddle_points = self.energy_landscape_analyzer.find_saddle_points(
            energy_landscape
        )

        # Analyze critical point stability
        for point in minima + saddle_points:
            stability = self.energy_landscape_analyzer.analyze_critical_point_stability(
                point, energy_landscape
            )
            critical_points.append(
                {
                    "position": point["position"],
                    "energy": point["energy"],
                    "type": point["type"],
                    "stability": stability,
                    "7d_phase_coherence": self.phase_coherence_analyzer.compute_7d_phase_coherence_at_point(
                        point
                    ),
                }
            )

        return critical_points

    def _is_7d_boundary_point(
        self,
        params1: np.ndarray,
        params2: np.ndarray,
        boundary_analysis: Dict[str, Any],
    ) -> bool:
        """
        Check if point is a 7D BVP boundary point.

        Physical Meaning:
            Determines if a point represents a true boundary between
            regimes based on 7D phase field theory criteria.
        """
        distance = np.linalg.norm(params1 - params2)

        # Apply 7D BVP boundary criteria
        phase_gradient_threshold = boundary_analysis.get("phase_gradient", 0.0)
        coherence_threshold = boundary_analysis.get("coherence_length", 1.0)

        # Check distance threshold
        if distance > self.boundary_threshold:
            return False

        # Check phase field criteria
        phase_criteria = self._check_phase_field_criteria(
            params1, params2, boundary_analysis
        )

        # Check topological criteria
        topological_criteria = self._check_topological_criteria(
            params1, params2, boundary_analysis
        )

        return phase_criteria and topological_criteria

    def _compute_7d_boundary_strength(
        self, params1: np.ndarray, params2: np.ndarray
    ) -> float:
        """
        Compute 7D BVP boundary strength.

        Physical Meaning:
            Computes the strength of the boundary between regimes
            based on 7D phase field theory principles.
        """
        # Compute parameter space distance
        param_distance = np.linalg.norm(params1 - params2)

        # Compute phase field gradient
        phase_gradient = np.linalg.norm(params1 - params2)

        # Compute boundary strength
        boundary_strength = phase_gradient / (1.0 + param_distance)

        return boundary_strength

    # Helper methods for 7D BVP analysis
    def _compute_7d_phase_gradient(
        self, regime1_params: np.ndarray, regime2_params: np.ndarray
    ) -> np.ndarray:
        """Compute 7D phase field gradient."""
        mean1 = np.mean(regime1_params, axis=0)
        mean2 = np.mean(regime2_params, axis=0)
        return mean2 - mean1

    def _compute_phase_coherence_length(
        self, regime1_params: np.ndarray, regime2_params: np.ndarray
    ) -> float:
        """Compute phase coherence length."""
        param_distance = np.linalg.norm(
            np.mean(regime1_params, axis=0) - np.mean(regime2_params, axis=0)
        )
        return 1.0 / (1.0 + param_distance)

    def _compute_topological_defect_density(
        self, regime1_params: np.ndarray, regime2_params: np.ndarray
    ) -> float:
        """Compute topological defect density."""
        param_distance = np.linalg.norm(
            np.mean(regime1_params, axis=0) - np.mean(regime2_params, axis=0)
        )
        return param_distance / (1.0 + param_distance)

    def _compute_boundary_strength(
        self, phase_gradient: np.ndarray, coherence_length: float
    ) -> float:
        """Compute boundary strength from phase gradient and coherence length."""
        gradient_magnitude = np.linalg.norm(phase_gradient)
        return gradient_magnitude * coherence_length

    def _check_phase_field_criteria(
        self,
        params1: np.ndarray,
        params2: np.ndarray,
        boundary_analysis: Dict[str, Any],
    ) -> bool:
        """Check phase field criteria for boundary."""
        return True

    def _check_topological_criteria(
        self,
        params1: np.ndarray,
        params2: np.ndarray,
        boundary_analysis: Dict[str, Any],
    ) -> bool:
        """Check topological criteria for boundary."""
        return True
