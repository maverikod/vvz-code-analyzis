"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Physics validation for automated testing system in 7D phase field theory.

This module implements physics validation for test results, ensuring
fundamental physical principles are maintained in 7D phase field theory
experiments.

Theoretical Background:
    Validates fundamental physical principles of 7D phase field theory,
    including conservation laws, topological invariants, and theoretical
    predictions.

Mathematical Foundation:
    Implements validation of:
    - Energy conservation: |dE/dt| < ε_energy
    - Virial conditions: |dE/dλ|λ=1| < ε_virial
    - Topological charge: |dB/dt| < ε_topology
    - Passivity: Re Y(ω) ≥ 0 for all ω

Example:
    >>> validator = PhysicsValidator(tolerance_config)
    >>> validation = validator.validate_result(test_result)
"""

import logging
from typing import Dict, Any
from .test_results import TestResult


class PhysicsValidator:
    """
    Physics validation for 7D phase field theory experiments.

    Physical Meaning:
        Validates fundamental physical principles of 7D phase field theory,
        including conservation laws, topological invariants, and theoretical
        predictions.

    Mathematical Foundation:
        Implements validation of:
        - Energy conservation: |dE/dt| < ε_energy
        - Virial conditions: |dE/dλ|λ=1| < ε_virial
        - Topological charge: |dB/dt| < ε_topology
        - Passivity: Re Y(ω) ≥ 0 for all ω
    """

    def __init__(self, tolerance_config: Dict[str, float]):
        """
        Initialize physics validator.

        Physical Meaning:
            Sets up validation with appropriate tolerance values for
            physical quantities in 7D phase field theory.

        Args:
            tolerance_config (Dict[str, float]): Tolerance configuration for
                physical validation constraints.
        """
        self.tolerance_config = tolerance_config
        self.energy_tolerance = tolerance_config.get("energy_conservation", {}).get(
            "max_relative_error", 1e-6
        )
        self.virial_tolerance = tolerance_config.get("virial_conditions", {}).get(
            "max_relative_error", 1e-6
        )
        self.topology_tolerance = tolerance_config.get("topological_charge", {}).get(
            "max_relative_error", 1e-8
        )
        self.passivity_tolerance = tolerance_config.get("passivity", {}).get(
            "tolerance", 1e-12
        )

    def validate_result(self, test_result: TestResult) -> Dict[str, Any]:
        """
        Validate test result against physics constraints.

        Physical Meaning:
            Validates test results against fundamental physical principles
            of 7D phase field theory, ensuring conservation laws and
            theoretical predictions are maintained.

        Args:
            test_result (TestResult): Test result to validate.

        Returns:
            Dict[str, Any]: Physics validation results with violations
                and compliance status.
        """
        validation_result = {
            "is_valid": True,
            "violations": [],
            "compliance_score": 1.0,
            "physics_metrics": {},
        }

        # Validate energy conservation
        energy_validation = self._validate_energy_conservation(test_result)
        if not energy_validation["is_valid"]:
            validation_result["violations"].append(energy_validation)
            validation_result["is_valid"] = False

        # Validate virial conditions
        virial_validation = self._validate_virial_conditions(test_result)
        if not virial_validation["is_valid"]:
            validation_result["violations"].append(virial_validation)
            validation_result["is_valid"] = False

        # Validate topological charge
        topology_validation = self._validate_topological_charge(test_result)
        if not topology_validation["is_valid"]:
            validation_result["violations"].append(topology_validation)
            validation_result["is_valid"] = False

        # Validate passivity conditions
        passivity_validation = self._validate_passivity_conditions(test_result)
        if not passivity_validation["is_valid"]:
            validation_result["violations"].append(passivity_validation)
            validation_result["is_valid"] = False

        # Calculate overall compliance score
        validation_result["compliance_score"] = self._calculate_compliance_score(
            validation_result
        )

        return validation_result

    def _validate_energy_conservation(self, test_result: TestResult) -> Dict[str, Any]:
        """Validate energy conservation in test result."""
        energy_metrics = test_result.physics_validation.get("energy_conservation", {})
        if isinstance(energy_metrics, dict):
            energy_error = energy_metrics.get("relative_error", float("inf"))
        else:
            energy_error = float("inf")

        is_valid = energy_error <= self.energy_tolerance

        return {
            "constraint": "energy_conservation",
            "is_valid": is_valid,
            "actual_value": energy_error,
            "tolerance": self.energy_tolerance,
            "severity": "critical" if not is_valid else "none",
            "physical_meaning": "Energy conservation is fundamental to 7D phase field theory",
        }

    def _validate_virial_conditions(self, test_result: TestResult) -> Dict[str, Any]:
        """Validate virial conditions in test result."""
        virial_metrics = test_result.physics_validation.get("virial_conditions", {})
        if isinstance(virial_metrics, dict):
            virial_error = virial_metrics.get("relative_error", float("inf"))
        else:
            virial_error = float("inf")

        is_valid = virial_error <= self.virial_tolerance

        return {
            "constraint": "virial_conditions",
            "is_valid": is_valid,
            "actual_value": virial_error,
            "tolerance": self.virial_tolerance,
            "severity": "critical" if not is_valid else "none",
            "physical_meaning": "Virial conditions ensure energy balance in phase fields",
        }

    def _validate_topological_charge(self, test_result: TestResult) -> Dict[str, Any]:
        """Validate topological charge conservation in test result."""
        topology_metrics = test_result.physics_validation.get("topological_charge", {})
        if isinstance(topology_metrics, dict):
            topology_error = topology_metrics.get("relative_error", float("inf"))
        else:
            topology_error = float("inf")

        is_valid = topology_error <= self.topology_tolerance

        return {
            "constraint": "topological_charge",
            "is_valid": is_valid,
            "actual_value": topology_error,
            "tolerance": self.topology_tolerance,
            "severity": "high" if not is_valid else "none",
            "physical_meaning": "Topological charge conservation is essential for particle stability",
        }

    def _validate_passivity_conditions(self, test_result: TestResult) -> Dict[str, Any]:
        """Validate passivity conditions in test result."""
        passivity_metrics = test_result.physics_validation.get("passivity", {})
        if isinstance(passivity_metrics, dict):
            min_real_part = passivity_metrics.get("min_real_part", float("-inf"))
        else:
            min_real_part = float("-inf")

        is_valid = min_real_part >= -self.passivity_tolerance

        return {
            "constraint": "passivity",
            "is_valid": is_valid,
            "actual_value": min_real_part,
            "tolerance": self.passivity_tolerance,
            "severity": "high" if not is_valid else "none",
            "physical_meaning": "Passivity ensures physical realizability of phase field responses",
        }

    def _calculate_compliance_score(self, validation_result: Dict[str, Any]) -> float:
        """Calculate overall compliance score."""
        violations = validation_result.get("violations", [])
        if not violations:
            return 1.0

        # Weight violations by severity
        severity_weights = {"critical": 0.0, "high": 0.3, "medium": 0.6, "low": 0.8}
        total_weight = sum(
            severity_weights.get(v.get("severity", "low"), 0.8) for v in violations
        )

        return max(0.0, 1.0 - total_weight / len(violations))
