"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core advanced FFT solver for 7D space-time.

This module implements the core advanced FFT solving functionality
for the 7D phase field theory.
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple, List, TYPE_CHECKING
import logging

from bhlff.utils.cuda_utils import get_global_backend
from ..fractional_laplacian import FractionalLaplacian
from ..spectral_operations import SpectralOperations
from ..memory_manager_7d import MemoryManager7D
from ..fft_plan_7d import FFTPlan7D
from ..spectral_coefficient_cache import SpectralCoefficientCache
from ..fft_solver_time import FFTSolverTimeMethods
from ..fft_solver_validation import FFTSolverValidation
from .fft_optimization import FFTOptimization
from .fft_adaptive import FFTAdaptive
from .fft_analysis import FFTAnalysis

if TYPE_CHECKING:
    from ...solvers.base.abstract_solver import AbstractSolver
    from ..domain import Domain
    from ..domain.parameters import Parameters


class FFTAdvancedCore:
    """
    Core advanced FFT solver for fractional Riesz operator in 7D space-time.

    Physical Meaning:
        Provides core advanced solution methods for the fractional Laplacian equation
        in 7D space-time, coordinating specialized modules for different aspects
        of advanced solving.

    Mathematical Foundation:
        Extends basic fractional Laplacian solving with:
        - Advanced optimization techniques
        - Adaptive numerical methods
        - Comprehensive validation and analysis
    """

    def __init__(self, domain: "Domain", parameters: "Parameters"):
        """
        Initialize advanced 7D FFT solver.

        Physical Meaning:
            Sets up the advanced FFT solver with all necessary components
            for optimized, adaptive, and comprehensive solving capabilities.

        Args:
            domain (Domain): 7D computational domain.
            parameters (Parameters): Solver parameters and configuration.
        """
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA backend for optimal performance
        self.backend = get_global_backend()
        self.logger.info(
            f"Using {type(self.backend).__name__} backend for FFT operations"
        )

        # Advanced solver components
        beta = getattr(parameters, "beta", 1.0)
        lambda_param = getattr(parameters, "lambda_param", 0.0)
        self.fractional_laplacian = FractionalLaplacian(domain, beta, lambda_param)
        self.spectral_operations = SpectralOperations(domain, parameters)
        max_memory_gb = getattr(parameters, "max_memory_gb", 8.0)
        self.memory_manager = MemoryManager7D(domain.shape, max_memory_gb)
        self.fft_plan = FFTPlan7D(domain, parameters)
        max_cache_size = getattr(parameters, "max_cache_size", 100)
        self.spectral_cache = SpectralCoefficientCache(max_cache_size)
        self.time_methods = FFTSolverTimeMethods(domain, parameters)
        self.validation = FFTSolverValidation(
            domain, parameters, self.fractional_laplacian
        )

        # Initialize specialized modules
        self.optimization = FFTOptimization(domain, parameters)
        self.adaptive = FFTAdaptive(domain, parameters)
        self.analysis = FFTAnalysis(domain, parameters)

        # Setup advanced components
        self._setup_advanced_components()

    def solve_optimized(self, source: np.ndarray) -> np.ndarray:
        """
        Solve using optimization techniques.

        Physical Meaning:
            Solves the fractional Laplacian equation using optimization
            techniques for improved efficiency and accuracy.

        Mathematical Foundation:
            Uses optimized spectral methods with:
            - Efficient FFT operations
            - Optimized memory usage
            - Computational optimization

        Args:
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.

        Raises:
            ValueError: If source has incompatible shape.
            RuntimeError: If optimization fails.
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.optimization.solve_optimized(source)

    def solve_adaptive(self, source: np.ndarray) -> np.ndarray:
        """
        Solve using adaptive methods.

        Physical Meaning:
            Solves the fractional Laplacian equation using adaptive
            methods for improved convergence and accuracy.

        Mathematical Foundation:
            Uses adaptive spectral methods with:
            - Dynamic refinement
            - Adaptive step size control
            - Convergence monitoring

        Args:
            source (np.ndarray): Source term in the equation.

        Returns:
            np.ndarray: Solution field.

        Raises:
            ValueError: If source has incompatible shape.
            RuntimeError: If adaptive solving fails.
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.adaptive.solve_adaptive(source)

    def solve_with_analysis(
        self, source: np.ndarray
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Solve with comprehensive analysis.

        Physical Meaning:
            Solves the fractional Laplacian equation and provides
            comprehensive analysis of the solution and solving process.

        Mathematical Foundation:
            Combines solving with analysis including:
            - Solution quality assessment
            - Convergence analysis
            - Performance metrics

        Args:
            source (np.ndarray): Source term in the equation.

        Returns:
            Tuple[np.ndarray, Dict[str, Any]]: Solution field and analysis results.

        Raises:
            ValueError: If source has incompatible shape.
            RuntimeError: If solving or analysis fails.
        """
        if source.shape != self.domain.shape:
            raise ValueError(
                f"Source shape {source.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.analysis.solve_with_analysis(source)

    def solve_time_evolution(
        self, initial_condition: np.ndarray, time_steps: int
    ) -> List[np.ndarray]:
        """
        Solve time evolution of the system.

        Physical Meaning:
            Solves the time evolution of the fractional Laplacian equation
            starting from an initial condition.

        Mathematical Foundation:
            Uses time integration methods with:
            - Adaptive time stepping
            - Stability control
            - Conservation properties

        Args:
            initial_condition (np.ndarray): Initial field configuration.
            time_steps (int): Number of time steps to compute.

        Returns:
            List[np.ndarray]: List of field configurations at each time step.

        Raises:
            ValueError: If initial condition has incompatible shape.
            RuntimeError: If time evolution fails.
        """
        if initial_condition.shape != self.domain.shape:
            raise ValueError(
                f"Initial condition shape {initial_condition.shape} incompatible with domain shape {self.domain.shape}"
            )

        return self.time_methods.solve_time_evolution(initial_condition, time_steps)

    def validate_solution_comprehensive(
        self, solution: np.ndarray, source: np.ndarray
    ) -> Dict[str, Any]:
        """
        Perform comprehensive solution validation.

        Physical Meaning:
            Performs comprehensive validation of the solution including
            accuracy, stability, and physical reasonableness checks.

        Mathematical Foundation:
            Validates solution using:
            - Residual analysis
            - Conservation checks
            - Stability analysis
            - Physical constraints

        Args:
            solution (np.ndarray): Solution field to validate.
            source (np.ndarray): Original source term.

        Returns:
            Dict[str, Any]: Comprehensive validation results.

        Raises:
            ValueError: If solution or source have incompatible shapes.
        """
        if solution.shape != self.domain.shape or source.shape != self.domain.shape:
            raise ValueError(
                "Solution and source must have compatible shapes with domain"
            )

        return self.validation.validate_solution_comprehensive(solution, source)

    def _setup_advanced_components(self) -> None:
        """
        Setup advanced solver components.

        Physical Meaning:
            Initializes all advanced components including spectral coefficients,
            FFT plans, optimization settings, and adaptive methods.
        """
        self._setup_spectral_coefficients()
        self._setup_fft_plan()
        self._setup_optimization()
        self._setup_adaptive_methods()

    def _setup_spectral_coefficients(self) -> None:
        """Setup spectral coefficients for advanced solving."""
        # Spectral coefficients are computed on-demand in SpectralCoefficientCache
        self.spectral_coefficients = self.spectral_cache.get_coefficients(
            self.parameters.mu,
            self.parameters.beta,
            self.parameters.lambda_param,
            self.domain.shape,
        )

    def _setup_fft_plan(self) -> None:
        """Setup FFT plan for advanced solving."""
        # FFT plans are already set up in FFTPlan7D constructor
        self.fft_plan.setup_optimized_plans(
            precision=getattr(self.parameters, "precision", "float64"),
            plan_type=getattr(self.parameters, "fft_plan_type", "MEASURE"),
        )

    def _setup_optimization(self) -> None:
        """Setup optimization components."""
        self.optimization.setup_optimization()

    def _setup_adaptive_methods(self) -> None:
        """Setup adaptive methods."""
        self.adaptive.setup_adaptive_methods()
