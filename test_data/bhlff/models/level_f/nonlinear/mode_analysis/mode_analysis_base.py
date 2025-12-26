"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base initialization for nonlinear mode analysis.
"""

from typing import Dict, Any


class NonlinearModeAnalyzerBase:
    """
    Base class for nonlinear mode analysis initialization.

    Physical Meaning:
        Provides base initialization for nonlinear mode analysis
        with system and parameters.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """
        Initialize nonlinear mode analyzer.

        Physical Meaning:
            Sets up the nonlinear mode analysis system with
            nonlinear parameters and analysis methods.

        Args:
            system: Multi-particle system
            nonlinear_params (Dict[str, Any]): Nonlinear parameters
        """
        # Initialize base class
        self.system = system
        self.nonlinear_params = nonlinear_params

        # Mode analysis parameters
        self.mode_tolerance = nonlinear_params.get("mode_tolerance", 1e-6)
        self.max_modes = nonlinear_params.get("max_modes", 10)
        self.stability_threshold = nonlinear_params.get("stability_threshold", 0.1)

