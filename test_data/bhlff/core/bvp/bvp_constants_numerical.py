"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Numerical constants and solver parameters for BVP system.

This module defines numerical solver parameters, quench detection thresholds,
and impedance calculation parameters for the BVP system.

Physical Meaning:
    Contains numerical parameters for:
    - Newton-Raphson solver configuration
    - Quench detection thresholds
    - Impedance calculation parameters
    - Line search algorithms

Mathematical Foundation:
    Defines numerical parameters for:
    - Solver convergence criteria
    - Threshold values for physical phenomena
    - Signal processing parameters

Example:
    >>> constants = BVPConstantsNumerical()
    >>> max_iter = constants.get_numerical_parameter('max_iterations')
    >>> threshold = constants.get_quench_threshold('amplitude_threshold')
"""

from typing import Dict, Any

from .bvp_constants_base import BVPConstantsBase


class BVPConstantsNumerical(BVPConstantsBase):
    """
    Numerical constants and solver parameters for BVP system.

    Physical Meaning:
        Extends base constants with numerical solver parameters,
        quench detection thresholds, and impedance calculation parameters.

    Mathematical Foundation:
        Defines numerical parameters for:
        - Solver convergence criteria
        - Threshold values for physical phenomena
        - Signal processing parameters
    """

    def __init__(self, config: Dict[str, Any] = None) -> None:
        """
        Initialize numerical BVP constants.

        Physical Meaning:
            Sets up numerical solver parameters, quench detection thresholds,
            and impedance calculation parameters.

        Args:
            config (Dict[str, Any], optional): Configuration to override defaults.
        """
        super().__init__(config)
        self._setup_numerical_constants()
        self._setup_quench_constants()
        self._setup_impedance_constants()

    def _setup_numerical_constants(self) -> None:
        """Setup numerical solver constants."""
        numerical_config = self.config.get("numerical_parameters", {})

        # Newton-Raphson solver parameters
        self.MAX_ITERATIONS = numerical_config.get("max_iterations", 50)
        self.TOLERANCE = numerical_config.get("tolerance", 1e-8)
        self.DAMPING_FACTOR = numerical_config.get("damping_factor", 0.8)
        self.MIN_STEP_SIZE = numerical_config.get("min_step_size", 1e-12)

        # Finite difference parameters
        self.FINITE_DIFF_STEP = numerical_config.get("finite_diff_step", 1e-8)
        self.REGULARIZATION = numerical_config.get("regularization", 1e-12)

        # Line search parameters
        self.LINE_SEARCH_MAX_ITER = numerical_config.get("line_search_max_iter", 20)
        self.LINE_SEARCH_BETA = numerical_config.get("line_search_beta", 0.5)
        self.LINE_SEARCH_GAMMA = numerical_config.get("line_search_gamma", 1e-4)
        self.ARMIJO_C1 = numerical_config.get("armijo_c1", 1e-4)
        self.CURVATURE_C2 = numerical_config.get("curvature_c2", 0.9)

        # Gradient descent fallback
        self.GRADIENT_DESCENT_STEP = numerical_config.get("gradient_descent_step", 0.1)

        # Memory protection
        self.MEMORY_THRESHOLD = numerical_config.get("memory_threshold", 0.8)

    def _setup_quench_constants(self) -> None:
        """Setup quench detection constants."""
        quench_config = self.config.get("quench_detection", {})

        # Quench detection thresholds
        self.AMPLITUDE_THRESHOLD = quench_config.get("amplitude_threshold", 0.8)
        self.DETUNING_THRESHOLD = quench_config.get("detuning_threshold", 0.1)
        self.GRADIENT_THRESHOLD = quench_config.get("gradient_threshold", 0.5)

    def _setup_impedance_constants(self) -> None:
        """Setup impedance calculation constants."""
        impedance_config = self.config.get("impedance_calculation", {})

        # Frequency analysis parameters
        self.FREQUENCY_RANGE = impedance_config.get("frequency_range", (0.1, 10.0))
        self.FREQUENCY_POINTS = impedance_config.get("frequency_points", 1000)
        self.BOUNDARY_CONDITIONS = impedance_config.get(
            "boundary_conditions", "periodic"
        )

        # Quality factor parameters
        self.QUALITY_FACTOR_THRESHOLD = impedance_config.get(
            "quality_factor_threshold", 0.1
        )
        self.MIN_QUALITY_FACTOR = impedance_config.get("min_quality_factor", 1.0)
        self.MAX_QUALITY_FACTOR = impedance_config.get("max_quality_factor", 1000.0)

        # Peak detection parameters
        self.PROMINENCE_THRESHOLD_MULTIPLIER = impedance_config.get(
            "prominence_threshold_multiplier", 2.0
        )
        self.PHASE_THRESHOLD_MULTIPLIER = impedance_config.get(
            "phase_threshold_multiplier", 2.0
        )
        self.PEAK_WINDOW_SIZE = impedance_config.get("peak_window_size", 20)
        self.SMOOTHING_WINDOW_SIZE = impedance_config.get("smoothing_window_size", 5)

    def get_numerical_parameter(self, parameter_name: str) -> float:
        """
        Get numerical solver parameter.

        Args:
            parameter_name (str): Name of the numerical parameter.

        Returns:
            float: Parameter value.
        """
        parameter_map = {
            "max_iterations": self.MAX_ITERATIONS,
            "tolerance": self.TOLERANCE,
            "damping_factor": self.DAMPING_FACTOR,
            "min_step_size": self.MIN_STEP_SIZE,
            "finite_diff_step": self.FINITE_DIFF_STEP,
            "regularization": self.REGULARIZATION,
            "line_search_max_iter": self.LINE_SEARCH_MAX_ITER,
            "line_search_beta": self.LINE_SEARCH_BETA,
            "line_search_gamma": self.LINE_SEARCH_GAMMA,
            "armijo_c1": self.ARMIJO_C1,
            "curvature_c2": self.CURVATURE_C2,
            "gradient_descent_step": self.GRADIENT_DESCENT_STEP,
            "memory_threshold": getattr(self, "MEMORY_THRESHOLD", 0.8),
        }
        return parameter_map.get(parameter_name, 0.0)

    def get_quench_threshold(self, threshold_name: str) -> float:
        """
        Get quench detection threshold.

        Args:
            threshold_name (str): Name of the threshold.

        Returns:
            float: Threshold value.
        """
        threshold_map = {
            "amplitude_threshold": self.AMPLITUDE_THRESHOLD,
            "detuning_threshold": self.DETUNING_THRESHOLD,
            "gradient_threshold": self.GRADIENT_THRESHOLD,
        }
        return threshold_map.get(threshold_name, 0.0)

    def get_impedance_parameter(self, parameter_name: str) -> Any:
        """
        Get impedance calculation parameter.

        Args:
            parameter_name (str): Name of the impedance parameter.

        Returns:
            Any: Parameter value.
        """
        parameter_map = {
            "frequency_range": self.FREQUENCY_RANGE,
            "frequency_points": self.FREQUENCY_POINTS,
            "boundary_conditions": self.BOUNDARY_CONDITIONS,
            "quality_factor_threshold": self.QUALITY_FACTOR_THRESHOLD,
            "min_quality_factor": self.MIN_QUALITY_FACTOR,
            "max_quality_factor": self.MAX_QUALITY_FACTOR,
            "prominence_threshold_multiplier": self.PROMINENCE_THRESHOLD_MULTIPLIER,
            "phase_threshold_multiplier": self.PHASE_THRESHOLD_MULTIPLIER,
            "peak_window_size": self.PEAK_WINDOW_SIZE,
            "smoothing_window_size": self.SMOOTHING_WINDOW_SIZE,
        }
        return parameter_map.get(parameter_name, None)

    def __repr__(self) -> str:
        """String representation of numerical BVP constants."""
        return (
            f"BVPConstantsNumerical(carrier_freq={self.CARRIER_FREQUENCY}, "
            f"max_iter={self.MAX_ITERATIONS}, tolerance={self.TOLERANCE})"
        )
