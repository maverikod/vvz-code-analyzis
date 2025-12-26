"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Three-soliton optimization methods for multi-soliton optimization.

This module provides three-soliton optimization methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List
from scipy.optimize import minimize
from scipy.integrate import solve_bvp


class MultiSolitonOptimizationThreeMixin:
    """Mixin providing three-soliton optimization methods."""
    
    def find_three_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find three-soliton solutions using full 7D BVP theory.
        
        Physical Meaning:
            Finds three-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and multi-soliton
            interaction potentials with full 7D BVP theory implementation.
            
        Returns:
            List[Dict[str, Any]]: Three-soliton solutions with full
            interaction analysis and stability properties.
        """
        try:
            solutions = []
            
            # Multiple initial guesses for robust optimization
            initial_guesses = [
                [1.0, 1.0, -4.0, 1.0, 1.0, 0.0, 1.0, 1.0, 4.0],  # Standard triangular
                [
                    1.2,
                    0.8,
                    -3.0,
                    0.8,
                    1.2,
                    0.0,
                    1.0,
                    0.9,
                    3.0,
                ],  # Different amplitudes/widths
                [0.9, 1.1, -5.0, 1.1, 0.9, 0.0, 0.8, 1.0, 5.0],  # Wider separation
                [1.1, 0.9, -2.0, 0.9, 1.1, 0.0, 1.2, 0.8, 2.0],  # Closer separation
                [1.3, 0.7, -3.5, 0.7, 1.3, 0.0, 0.9, 1.1, 3.5],  # Asymmetric
            ]
            
            best_solution = None
            best_energy = float("inf")
            
            for i, initial_params in enumerate(initial_guesses):
                try:
                    # Setup 7D mesh for BVP solving with adaptive resolution
                    x_mesh = np.linspace(-25.0, 25.0, 400)
                    y_guess = np.zeros((2, len(x_mesh)))
                    
                    def three_soliton_equations_7d(params):
                        """7D three-soliton equations with full interaction physics."""
                        amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3 = (
                            params
                        )
                        
                        def three_soliton_ode(x, y):
                            """7D three-soliton ODE system with complete interactions."""
                            return self.core.compute_7d_three_soliton_ode(
                                x,
                                y,
                                amp1,
                                width1,
                                pos1,
                                amp2,
                                width2,
                                pos2,
                                amp3,
                                width3,
                                pos3,
                            )
                        
                        # Enhanced boundary conditions for three solitons
                        def bc(ya, yb):
                            # Soliton boundary conditions with proper 7D BVP theory
                            return [
                                ya[0]
                                - amp1
                                * self._step_resonator_boundary_condition(ya[0], amp1),
                                yb[0]
                                - amp3
                                * self._step_resonator_boundary_condition(yb[0], amp3),
                            ]
                        
                        try:
                            # Solve BVP with enhanced convergence
                            sol = solve_bvp(
                                three_soliton_ode,
                                bc,
                                x_mesh,
                                y_guess,
                                tol=1e-8,
                                max_nodes=2000,
                            )
                            
                            if sol.success:
                                # Compute total energy including all interactions
                                energy = self.core.compute_three_soliton_energy(
                                    sol.y,
                                    amp1,
                                    width1,
                                    pos1,
                                    amp2,
                                    width2,
                                    pos2,
                                    amp3,
                                    width3,
                                    pos3,
                                )
                                
                                # Additional energy penalty for unphysical solutions
                                if np.any(np.isnan(sol.y)) or np.any(np.isinf(sol.y)):
                                    return 1e10
                                
                                # Check for proper three-soliton shape
                                if not self.validator.validate_three_soliton_shape(
                                    sol.y, amp1, width1, amp2, width2, amp3, width3
                                ):
                                    return 1e10
                                
                                return -energy  # Minimize negative energy
                            else:
                                return 1e10  # Large penalty for failed solution
                        
                        except Exception as e:
                            self.logger.debug(
                                f"BVP solution failed for three-soliton guess {i}: {e}"
                            )
                            return 1e10  # Penalty for failed BVP solution
                    
                    # Optimize three-soliton parameters using 7D theory with enhanced bounds
                    result = minimize(
                        three_soliton_equations_7d,
                        initial_params,
                        method="L-BFGS-B",
                        bounds=[
                            (0.1, 3.0),
                            (0.3, 2.0),
                            (-15.0, 15.0),
                            (0.1, 3.0),
                            (0.3, 2.0),
                            (-15.0, 15.0),
                            (0.1, 3.0),
                            (0.3, 2.0),
                            (-15.0, 15.0),
                        ],
                        options={"maxiter": 300, "ftol": 1e-12, "gtol": 1e-8},
                    )
                    
                    if result.success and result.fun < best_energy and result.fun < 1e9:
                        best_energy = result.fun
                        amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3 = (
                            result.x
                        )
                        
                        # Compute final three-soliton solution with full validation
                        final_solution = self._compute_final_three_soliton_solution(
                            amp1, width1, pos1, amp2, width2, pos2, amp3, width3, pos3
                        )
                        
                        # Validate solution quality
                        if self.validator.validate_three_soliton_solution_quality(
                            final_solution, amp1, width1, amp2, width2, amp3, width3
                        ):
                            best_solution = {
                                "type": "multi",
                                "num_solitons": 3,
                                "soliton_1": {
                                    "amplitude": amp1,
                                    "width": width1,
                                    "position": pos1,
                                },
                                "soliton_2": {
                                    "amplitude": amp2,
                                    "width": width2,
                                    "position": pos2,
                                },
                                "soliton_3": {
                                    "amplitude": amp3,
                                    "width": width3,
                                    "position": pos3,
                                },
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
                                "physical_properties": self.validator.compute_three_soliton_physical_properties(
                                    amp1,
                                    width1,
                                    pos1,
                                    amp2,
                                    width2,
                                    pos2,
                                    amp3,
                                    width3,
                                    pos3,
                                    final_solution,
                                ),
                            }
                
                except Exception as e:
                    self.logger.debug(
                        f"Three-soliton optimization failed for guess {i}: {e}"
                    )
                    continue
            
            if best_solution:
                solutions.append(best_solution)
            
            return solutions
        
        except Exception as e:
            self.logger.warning(f"Three-soliton finding failed: {e}")
            return []
    
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
        """
        Compute final three-soliton solution with full physical parameters.
        
        Physical Meaning:
            Generates the complete three-soliton solution with all physical
            parameters and properties computed from the optimization results.
            
        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            amp3, width3, pos3 (float): Third soliton parameters.
            
        Returns:
            Dict[str, Any]: Complete three-soliton solution with physical properties.
        """
        try:
            # Generate spatial grid
            x = np.linspace(-20.0, 20.0, 400)
            
            # Compute individual soliton profiles using 7D BVP step resonator theory
            profile1 = amp1 * self._step_resonator_profile(x, pos1, width1)
            profile2 = amp2 * self._step_resonator_profile(x, pos2, width2)
            profile3 = amp3 * self._step_resonator_profile(x, pos3, width3)
            total_profile = profile1 + profile2 + profile3
            
            # Compute soliton properties
            field_energy1 = self._compute_field_energy(profile1, x)
            field_energy2 = self._compute_field_energy(profile2, x)
            field_energy3 = self._compute_field_energy(profile3, x)
            total_field_energy = self._compute_field_energy(total_profile, x)
            
            # Compute interaction metrics
            distances = [abs(pos2 - pos1), abs(pos3 - pos1), abs(pos3 - pos2)]
            overlap_integrals = [
                np.trapz(profile1 * profile2, x),
                np.trapz(profile1 * profile3, x),
                np.trapz(profile2 * profile3, x),
            ]
            
            return {
                "spatial_grid": x,
                "total_profile": total_profile,
                "soliton_1_profile": profile1,
                "soliton_2_profile": profile2,
                "soliton_3_profile": profile3,
                "total_field_energy": total_field_energy,
                "individual_energies": [field_energy1, field_energy2, field_energy3],
                "distances": distances,
                "overlap_integrals": overlap_integrals,
            }
        
        except Exception as e:
            self.logger.error(f"Final three-soliton solution computation failed: {e}")
            return {}

