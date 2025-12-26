"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core observational comparison for cosmological analysis in 7D phase field theory.

This module implements the main observational comparison functionality
for cosmological evolution results using 7D BVP theory principles.

Theoretical Background:
    Observational comparison in cosmological evolution involves
    comparing theoretical results with observational data to
    validate the model using 7D BVP theory principles.

Example:
    >>> core = ObservationalComparisonCore(evolution_results, observational_data)
    >>> comparison_results = core.compare_with_observations()
"""

import numpy as np
from typing import Dict, Any
from .observational_data_loader import ObservationalDataLoader
from .observable_extractor import ObservableExtractor
from .statistical_comparison import StatisticalComparison


class ObservationalComparisonCore:
    """
    Core observational comparison for cosmological analysis.

    Physical Meaning:
        Implements core observational comparison methods for
        cosmological evolution results, including comparison
        with observational data and goodness of fit analysis.

    Mathematical Foundation:
        Implements core observational comparison methods:
        - Structure formation comparison: with observational data
        - Parameter comparison: with observational constraints
        - Statistical comparison: with observational statistics
        - Goodness of fit: various goodness of fit metrics

    Attributes:
        evolution_results (dict): Cosmological evolution results
        observational_data (dict): Observational data for comparison
        analysis_parameters (dict): Analysis parameters
        _data_loader (ObservationalDataLoader): Data loading functionality
        _observable_extractor (ObservableExtractor): Observable extraction
        _statistical_comparison (StatisticalComparison): Statistical comparison
    """

    def __init__(
        self,
        evolution_results: Dict[str, Any],
        observational_data: Dict[str, Any] = None,
        analysis_parameters: Dict[str, Any] = None,
    ):
        """
        Initialize observational comparison core.

        Physical Meaning:
            Sets up the observational comparison with evolution results,
            observational data, and analysis parameters.

        Args:
            evolution_results: Cosmological evolution results
            observational_data: Observational data for comparison
            analysis_parameters: Analysis parameters
        """
        self.evolution_results = evolution_results
        self.observational_data = observational_data or {}
        self.analysis_parameters = analysis_parameters or {}

        # Initialize specialized components
        self._data_loader = ObservationalDataLoader(
            observational_data, analysis_parameters
        )
        self._observable_extractor = ObservableExtractor(
            evolution_results, analysis_parameters
        )
        self._statistical_comparison = StatisticalComparison(analysis_parameters)

    def compare_with_observations(self) -> Dict[str, Any]:
        """
        Compare results with observational data using 7D BVP theory.

        Physical Meaning:
            Compares the theoretical results with observational
            data to validate the model using 7D BVP theory principles.

        Returns:
            Comprehensive comparison results
        """
        if not self.observational_data:
            return {}

        # Load observational data
        obs_data = self._data_loader.load_observational_data()

        # Compute 7D phase field observables
        model_observables = self._observable_extractor.compute_7d_observables()

        # Statistical comparison
        comparison_results = self._statistical_comparison.perform_comparison(
            obs_data, model_observables
        )

        # Compute chi-squared
        chi_squared = self._statistical_comparison.compute_chi_squared(
            obs_data, model_observables
        )

        # Compute likelihood
        likelihood = self._statistical_comparison.compute_likelihood(chi_squared)

        # Compare with observations
        comparison = {
            "structure_formation_comparison": self._compare_structure_formation(
                obs_data, model_observables
            ),
            "parameter_comparison": self._compare_parameters(
                obs_data, model_observables
            ),
            "statistical_comparison": comparison_results,
            "goodness_of_fit": self._statistical_comparison.compute_goodness_of_fit(
                obs_data, model_observables
            ),
            "chi_squared": chi_squared,
            "likelihood": likelihood,
            "comparison_results": comparison_results,
            "model_observables": model_observables,
            "observational_data": obs_data,
        }

        return comparison

    def _compare_structure_formation(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare structure formation between observations and model.

        Physical Meaning:
            Compares structure formation predictions with observational
            data using 7D BVP theory principles.
        """
        # Compare correlation functions
        correlation_comparison = self._compare_correlation_functions(
            obs_data.get("correlation_function", np.array([])),
            model_observables.get("correlation_function", np.array([])),
        )

        # Compare power spectra
        power_spectrum_comparison = self._compare_power_spectra(
            obs_data.get("power_spectrum", np.array([])),
            model_observables.get("power_spectrum", np.array([])),
        )

        # Compare structure statistics
        structure_comparison = self._compare_structure_statistics(
            obs_data.get("structure_statistics", {}),
            model_observables.get("structure_statistics", {}),
        )

        return {
            "correlation_comparison": correlation_comparison,
            "power_spectrum_comparison": power_spectrum_comparison,
            "structure_comparison": structure_comparison,
        }

    def _compare_parameters(
        self, obs_data: Dict[str, Any], model_observables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare cosmological parameters between observations and model.

        Physical Meaning:
            Compares cosmological parameters with observational
            constraints using 7D BVP theory.
        """
        parameter_comparison = {}

        # Compare Hubble parameter
        if "hubble_parameter" in obs_data and "hubble_parameter" in model_observables:
            parameter_comparison["hubble_parameter"] = self._compare_parameter(
                obs_data["hubble_parameter"], model_observables["hubble_parameter"]
            )

        # Compare matter density
        if "matter_density" in obs_data and "matter_density" in model_observables:
            parameter_comparison["matter_density"] = self._compare_parameter(
                obs_data["matter_density"], model_observables["matter_density"]
            )

        # Compare dark energy
        if "dark_energy" in obs_data and "dark_energy" in model_observables:
            parameter_comparison["dark_energy"] = self._compare_parameter(
                obs_data["dark_energy"], model_observables["dark_energy"]
            )

        return parameter_comparison

    def _compare_correlation_functions(
        self, obs_corr: np.ndarray, model_corr: np.ndarray
    ) -> Dict[str, Any]:
        """Compare correlation functions."""
        if len(obs_corr) == 0 or len(model_corr) == 0:
            return {"comparison": "insufficient_data"}

        # Compute correlation coefficient
        if len(obs_corr) == len(model_corr):
            correlation = np.corrcoef(obs_corr, model_corr)[0, 1]
        else:
            correlation = 0.0

        return {
            "correlation_coefficient": correlation,
            "rms_difference": np.sqrt(np.mean((obs_corr - model_corr) ** 2)),
            "agreement_quality": "good" if correlation > 0.8 else "fair",
        }

    def _compare_power_spectra(
        self, obs_power: np.ndarray, model_power: np.ndarray
    ) -> Dict[str, Any]:
        """Compare power spectra."""
        if len(obs_power) == 0 or len(model_power) == 0:
            return {"comparison": "insufficient_data"}

        # Compute correlation coefficient
        if len(obs_power) == len(model_power):
            correlation = np.corrcoef(obs_power, model_power)[0, 1]
        else:
            correlation = 0.0

        return {
            "correlation_coefficient": correlation,
            "rms_difference": np.sqrt(np.mean((obs_power - model_power) ** 2)),
            "agreement_quality": "good" if correlation > 0.8 else "fair",
        }

    def _compare_structure_statistics(
        self, obs_stats: Dict[str, Any], model_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compare structure statistics."""
        comparison = {}

        for key in ["variance", "skewness", "kurtosis"]:
            if key in obs_stats and key in model_stats:
                obs_value = obs_stats[key]
                model_value = model_stats[key]

                if isinstance(obs_value, (int, float)) and isinstance(
                    model_value, (int, float)
                ):
                    comparison[key] = {
                        "observational": obs_value,
                        "model": model_value,
                        "difference": abs(model_value - obs_value),
                        "relative_difference": (
                            abs(model_value - obs_value) / abs(obs_value)
                            if obs_value != 0
                            else 0.0
                        ),
                    }

        return comparison

    def _compare_parameter(
        self, obs_value: float, model_value: float
    ) -> Dict[str, Any]:
        """Compare individual parameter."""
        return {
            "observational": obs_value,
            "model": model_value,
            "difference": abs(model_value - obs_value),
            "relative_difference": (
                abs(model_value - obs_value) / abs(obs_value) if obs_value != 0 else 0.0
            ),
            "agreement": (
                "good"
                if abs(model_value - obs_value) / abs(obs_value) < 0.1
                else "fair"
            ),
        }
