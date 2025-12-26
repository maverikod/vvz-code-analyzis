"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for nonlinear mode analysis.
"""

from typing import Dict, Any

from .mode_analysis_base import NonlinearModeAnalyzerBase
from .mode_analysis_setup import NonlinearModeAnalyzerSetup
from .mode_analysis_corrections import NonlinearModeAnalyzerCorrections


class NonlinearModeAnalyzer(NonlinearModeAnalyzerBase):
    """
    Nonlinear mode analysis for collective systems.

    Physical Meaning:
        Analyzes nonlinear modes in collective systems,
        including mode finding, stability analysis, and
        mode interactions.

    Mathematical Foundation:
        Implements nonlinear mode analysis methods:
        - Mode finding algorithms
        - Stability analysis
        - Mode interaction analysis
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize nonlinear mode analyzer."""
        super().__init__(system, nonlinear_params)
        
        # Initialize mode analysis methods
        setup = NonlinearModeAnalyzerSetup(self.nonlinear_params)
        methods = setup.initialize_mode_methods()
        self.mode_finder = methods["mode_finder"]
        self.mode_stability = methods["mode_stability"]
        self.mode_interactions = methods["mode_interactions"]
        
        self._corrections = NonlinearModeAnalyzerCorrections(self.nonlinear_params)

    def find_nonlinear_modes(self) -> Dict[str, Any]:
        """
        Find nonlinear modes in the system.

        Physical Meaning:
            Identifies nonlinear collective modes that
            arise from nonlinear interactions.

        Returns:
            Dict containing:
                - frequencies: ω_n (nonlinear mode frequencies)
                - amplitudes: A_n (mode amplitudes)
                - stability: stability analysis
                - bifurcations: bifurcation points
        """
        # Get linear modes first
        linear_modes = self.system.find_collective_modes()

        # Find nonlinear corrections
        nonlinear_corrections = self._corrections.compute_nonlinear_corrections(linear_modes)

        # Find bifurcation points
        bifurcations = self._corrections.find_bifurcation_points()

        # Analyze stability
        stability = self._corrections.analyze_nonlinear_stability()

        return {
            "linear_frequencies": linear_modes["frequencies"],
            "nonlinear_frequencies": nonlinear_corrections["frequencies"],
            "amplitudes": nonlinear_corrections["amplitudes"],
            "stability": stability,
            "bifurcations": bifurcations,
        }

