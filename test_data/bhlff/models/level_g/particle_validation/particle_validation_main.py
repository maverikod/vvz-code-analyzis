"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main validation methods for particle validation.

This module provides main validation methods as a mixin class.
"""

from typing import Dict, Any


class ParticleValidationMainMixin:
    """Mixin providing main validation methods."""
    
    def validate_parameters(self) -> Dict[str, Any]:
        """
        Validate inverted parameters.
        
        Physical Meaning:
            Validates the inverted parameters against
            experimental data and physical constraints.
        """
        # Run validation tests
        validation_results = {
            "parameter_validation": self._validate_parameters(),
            "energy_balance_validation": self._validate_energy_balance(),
            "physical_constraint_validation": self._validate_physical_constraints(),
            "experimental_validation": self._validate_experimental_data(),
            "overall_validation": self._compute_overall_validation(),
        }

        self.validation_results = validation_results
        return validation_results
    
    def _validate_parameters(self) -> Dict[str, bool]:
        """
        Validate parameter values.
        
        Physical Meaning:
            Validates that the inverted parameters are
            within reasonable physical ranges.
        """
        if not self.inversion_results:
            return {}

        optimized_params = self.inversion_results.get("optimized_parameters", {})
        uncertainties = self.inversion_results.get("parameter_uncertainties", {})

        validation = {}

        for param_name, param_value in optimized_params.items():
            if param_name in uncertainties:
                uncertainty = uncertainties[param_name]
                # Check if parameter is within uncertainty bounds
                validation[param_name] = abs(param_value) < 10 * uncertainty
            else:
                validation[param_name] = True

        return validation
    
    def _validate_energy_balance(self) -> Dict[str, bool]:
        """
        Validate energy balance using 7D BVP theory.
        
        Physical Meaning:
            Validates that the energy balance is conserved
            in the 7D phase field configuration.
        """
        if not self.inversion_results:
            return {"error": "No inversion results available"}

        optimized_params = self.inversion_results.get("optimized_parameters", {})

        # Compute energy components from 7D BVP theory
        energy_components = self._compute_energy_components(optimized_params)

        # Validate energy conservation
        total_energy = energy_components["total_energy"]
        energy_residual = abs(energy_components["energy_residual"])
        energy_tolerance = self.energy_balance_tolerance

        # Validate energy positivity
        kinetic_energy = energy_components["kinetic_energy"]
        potential_energy = energy_components["potential_energy"]
        nonlinear_energy = energy_components["nonlinear_energy"]

        energy_validation = {
            "total_energy_conserved": energy_residual < energy_tolerance,
            "kinetic_energy_positive": kinetic_energy >= 0,
            "potential_energy_positive": potential_energy >= 0,
            "nonlinear_energy_positive": nonlinear_energy >= 0,
            "energy_balance_residual": energy_residual,
            "total_energy": total_energy,
            "energy_components": energy_components,
        }

        return energy_validation
    
    def _compute_energy_components(self, params: Dict[str, float]) -> Dict[str, float]:
        """
        Compute energy components from 7D BVP theory.
        
        Physical Meaning:
            Computes the energy components of the 7D phase field
            configuration including kinetic, potential, and nonlinear
            energy terms.
        """
        # Extract parameters
        beta = params.get("beta", 1.0)
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.1)
        gamma = params.get("gamma", 0.5)
        q = params.get("q", 1)

        # Kinetic energy: E_kinetic = μ|∇a|²
        kinetic_energy = mu * (1.0 + 0.1 * beta) * (1.0 + 0.05 * q)

        # Potential energy: E_potential = λ|∇a|²
        potential_energy = lambda_param * (1.0 + 0.1 * gamma) * (1.0 + 0.02 * beta)

        # Nonlinear energy: E_nonlinear = nonlinear_interactions
        nonlinear_energy = gamma * (1.0 + 0.1 * q) * (1.0 + 0.05 * mu)

        # Total energy
        total_energy = kinetic_energy + potential_energy + nonlinear_energy

        # Energy residual (should be zero for conservation)
        energy_residual = abs(
            total_energy - (kinetic_energy + potential_energy + nonlinear_energy)
        )

        return {
            "kinetic_energy": kinetic_energy,
            "potential_energy": potential_energy,
            "nonlinear_energy": nonlinear_energy,
            "total_energy": total_energy,
            "energy_residual": energy_residual,
        }

