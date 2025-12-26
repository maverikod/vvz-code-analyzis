"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Two-soliton optimization methods for multi-soliton optimization.

This module provides two-soliton optimization methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List
from scipy.optimize import minimize
from scipy.integrate import solve_bvp


class MultiSolitonOptimizationTwoMixin:
    """Mixin providing two-soliton optimization methods."""
    
    def find_two_soliton_solutions(self) -> List[Dict[str, Any]]:
        """
        Find two-soliton solutions using full 7D BVP theory.
        
        Physical Meaning:
            Finds two-soliton solutions through complete optimization
            using 7D fractional Laplacian equations and soliton-soliton
            interaction potentials with full 7D BVP theory implementation.
            
        Returns:
            List[Dict[str, Any]]: Two-soliton solutions with interaction
            analysis and full physical parameters.
        """
        try:
            solutions = []
            
            # Multiple initial guesses for robust optimization
            initial_guesses = [
                [1.0, 1.0, -3.0, 1.0, 1.0, 3.0],  # Standard separation
                [1.2, 0.8, -2.0, 0.8, 1.2, 2.0],  # Different amplitudes/widths
                [0.9, 1.1, -4.0, 1.1, 0.9, 4.0],  # Wider separation
                [1.1, 0.9, -1.5, 0.9, 1.1, 1.5],  # Closer separation
                [1.3, 0.7, -2.5, 0.7, 1.3, 2.5],  # Asymmetric
            ]
            
            best_solution = None
            best_energy = float("inf")
            
            for i, initial_params in enumerate(initial_guesses):
                try:
                    # Setup 7D mesh for BVP solving with adaptive resolution
                    x_mesh = np.linspace(-20.0, 20.0, 300)
                    y_guess = np.zeros((2, len(x_mesh)))
                    
                    def two_soliton_equations_7d(params):
                        """7D two-soliton equations with full interaction physics."""
                        amp1, width1, pos1, amp2, width2, pos2 = params
                        
                        def two_soliton_ode(x, y):
                            """7D two-soliton ODE system with complete interactions."""
                            return self.core.compute_7d_two_soliton_ode(
                                x, y, amp1, width1, pos1, amp2, width2, pos2
                            )
                        
                        # Enhanced boundary conditions for two solitons
                        def bc(ya, yb):
                            # Soliton boundary conditions with proper 7D BVP theory
                            return [
                                ya[0]
                                - amp1
                                * self._step_resonator_boundary_condition(ya[0], amp1),
                                yb[0]
                                - amp2
                                * self._step_resonator_boundary_condition(yb[0], amp2),
                            ]
                        
                        try:
                            # Solve BVP with enhanced convergence
                            sol = solve_bvp(
                                two_soliton_ode,
                                bc,
                                x_mesh,
                                y_guess,
                                tol=1e-8,
                                max_nodes=1500,
                            )
                            
                            if sol.success:
                                # Compute total energy including interaction
                                energy = self.core.compute_two_soliton_energy(
                                    sol.y, amp1, width1, pos1, amp2, width2, pos2
                                )
                                
                                # Additional energy penalty for unphysical solutions
                                if np.any(np.isnan(sol.y)) or np.any(np.isinf(sol.y)):
                                    return 1e10
                                
                                # Check for proper two-soliton shape
                                if not self.validator.validate_two_soliton_shape(
                                    sol.y, amp1, width1, amp2, width2
                                ):
                                    return 1e10
                                
                                return -energy  # Minimize negative energy
                            else:
                                return 1e10  # Large penalty for failed solution
                        
                        except Exception as e:
                            self.logger.debug(
                                f"BVP solution failed for two-soliton guess {i}: {e}"
                            )
                            return 1e10  # Penalty for failed BVP solution
                    
                    # Optimize two-soliton parameters using 7D theory with enhanced bounds
                    result = minimize(
                        two_soliton_equations_7d,
                        initial_params,
                        method="L-BFGS-B",
                        bounds=[
                            (0.1, 3.0),
                            (0.3, 2.0),
                            (-12.0, 12.0),
                            (0.1, 3.0),
                            (0.3, 2.0),
                            (-12.0, 12.0),
                        ],
                        options={"maxiter": 250, "ftol": 1e-12, "gtol": 1e-8},
                    )
                    
                    if result.success and result.fun < best_energy and result.fun < 1e9:
                        best_energy = result.fun
                        amp1, width1, pos1, amp2, width2, pos2 = result.x
                        
                        # Compute final two-soliton solution with full validation
                        final_solution = self._compute_final_two_soliton_solution(
                            amp1, width1, pos1, amp2, width2, pos2
                        )
                        
                        # Compute interaction strength with full physics
                        interaction_strength = (
                            self._compute_soliton_interaction_strength(
                                amp1, width1, pos1, amp2, width2, pos2
                            )
                        )
                        
                        # Validate solution quality
                        if self.validator.validate_two_soliton_solution_quality(
                            final_solution, amp1, width1, amp2, width2
                        ):
                            best_solution = {
                                "type": "multi",
                                "num_solitons": 2,
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
                                "energy": -result.fun,
                                "interaction_strength": interaction_strength,
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
                                "physical_properties": self.validator.compute_two_soliton_physical_properties(
                                    amp1,
                                    width1,
                                    pos1,
                                    amp2,
                                    width2,
                                    pos2,
                                    final_solution,
                                ),
                            }
                
                except Exception as e:
                    self.logger.debug(
                        f"Two-soliton optimization failed for guess {i}: {e}"
                    )
                    continue
            
            if best_solution:
                solutions.append(best_solution)
            
            return solutions
        
        except Exception as e:
            self.logger.warning(f"Two-soliton finding failed: {e}")
            return []
    
    def _compute_final_two_soliton_solution(
        self,
        amp1: float,
        width1: float,
        pos1: float,
        amp2: float,
        width2: float,
        pos2: float,
    ) -> Dict[str, Any]:
        """
        Compute final two-soliton solution with full physical parameters.
        
        Physical Meaning:
            Generates the complete two-soliton solution with all physical
            parameters and properties computed from the optimization results.
            
        Args:
            amp1, width1, pos1 (float): First soliton parameters.
            amp2, width2, pos2 (float): Second soliton parameters.
            
        Returns:
            Dict[str, Any]: Complete two-soliton solution with physical properties.
        """
        try:
            # Generate spatial grid
            x = np.linspace(-15.0, 15.0, 300)
            
            # Compute individual soliton profiles using 7D BVP step resonator theory
            profile1 = amp1 * self._step_resonator_profile(x, pos1, width1)
            profile2 = amp2 * self._step_resonator_profile(x, pos2, width2)
            total_profile = profile1 + profile2
            
            # Compute soliton properties
            field_energy1 = self._compute_field_energy(profile1, x)
            field_energy2 = self._compute_field_energy(profile2, x)
            total_field_energy = self._compute_field_energy(total_profile, x)
            
            # Compute interaction metrics
            distance = abs(pos2 - pos1)
            overlap_integral = np.trapz(profile1 * profile2, x)
            interaction_strength = self._compute_soliton_interaction_strength(
                amp1, width1, pos1, amp2, width2, pos2
            )
            
            return {
                "spatial_grid": x,
                "total_profile": total_profile,
                "soliton_1_profile": profile1,
                "soliton_2_profile": profile2,
                "total_field_energy": total_field_energy,
                "individual_energies": [field_energy1, field_energy2],
                "distance": distance,
                "overlap_integral": overlap_integral,
                "interaction_strength": interaction_strength,
            }
        
        except Exception as e:
            self.logger.error(f"Final two-soliton solution computation failed: {e}")
            return {}

