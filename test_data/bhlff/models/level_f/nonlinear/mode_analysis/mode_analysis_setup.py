"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Mode analysis setup methods.
"""

from typing import Dict, Any


class NonlinearModeAnalyzerSetup:
    """
    Mode analysis setup methods.

    Physical Meaning:
        Provides methods to setup mode analysis methods
        based on nonlinear type.
    """

    def __init__(self, nonlinear_params: Dict[str, Any]):
        """
        Initialize setup manager.

        Args:
            nonlinear_params (Dict[str, Any]): Nonlinear parameters.
        """
        self.nonlinear_params = nonlinear_params

    def initialize_mode_methods(self) -> Dict[str, Any]:
        """
        Initialize mode analysis methods.

        Physical Meaning:
            Initializes the methods for nonlinear mode analysis
            based on the nonlinear type.

        Returns:
            Dict[str, Any]: Dictionary with mode_finder, mode_stability,
                and mode_interactions methods.
        """
        # Set up mode analysis based on nonlinear type
        nonlinear_type = self.nonlinear_params.get("type", "cubic")

        if nonlinear_type == "cubic":
            return self._setup_cubic_mode_analysis()
        elif nonlinear_type == "quartic":
            return self._setup_quartic_mode_analysis()
        elif nonlinear_type == "sine_gordon":
            return self._setup_sine_gordon_mode_analysis()
        else:
            raise ValueError(f"Unknown nonlinear type: {nonlinear_type}")

    def _setup_cubic_mode_analysis(self) -> Dict[str, Any]:
        """
        Setup cubic mode analysis.

        Physical Meaning:
            Sets up analysis methods for cubic nonlinear modes.

        Returns:
            Dict[str, Any]: Methods for cubic mode analysis.
        """
        from .mode_analysis_mode_finding import NonlinearModeAnalyzerModeFinding
        from .mode_analysis_stability import NonlinearModeAnalyzerStability
        from .mode_analysis_interactions import NonlinearModeAnalyzerInteractions

        mode_finder_obj = NonlinearModeAnalyzerModeFinding(self.nonlinear_params)
        stability_obj = NonlinearModeAnalyzerStability(self.nonlinear_params)
        interactions_obj = NonlinearModeAnalyzerInteractions(self.nonlinear_params)

        return {
            "mode_finder": mode_finder_obj.find_cubic_modes,
            "mode_stability": stability_obj.analyze_cubic_mode_stability,
            "mode_interactions": interactions_obj.analyze_cubic_mode_interactions,
        }

    def _setup_quartic_mode_analysis(self) -> Dict[str, Any]:
        """
        Setup quartic mode analysis.

        Physical Meaning:
            Sets up analysis methods for quartic nonlinear modes.

        Returns:
            Dict[str, Any]: Methods for quartic mode analysis.
        """
        from .mode_analysis_mode_finding import NonlinearModeAnalyzerModeFinding
        from .mode_analysis_stability import NonlinearModeAnalyzerStability
        from .mode_analysis_interactions import NonlinearModeAnalyzerInteractions

        mode_finder_obj = NonlinearModeAnalyzerModeFinding(self.nonlinear_params)
        stability_obj = NonlinearModeAnalyzerStability(self.nonlinear_params)
        interactions_obj = NonlinearModeAnalyzerInteractions(self.nonlinear_params)

        return {
            "mode_finder": mode_finder_obj.find_quartic_modes,
            "mode_stability": stability_obj.analyze_quartic_mode_stability,
            "mode_interactions": interactions_obj.analyze_quartic_mode_interactions,
        }

    def _setup_sine_gordon_mode_analysis(self) -> Dict[str, Any]:
        """
        Setup sine-Gordon mode analysis.

        Physical Meaning:
            Sets up analysis methods for sine-Gordon nonlinear modes.

        Returns:
            Dict[str, Any]: Methods for sine-Gordon mode analysis.
        """
        from .mode_analysis_mode_finding import NonlinearModeAnalyzerModeFinding
        from .mode_analysis_stability import NonlinearModeAnalyzerStability
        from .mode_analysis_interactions import NonlinearModeAnalyzerInteractions

        mode_finder_obj = NonlinearModeAnalyzerModeFinding(self.nonlinear_params)
        stability_obj = NonlinearModeAnalyzerStability(self.nonlinear_params)
        interactions_obj = NonlinearModeAnalyzerInteractions(self.nonlinear_params)

        return {
            "mode_finder": mode_finder_obj.find_sine_gordon_modes,
            "mode_stability": stability_obj.analyze_sine_gordon_mode_stability,
            "mode_interactions": interactions_obj.analyze_sine_gordon_mode_interactions,
        }

