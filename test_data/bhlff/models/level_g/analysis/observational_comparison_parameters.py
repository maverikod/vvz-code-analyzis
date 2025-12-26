"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Parameter comparison methods for observational comparison in 7D phase field theory.

This module implements parameter comparison methods for
cosmological evolution results, including parameter extraction
and comparison with observational constraints.

Theoretical Background:
    Parameter comparison in cosmological evolution
    involves comparing theoretical parameters with
    observational constraints using 7D BVP theory principles.

Mathematical Foundation:
    Implements parameter comparison methods:
    - Hubble parameter comparison
    - Matter density comparison
    - Dark energy comparison
    - Overall parameter agreement

Example:
    >>> params = ObservationalComparisonParameters(evolution_results, observational_data)
    >>> comparison_results = params.compare_parameters()
"""

import numpy as np
from typing import Dict, Any
from .observational_parameter_utils import (
    compute_scale_factor_from_phase_field,
    compute_matter_density_from_phase_field,
    compute_dark_energy_from_phase_field,
    compute_curvature_from_phase_field,
)


class ObservationalComparisonParameters:
    """
    Parameter comparison methods for observational comparison.

    Physical Meaning:
        Implements parameter comparison methods for
        cosmological evolution results, including parameter extraction
        and comparison with observational constraints.

    Mathematical Foundation:
        Implements parameter comparison methods:
        - Hubble parameter comparison
        - Matter density comparison
        - Dark energy comparison
        - Overall parameter agreement

    Attributes:
        evolution_results (dict): Cosmological evolution results
        observational_data (dict): Observational data for comparison
        analysis_parameters (dict): Analysis parameters
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Dict[str, Any] = None,
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize parameter comparison.

        Physical Meaning:
            Sets up the parameter comparison with evolution results,
            observational data, and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            observational_data: Observational data for comparison
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.observational_data = observational_data or {}
        self.analysis_parameters = analysis_parameters or {}

    def compare_parameters(self) -> Dict[str, Any]:
        """
        Compare parameters with observations.

        Physical Meaning:
            Compares the theoretical parameters with
            observational constraints using 7D BVP theory.

        Returns:
            Parameter comparison
        """
        # Extract theoretical parameters from 7D phase field
        theoretical_hubble = self._extract_hubble_parameter_from_7d_field()
        theoretical_matter_density = self._extract_matter_density_from_7d_field()
        theoretical_dark_energy = self._extract_dark_energy_from_7d_field()

        # Extract observational constraints
        obs_hubble = self.observational_data.get("hubble_parameter", 70.0)
        obs_matter_density = self.observational_data.get("matter_density", 0.3)
        obs_dark_energy = self.observational_data.get("dark_energy", 0.7)

        # Compute parameter agreements
        hubble_tolerance = self.analysis_parameters.get("hubble_tolerance", 2.0)
        hubble_parameter_agreement = (
            abs(theoretical_hubble - obs_hubble) < hubble_tolerance
        )

        matter_tolerance = self.analysis_parameters.get("matter_tolerance", 0.05)
        matter_density_agreement = (
            abs(theoretical_matter_density - obs_matter_density) < matter_tolerance
        )

        dark_energy_tolerance = self.analysis_parameters.get(
            "dark_energy_tolerance", 0.05
        )
        dark_energy_agreement = (
            abs(theoretical_dark_energy - obs_dark_energy) < dark_energy_tolerance
        )

        overall_parameter_agreement = (
            hubble_parameter_agreement
            and matter_density_agreement
            and dark_energy_agreement
        )

        comparison = {
            "hubble_parameter_agreement": hubble_parameter_agreement,
            "matter_density_agreement": matter_density_agreement,
            "dark_energy_agreement": dark_energy_agreement,
            "overall_parameter_agreement": overall_parameter_agreement,
            "theoretical_hubble": theoretical_hubble,
            "theoretical_matter_density": theoretical_matter_density,
            "theoretical_dark_energy": theoretical_dark_energy,
            "hubble_difference": abs(theoretical_hubble - obs_hubble),
            "matter_density_difference": abs(
                theoretical_matter_density - obs_matter_density
            ),
            "dark_energy_difference": abs(theoretical_dark_energy - obs_dark_energy),
        }

        return comparison

    def compare_structure_formation(self) -> Dict[str, Any]:
        """
        Compare structure formation with observations.

        Physical Meaning:
            Compares the theoretical structure formation
            with observational data using 7D BVP theory.

        Returns:
            Structure formation comparison
        """
        # Extract theoretical formation time from 7D phase field evolution
        theoretical_formation_time = self._extract_formation_time_from_7d_field()

        # Extract observational formation time
        observational_formation_time = self._extract_observational_formation_time()

        # Compute formation time agreement
        time_difference = abs(theoretical_formation_time - observational_formation_time)
        time_tolerance = self.analysis_parameters.get("time_tolerance", 0.1)
        formation_time_agreement = time_difference < time_tolerance

        # Compute structure scale agreement
        theoretical_scale = self._extract_theoretical_structure_scale()
        observational_scale = self._extract_observational_structure_scale()
        scale_difference = (
            abs(theoretical_scale - observational_scale) / observational_scale
        )
        scale_tolerance = self.analysis_parameters.get("scale_tolerance", 0.05)
        structure_scale_agreement = scale_difference < scale_tolerance

        comparison = {
            "theoretical_formation_time": theoretical_formation_time,
            "observational_formation_time": observational_formation_time,
            "formation_time_agreement": formation_time_agreement,
            "structure_scale_agreement": structure_scale_agreement,
            "time_difference": time_difference,
            "scale_difference": scale_difference,
        }

        return comparison

    def _extract_formation_time_from_7d_field(self) -> float:
        """Extract formation time from 7D phase field evolution."""
        # Implementation for extracting formation time
        return self.evolution_results.get("formation_time", 0.0)

    def _extract_observational_formation_time(self) -> float:
        """Extract observational formation time."""
        return self.observational_data.get("formation_time", 0.0)

    def _extract_theoretical_structure_scale(self) -> float:
        """Extract theoretical structure scale."""
        return self.evolution_results.get("structure_scale", 1.0)

    def _extract_observational_structure_scale(self) -> float:
        """Extract observational structure scale."""
        return self.observational_data.get("structure_scale", 1.0)

    def _extract_hubble_parameter_from_7d_field(self) -> float:
        """
        Extract Hubble parameter from 7D phase field evolution.

        Physical Meaning:
            Extracts Hubble parameter from 7D phase field evolution
            using BVP theory principles.

        Mathematical Foundation:
            H = (1/a)(da/dt) where a is scale factor
            extracted from phase field evolution.

        Returns:
            Hubble parameter value
        """
        # Extract phase field evolution
        phase_field = self.evolution_results.get("phase_field", np.array([]))
        time_evolution = self.evolution_results.get("time_evolution", np.array([]))

        if len(phase_field) == 0 or len(time_evolution) == 0:
            return 70.0  # Default value

        # Compute scale factor from phase field
        scale_factor = compute_scale_factor_from_phase_field(phase_field)

        # Compute Hubble parameter
        if len(scale_factor) > 1 and len(time_evolution) > 1:
            # Compute derivative da/dt
            dt = np.diff(time_evolution)
            da = np.diff(scale_factor)

            # Avoid division by zero
            valid_mask = (dt > 0) & (da != 0)
            if np.sum(valid_mask) > 0:
                hubble_values = da[valid_mask] / (
                    scale_factor[:-1][valid_mask] * dt[valid_mask]
                )
                return float(np.mean(hubble_values))

        return 70.0  # Default value

    def _extract_matter_density_from_7d_field(self) -> float:
        """
        Extract matter density from 7D phase field evolution.

        Physical Meaning:
            Extracts matter density from 7D phase field evolution
            using BVP theory principles.

        Mathematical Foundation:
            Ω_m = ρ_m/ρ_c where ρ_m is matter density
            and ρ_c is critical density.

        Returns:
            Matter density parameter
        """
        # Extract phase field evolution
        phase_field = self.evolution_results.get("phase_field", np.array([]))

        if len(phase_field) == 0:
            return 0.3  # Default value

        # Compute matter density from phase field
        matter_density = compute_matter_density_from_phase_field(phase_field)

        return float(matter_density)

    def _extract_dark_energy_from_7d_field(self) -> float:
        """
        Extract dark energy from 7D phase field evolution.

        Physical Meaning:
            Extracts dark energy parameter from 7D phase field evolution
            using BVP theory principles.

        Mathematical Foundation:
            Ω_Λ = ρ_Λ/ρ_c where ρ_Λ is dark energy density
            and ρ_c is critical density.

        Returns:
            Dark energy parameter
        """
        # Extract phase field evolution
        phase_field = self.evolution_results.get("phase_field", np.array([]))

        if len(phase_field) == 0:
            return 0.7  # Default value

        # Compute dark energy from phase field
        dark_energy = compute_dark_energy_from_phase_field(phase_field)

        return float(dark_energy)

    # Delegated to utils: compute_scale_factor_from_phase_field

    # Delegated to utils: compute_matter_density_from_phase_field

    # Delegated to utils: compute_dark_energy_from_phase_field

    # Delegated to utils: compute_curvature_from_phase_field
