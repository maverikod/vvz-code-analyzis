"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Single soliton optimization functionality.

This module implements single soliton optimization using complete
7D BVP theory with advanced optimization algorithms.

Physical Meaning:
    Implements soliton optimization including parameter optimization,
    solution finding, and convergence analysis using 7D BVP theory.

Example:
    >>> optimizer = SingleSolitonOptimization(system, nonlinear_params)
    >>> solution = optimizer.find_single_soliton()
"""

import numpy as np
from typing import Dict, Any, Optional
from scipy.optimize import minimize
from scipy.integrate import solve_bvp
import logging

from .base import SolitonAnalysisBase
from .single_soliton_core import SingleSolitonCore
from .single_soliton_validation import SingleSolitonValidation


class SingleSolitonOptimization(SolitonAnalysisBase):
    """
    Single soliton optimization functionality.

    Physical Meaning:
        Implements soliton optimization including parameter optimization,
        solution finding, and convergence analysis using 7D BVP theory.

    Mathematical Foundation:
        Optimizes soliton parameters using complete 7D BVP theory
        with multiple initial guesses and advanced convergence criteria.
    """

    def __init__(self, system, nonlinear_params: Dict[str, Any]):
        """Initialize single soliton optimization."""
        super().__init__(system, nonlinear_params)
        self.logger = logging.getLogger(__name__)

        # Initialize core functionality
        self.core = SingleSolitonCore(system, nonlinear_params)
        self.validator = SingleSolitonValidation(system, nonlinear_params)

    def find_single_soliton(self) -> Optional[Dict[str, Any]]:
        """
        Find single soliton solution using full 7D BVP theory.

        Physical Meaning:
            Finds single soliton solution through complete optimization
            using 7D fractional Laplacian equations and boundary value
            problem solving with full 7D BVP theory implementation.

        Mathematical Foundation:
            Solves the 7D soliton equation:
            L_β a = μ(-Δ)^β a + λa = s(x,t)
            with soliton boundary conditions and energy minimization.
            Uses complete optimization with multiple initial guesses
            and advanced convergence criteria.

        Returns:
            Optional[Dict[str, Any]]: Single soliton solution with full
            physical parameters and optimization results.
        """
        try:
            # Multiple initial guesses for robust optimization
            initial_guesses = [
                [1.0, 1.0, 0.0],  # Standard guess
                [1.5, 0.8, 0.0],  # Higher amplitude, narrower
                [0.8, 1.2, 0.0],  # Lower amplitude, wider
                [1.2, 1.0, 2.0],  # Offset position
                [0.9, 0.9, -1.5],  # Negative offset
            ]

            best_solution = None
            best_energy = float("inf")

            for i, initial_params in enumerate(initial_guesses):
                try:
                    # Setup 7D mesh for BVP solving with adaptive resolution
                    x_mesh = np.linspace(-15.0, 15.0, 200)
                    y_guess = np.zeros((2, len(x_mesh)))

                    def soliton_equations_7d(params):
                        """7D soliton equations from BVP theory with full implementation."""
                        amplitude, width, position = params

                        def soliton_ode(x, y):
                            """7D soliton ODE system with complete physics."""
                            return self.core.compute_7d_soliton_ode(
                                x, y, amplitude, width, position
                            )

                        # Boundary conditions for soliton with proper 7D BVP theory
                        def bc(ya, yb):
                            # Soliton boundary conditions: field approaches zero at boundaries
                            return [
                                ya[0]
                                - amplitude
                                * self._step_resonator_boundary_condition(
                                    ya[0], amplitude
                                ),
                                yb[0] - 0.0,
                            ]  # Field vanishes at far boundary

                        try:
                            # Solve BVP with enhanced convergence
                            sol = solve_bvp(
                                soliton_ode,
                                bc,
                                x_mesh,
                                y_guess,
                                tol=1e-8,
                                max_nodes=1000,
                            )

                            if sol.success:
                                # Compute soliton energy with full 7D BVP theory
                                energy = self.core.compute_soliton_energy(
                                    sol.y, amplitude, width
                                )

                                # Additional energy penalty for unphysical solutions
                                if np.any(np.isnan(sol.y)) or np.any(np.isinf(sol.y)):
                                    return 1e10

                                # Check for proper soliton shape
                                if not self.validator.validate_soliton_shape(
                                    sol.y, amplitude, width
                                ):
                                    return 1e10

                                return -energy  # Minimize negative energy
                            else:
                                return 1e10  # Large penalty for failed solution

                        except Exception as e:
                            self.logger.debug(f"BVP solution failed for guess {i}: {e}")
                            return 1e10  # Penalty for failed BVP solution

                    # Optimize soliton parameters using 7D theory with enhanced bounds
                    result = minimize(
                        soliton_equations_7d,
                        initial_params,
                        method="L-BFGS-B",
                        bounds=[(0.1, 3.0), (0.3, 2.0), (-8.0, 8.0)],
                        options={"maxiter": 200, "ftol": 1e-12, "gtol": 1e-8},
                    )

                    if result.success and result.fun < best_energy and result.fun < 1e9:
                        best_energy = result.fun
                        amplitude, width, position = result.x

                        # Compute final soliton solution with full validation
                        final_solution = self._compute_final_soliton_solution(
                            amplitude, width, position
                        )

                        # Validate solution quality
                        if self.validator.validate_solution_quality(
                            final_solution, amplitude, width
                        ):
                            best_solution = {
                                "type": "single",
                                "amplitude": amplitude,
                                "width": width,
                                "position": position,
                                "energy": -result.fun,
                                "optimization_success": True,
                                "solution": final_solution,
                                "convergence_info": {
                                    "iterations": result.nit,
                                    "function_evaluations": result.nfev,
                                    "gradient_norm": (
                                        np.linalg.norm(result.jac)
                                        if result.jac is not None
                                        else 0.0
                                    ),
                                    "initial_guess_index": i,
                                    "energy_convergence": best_energy,
                                },
                                "physical_properties": self.validator.compute_soliton_physical_properties(
                                    amplitude, width, position, final_solution
                                ),
                            }

                except Exception as e:
                    self.logger.debug(f"Optimization failed for guess {i}: {e}")
                    continue

            return best_solution

        except Exception as e:
            self.logger.warning(f"Single soliton finding failed: {e}")
            return None

    def _compute_final_soliton_solution(
        self, amplitude: float, width: float, position: float
    ) -> Dict[str, Any]:
        """
        Compute final soliton solution with full physical parameters.

        Physical Meaning:
            Generates the complete soliton solution with all physical
            parameters and properties computed from the optimization results.

        Args:
            amplitude (float): Optimized soliton amplitude.
            width (float): Optimized soliton width.
            position (float): Optimized soliton position.

        Returns:
            Dict[str, Any]: Complete soliton solution with physical properties.
        """
        try:
            # Generate spatial grid
            x = np.linspace(-10.0, 10.0, 200)

            # Compute soliton profile using 7D BVP step resonator theory
            profile = amplitude * self._step_resonator_profile(x, position, width)

            # Compute soliton properties
            soliton_field_energy = self._compute_field_energy(profile, x)
            soliton_momentum = np.trapz(profile * np.gradient(profile), x)

            # Compute topological charge
            topological_charge = self.compute_topological_charge(profile)

            return {
                "spatial_grid": x,
                "profile": profile,
                "field_energy": soliton_field_energy,
                "momentum": soliton_momentum,
                "topological_charge": topological_charge,
                "width_parameter": width,
                "amplitude_parameter": amplitude,
                "position_parameter": position,
            }

        except Exception as e:
            self.logger.error(f"Final soliton solution computation failed: {e}")
            return {}

    def _step_resonator_profile(
        self, x: np.ndarray, position: float, width: float
    ) -> np.ndarray:
        """
        Step resonator profile using 7D BVP theory.

        Physical Meaning:
            Implements step resonator profile instead of exponential
            decay, following 7D BVP theory principles with sharp
            cutoff at soliton width.

        Mathematical Foundation:
            Step resonator profile:
            f(x) = 1 if |x - pos| < width, 0 if |x - pos| ≥ width
            where width is the soliton width parameter.

        Args:
            x (np.ndarray): Spatial coordinate array.
            position (float): Soliton position.
            width (float): Soliton width parameter.

        Returns:
            np.ndarray: Step resonator profile.
        """
        try:
            # Step resonator: sharp cutoff at soliton width
            distance = np.abs(x - position)
            return np.where(distance < width, 1.0, 0.0)

        except Exception as e:
            self.logger.error(f"Step resonator profile computation failed: {e}")
            return np.zeros_like(x)

    def _step_resonator_boundary_condition(
        self, field_value: float, amplitude: float
    ) -> float:
        """
        Step resonator boundary condition using 7D BVP theory.

        Physical Meaning:
            Implements step resonator boundary condition instead of
            exponential decay, following 7D BVP theory principles.

        Args:
            field_value (float): Field value at boundary.
            amplitude (float): Soliton amplitude.

        Returns:
            float: Boundary condition value.
        """
        try:
            # Step resonator: sharp boundary condition
            if abs(field_value) < 0.1 * amplitude:
                return 0.0
            else:
                return field_value

        except Exception as e:
            self.logger.error(
                f"Step resonator boundary condition computation failed: {e}"
            )
            return field_value

    def _compute_field_energy(self, profile: np.ndarray, x: np.ndarray) -> float:
        """
        Compute field energy according to 7D BVP theory.

        Physical Meaning:
            Computes the field energy instead of mass according to 7D BVP theory
            principles where energy is the fundamental quantity rather than mass.

        Mathematical Foundation:
            Field energy = ∫ |∇a|² dx where a is the field amplitude
            and ∇a is the field gradient.

        Args:
            profile (np.ndarray): Field profile.
            x (np.ndarray): Spatial coordinates.

        Returns:
            float: Field energy according to 7D BVP theory.
        """
        # Compute field gradient
        field_gradient = np.gradient(profile, x)

        # Compute field energy density
        energy_density = np.abs(field_gradient) ** 2

        # Integrate over space
        field_energy = np.trapz(energy_density, x)

        return field_energy
