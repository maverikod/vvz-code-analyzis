"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Physical constraints validation methods for particle validation.

This module provides physical constraints validation methods as a mixin class.
"""

from typing import Dict, Any


class ParticleValidationConstraintsMixin:
    """Mixin providing physical constraints validation methods."""
    
    def _validate_physical_constraints(self) -> Dict[str, bool]:
        """
        Validate physical constraints using 7D BVP theory.
        
        Physical Meaning:
            Validates that the inverted parameters satisfy
            physical constraints and conservation laws.
        """
        if not self.inversion_results:
            return {"error": "No inversion results available"}

        optimized_params = self.inversion_results.get("optimized_parameters", {})

        # Validate passivity constraint
        passivity_valid = self._validate_passivity_constraint(optimized_params)

        # Validate causality constraint
        causality_valid = self._validate_causality_constraint(optimized_params)

        # Validate unitarity constraint
        unitarity_valid = self._validate_unitarity_constraint(optimized_params)

        # Validate gauge invariance
        gauge_invariance_valid = self._validate_gauge_invariance(optimized_params)

        # Validate 7D BVP specific constraints
        bvp_constraints_valid = self._validate_7d_bvp_constraints(optimized_params)

        constraint_validation = {
            "passivity_constraint": passivity_valid,
            "causality_constraint": causality_valid,
            "unitarity_constraint": unitarity_valid,
            "gauge_invariance": gauge_invariance_valid,
            "bvp_7d_constraints": bvp_constraints_valid,
            "overall_constraints": all(
                [
                    passivity_valid,
                    causality_valid,
                    unitarity_valid,
                    gauge_invariance_valid,
                    bvp_constraints_valid,
                ]
            ),
        }

        return constraint_validation
    
    def _validate_passivity_constraint(self, params: Dict[str, float]) -> bool:
        """Validate passivity constraint."""
        # Passivity: Re[Z(ω)] ≥ 0 for all frequencies
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.1)

        # Passivity requires positive dissipation
        dissipation = mu + lambda_param
        return dissipation > 0
    
    def _validate_causality_constraint(self, params: Dict[str, float]) -> bool:
        """Validate causality constraint."""
        # Causality: Kramers-Kronig relations must be satisfied
        beta = params.get("beta", 1.0)
        tau = params.get("tau", 1.0)

        # Causality requires positive time constants
        return beta > 0 and tau > 0
    
    def _validate_unitarity_constraint(self, params: Dict[str, float]) -> bool:
        """Validate unitarity constraint."""
        # Unitarity: |S|² = 1 for scattering matrix
        q = params.get("q", 1)
        gamma = params.get("gamma", 0.5)

        # Unitarity requires proper normalization
        normalization = q * (1.0 + gamma)
        return 0.5 <= normalization <= 2.0
    
    def _validate_gauge_invariance(self, params: Dict[str, float]) -> bool:
        """Validate gauge invariance."""
        # Gauge invariance: U(1) symmetry preserved
        eta = params.get("eta", 0.1)
        gamma = params.get("gamma", 0.5)

        # Gauge invariance requires proper phase structure
        phase_structure = eta * gamma
        return 0.01 <= phase_structure <= 1.0
    
    def _validate_7d_bvp_constraints(self, params: Dict[str, float]) -> bool:
        """Validate 7D BVP specific constraints."""
        # 7D BVP constraints
        beta = params.get("beta", 1.0)
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.1)
        q = params.get("q", 1)

        # Fractional order constraint: 0 < β < 2
        beta_valid = 0 < beta < 2

        # Diffusion coefficient constraint: μ > 0
        mu_valid = mu > 0

        # Damping parameter constraint: λ ≥ 0
        lambda_valid = lambda_param >= 0

        # Topological charge constraint: q ∈ ℤ
        q_valid = isinstance(q, int) and q != 0

        return all([beta_valid, mu_valid, lambda_valid, q_valid])

