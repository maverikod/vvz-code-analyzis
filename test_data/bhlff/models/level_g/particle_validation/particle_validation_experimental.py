"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Experimental data validation methods for particle validation.

This module provides experimental data validation methods as a mixin class.
"""

from typing import Dict, Any


class ParticleValidationExperimentalMixin:
    """Mixin providing experimental data validation methods."""
    
    def _validate_experimental_data(self) -> Dict[str, bool]:
        """
        Validate against experimental data using 7D BVP theory.
        
        Physical Meaning:
            Validates that the inverted parameters reproduce
            experimental observations within uncertainties.
        """
        if not self.experimental_data:
            return {"error": "No experimental data available"}

        if not self.inversion_results:
            return {"error": "No inversion results available"}

        optimized_params = self.inversion_results.get("optimized_parameters", {})

        # Validate mass spectrum agreement
        mass_agreement = self._validate_mass_spectrum(optimized_params)

        # Validate charge spectrum agreement
        charge_agreement = self._validate_charge_spectrum(optimized_params)

        # Validate magnetic moment agreement
        magnetic_moment_agreement = self._validate_magnetic_moment(optimized_params)

        # Validate lifetime agreement
        lifetime_agreement = self._validate_lifetime(optimized_params)

        # Validate 7D BVP specific observables
        bvp_observables_agreement = self._validate_7d_bvp_observables(optimized_params)

        experimental_validation = {
            "mass_spectrum_agreement": mass_agreement,
            "charge_spectrum_agreement": charge_agreement,
            "magnetic_moment_agreement": magnetic_moment_agreement,
            "lifetime_agreement": lifetime_agreement,
            "bvp_observables_agreement": bvp_observables_agreement,
            "overall_experimental_agreement": all(
                [
                    mass_agreement,
                    charge_agreement,
                    magnetic_moment_agreement,
                    lifetime_agreement,
                    bvp_observables_agreement,
                ]
            ),
        }

        return experimental_validation
    
    def _validate_mass_spectrum(self, params: Dict[str, float]) -> bool:
        """Validate mass spectrum agreement."""
        # In 7D BVP theory, mass is resistance to phase state rearrangement
        q = params.get("q", 1)
        tau = params.get("tau", 1.0)
        beta = params.get("beta", 1.0)

        # Predicted mass from 7D BVP theory
        predicted_mass = q * tau * (1.0 + 0.1 * beta)

        # Compare with experimental data (if available)
        if "mass_spectrum" in self.experimental_data:
            exp_mass = self.experimental_data["mass_spectrum"]
            mass_tolerance = 0.1  # 10% tolerance
            return abs(predicted_mass - exp_mass) / exp_mass < mass_tolerance
        else:
            # Default validation (mass should be positive)
            return predicted_mass > 0
    
    def _validate_charge_spectrum(self, params: Dict[str, float]) -> bool:
        """Validate charge spectrum agreement."""
        # Charge spectrum depends on topological charge in 7D BVP theory
        q = params.get("q", 1)

        # Predicted charge from 7D BVP theory
        predicted_charge = q

        # Compare with experimental data (if available)
        if "charge_spectrum" in self.experimental_data:
            exp_charge = self.experimental_data["charge_spectrum"]
            return predicted_charge == exp_charge
        else:
            # Default validation (charge should be integer)
            return isinstance(q, int)
    
    def _validate_magnetic_moment(self, params: Dict[str, float]) -> bool:
        """Validate magnetic moment agreement."""
        # Magnetic moment depends on phase field structure in 7D BVP theory
        q = params.get("q", 1)
        gamma = params.get("gamma", 0.5)
        eta = params.get("eta", 0.1)

        # Predicted magnetic moment from 7D BVP theory
        predicted_moment = q * gamma * eta * (1.0 + 0.1 * gamma)

        # Compare with experimental data (if available)
        if "magnetic_moment" in self.experimental_data:
            exp_moment = self.experimental_data["magnetic_moment"]
            moment_tolerance = 0.05  # 5% tolerance
            return abs(predicted_moment - exp_moment) / exp_moment < moment_tolerance
        else:
            # Default validation (moment should be positive)
            return predicted_moment > 0
    
    def _validate_lifetime(self, params: Dict[str, float]) -> bool:
        """Validate lifetime agreement."""
        # Lifetime depends on phase field dynamics in 7D BVP theory
        tau = params.get("tau", 1.0)
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.1)

        # Predicted lifetime from 7D BVP theory
        predicted_lifetime = tau / (mu + lambda_param)

        # Compare with experimental data (if available)
        if "lifetime" in self.experimental_data:
            exp_lifetime = self.experimental_data["lifetime"]
            lifetime_tolerance = 0.2  # 20% tolerance
            return (
                abs(predicted_lifetime - exp_lifetime) / exp_lifetime
                < lifetime_tolerance
            )
        else:
            # Default validation (lifetime should be positive)
            return predicted_lifetime > 0
    
    def _validate_7d_bvp_observables(self, params: Dict[str, float]) -> bool:
        """Validate 7D BVP specific observables."""
        # 7D BVP specific observables
        beta = params.get("beta", 1.0)
        mu = params.get("mu", 1.0)
        lambda_param = params.get("lambda", 0.1)

        # Predicted power law exponent from 7D BVP theory
        predicted_exponent = 2 * beta - 3

        # Compare with experimental data (if available)
        if "power_law_exponent" in self.experimental_data:
            exp_exponent = self.experimental_data["power_law_exponent"]
            exponent_tolerance = 0.1  # 10% tolerance
            return (
                abs(predicted_exponent - exp_exponent) / abs(exp_exponent)
                < exponent_tolerance
            )
        else:
            # Default validation (exponent should be in reasonable range)
            return -1 <= predicted_exponent <= 1

