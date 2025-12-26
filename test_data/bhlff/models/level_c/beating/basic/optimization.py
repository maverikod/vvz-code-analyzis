"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Beating optimization module.

This module implements optimization functionality
for analyzing mode beating in the 7D phase field according to the
theoretical framework.

Physical Meaning:
    Implements optimization of beating analysis parameters
    to improve accuracy and reliability of detected patterns.

Example:
    >>> optimizer = BeatingOptimizer(bvp_core)
    >>> results = optimizer.optimize_analysis(envelope, results)
"""

import numpy as np
from typing import Dict, Any, List, Tuple
import logging

from bhlff.core.bvp import BVPCore
from .optimization_parameters import BeatingParameterOptimizer
from .optimization_thresholds import BeatingThresholdOptimizer
from .optimization_methods import BeatingMethodOptimizer


class BeatingOptimizer:
    """
    Beating optimization for Level C.

    Physical Meaning:
        Optimizes beating analysis parameters to improve
        accuracy and reliability of detected patterns.

    Mathematical Foundation:
        Implements optimization methods for beating analysis:
        - Parameter optimization using gradient-based methods
        - Global optimization using evolutionary algorithms
        - Multi-objective optimization for conflicting goals
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize beating optimizer.

        Physical Meaning:
            Sets up the optimization system with
            optimization parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Optimization parameters
        self.optimization_enabled = True
        self.optimization_method = "L-BFGS-B"
        self.max_iterations = 1000
        self.tolerance = 1e-8

        # Initialize optimization components
        self._parameter_optimizer = BeatingParameterOptimizer(bvp_core)
        self._threshold_optimizer = BeatingThresholdOptimizer(bvp_core)
        self._method_optimizer = BeatingMethodOptimizer(bvp_core)

    def optimize_analysis(
        self, envelope: np.ndarray, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Optimize analysis.

        Physical Meaning:
            Performs comprehensive optimization of beating analysis
            including parameter optimization, threshold optimization,
            and method optimization.

        Mathematical Foundation:
            Implements optimization methods for beating analysis:
            - Parameter optimization using gradient-based methods
            - Global optimization using evolutionary algorithms
            - Multi-objective optimization for conflicting goals

        Args:
            envelope (np.ndarray): 7D envelope field data.
            results (Dict[str, Any]): Current analysis results.

        Returns:
            Dict[str, Any]: Optimization results including:
                - parameter_optimization: Parameter optimization results
                - threshold_optimization: Threshold optimization results
                - method_optimization: Method optimization results
        """
        self.logger.info("Starting comprehensive optimization")

        # Optimize parameters
        parameter_optimization = self._parameter_optimizer.optimize_parameters(
            envelope, results
        )

        # Optimize thresholds
        threshold_optimization = self._threshold_optimizer.optimize_thresholds(
            envelope, results
        )

        # Optimize methods
        method_optimization = self._method_optimizer.optimize_methods(envelope, results)

        # Combine all optimization results
        optimization_results = {
            "parameter_optimization": parameter_optimization,
            "threshold_optimization": threshold_optimization,
            "method_optimization": method_optimization,
            "optimization_complete": True,
        }

        self.logger.info("Comprehensive optimization completed")
        return optimization_results
