"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Experiment runner for Level E experiments.

This module implements the main experiment runner functionality
for coordinating Level E experiments in 7D phase field theory.

Theoretical Background:
    Level E experiments focus on solitons and topological defects in the
    7D phase field theory, representing fundamental particle-like structures
    with topological protection.

Example:
    >>> runner = ExperimentRunner(config)
    >>> results = runner.run_full_analysis()
"""

import numpy as np
from typing import Dict, Any, List, Optional
import json
import logging

from ..sensitivity_analysis import SensitivityAnalyzer
from ..robustness_tests import RobustnessTester
from ..discretization_effects import DiscretizationAnalyzer
from ..failure_detection import FailureDetector
from ..phase_mapping import PhaseMapper
from ..performance_analysis import PerformanceAnalyzer


class ExperimentRunner:
    """
    Main experiment runner for Level E experiments.

    Physical Meaning:
        Coordinates comprehensive stability and sensitivity analysis
        of the 7D phase field theory, investigating the robustness
        of solitons and topological defects under various conditions.

    Mathematical Foundation:
        Implements systematic parameter sweeps, sensitivity analysis
        using Sobol indices, and phase space mapping to understand
        the stability boundaries of the theory.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize experiment runner.

        Args:
            config: Configuration dictionary with experiment parameters
        """
        self.config = config
        self._setup_logging()
        self._setup_analyzers()
        self._setup_experiment_parameters()

    def _setup_logging(self) -> None:
        """Setup logging for experiments."""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _setup_analyzers(self) -> None:
        """Setup analysis components."""
        # Initialize analyzers
        self.sensitivity_analyzer = SensitivityAnalyzer(
            self.config.get("parameter_ranges", {})
        )
        self.robustness_tester = RobustnessTester(self.config.get("base_config", {}))
        self.discretization_analyzer = DiscretizationAnalyzer(
            self.config.get("reference_config", {})
        )
        self.failure_detector = FailureDetector(self.config.get("base_config", {}))
        self.phase_mapper = PhaseMapper(self.config.get("phase_mapping_config", {}))
        self.performance_analyzer = PerformanceAnalyzer(
            self.config.get("performance_config", {})
        )

    def _setup_experiment_parameters(self) -> None:
        """Setup experiment parameters."""
        self.experiment_parameters = {
            "E1_sensitivity": self.config.get("E1_sensitivity", {}),
            "E2_robustness": self.config.get("E2_robustness", {}),
            "E3_discretization": self.config.get("E3_discretization", {}),
            "E4_failures": self.config.get("E4_failures", {}),
            "E5_phase_mapping": self.config.get("E5_phase_mapping", {}),
            "E6_performance": self.config.get("E6_performance", {}),
        }

    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Execute complete Level E analysis suite.

        Physical Meaning:
            Performs comprehensive investigation of system stability
            and sensitivity, providing complete characterization of
            the 7D phase field theory behavior.

        Returns:
            Dict containing all analysis results and metrics
        """
        self.logger.info("Starting Level E experiments")

        results = {}

        try:
            # E1: Sensitivity analysis
            self.logger.info("Running E1: Sensitivity analysis")
            results["E1_sensitivity"] = self._run_sensitivity_analysis()

            # E2: Robustness testing
            self.logger.info("Running E2: Robustness testing")
            results["E2_robustness"] = self._run_robustness_testing()

            # E3: Discretization effects
            self.logger.info("Running E3: Discretization effects")
            results["E3_discretization"] = self._run_discretization_analysis()

            # E4: Failure detection
            self.logger.info("Running E4: Failure detection")
            results["E4_failures"] = self._run_failure_detection()

            # E5: Phase mapping
            self.logger.info("Running E5: Phase mapping")
            results["E5_phase_mapping"] = self._run_phase_mapping()

            # E6: Performance analysis
            self.logger.info("Running E6: Performance analysis")
            results["E6_performance"] = self._run_performance_analysis()

            # Overall assessment
            results["overall_assessment"] = self._assess_overall_results(results)

        except Exception as e:
            self.logger.error(f"Error in Level E experiments: {e}")
            results["error"] = str(e)

        self.logger.info("Level E experiments completed")
        return results

    def _run_sensitivity_analysis(self) -> Dict[str, Any]:
        """Run sensitivity analysis (E1)."""
        try:
            # Extract sensitivity parameters
            sensitivity_params = self.experiment_parameters["E1_sensitivity"]
            n_samples = sensitivity_params.get("lhs_samples", 1000)

            # Run sensitivity analysis
            sensitivity_results = (
                self.sensitivity_analyzer.analyze_parameter_sensitivity(n_samples)
            )

            # Analyze mass-complexity correlation
            mass_complexity_results = (
                self.sensitivity_analyzer.analyze_mass_complexity_correlation(
                    sensitivity_results["samples"], sensitivity_results["outputs"]
                )
            )

            # Combine results
            results = {
                "sensitivity_analysis": sensitivity_results,
                "mass_complexity_analysis": mass_complexity_results,
                "status": "completed",
            }

            return results

        except Exception as e:
            self.logger.error(f"Error in sensitivity analysis: {e}")
            return {"error": str(e), "status": "failed"}

    def _run_robustness_testing(self) -> Dict[str, Any]:
        """Run robustness testing (E2)."""
        try:
            # Extract robustness parameters
            robustness_params = self.experiment_parameters["E2_robustness"]
            noise_levels = robustness_params.get(
                "noise_levels", [0.0, 0.05, 0.1, 0.15, 0.2]
            )
            parameter_uncertainty = robustness_params.get("parameter_uncertainty", {})
            geometry_perturbations = robustness_params.get("geometry_perturbations", [])

            # Run noise robustness tests
            noise_results = self.robustness_tester.test_noise_robustness(noise_levels)

            # Run parameter uncertainty tests
            param_results = self.robustness_tester.test_parameter_uncertainty(
                parameter_uncertainty
            )

            # Run geometry perturbation tests
            geometry_results = self.robustness_tester.test_geometry_perturbations(
                geometry_perturbations
            )

            # Combine results
            results = {
                "noise_robustness": noise_results,
                "parameter_uncertainty": param_results,
                "geometry_perturbations": geometry_results,
                "status": "completed",
            }

            return results

        except Exception as e:
            self.logger.error(f"Error in robustness testing: {e}")
            return {"error": str(e), "status": "failed"}

    def _run_discretization_analysis(self) -> Dict[str, Any]:
        """Run discretization analysis (E3)."""
        try:
            # Extract discretization parameters
            discretization_params = self.experiment_parameters["E3_discretization"]
            grid_sizes = discretization_params.get("grid_sizes", [64, 128, 256, 512])
            domain_sizes = discretization_params.get(
                "domain_sizes", [10.0, 15.0, 20.0, 25.0, 30.0]
            )
            time_steps = discretization_params.get(
                "time_steps", [0.001, 0.005, 0.01, 0.02, 0.05]
            )

            # Run grid convergence analysis
            grid_results = self.discretization_analyzer.analyze_grid_convergence(
                grid_sizes
            )

            # Run domain size analysis
            domain_results = self.discretization_analyzer.analyze_domain_size_effects(
                domain_sizes
            )

            # Run time step analysis
            time_results = self.discretization_analyzer.analyze_time_step_stability(
                time_steps
            )

            # Combine results
            results = {
                "grid_convergence": grid_results,
                "domain_size_effects": domain_results,
                "time_step_stability": time_results,
                "status": "completed",
            }

            return results

        except Exception as e:
            self.logger.error(f"Error in discretization analysis: {e}")
            return {"error": str(e), "status": "failed"}

    def _run_failure_detection(self) -> Dict[str, Any]:
        """Run failure detection (E4)."""
        try:
            # Run failure detection
            failure_results = self.failure_detector.detect_failures()

            # Analyze failure boundaries
            failure_params = self.experiment_parameters["E4_failures"]
            parameter_ranges = failure_params.get("parameter_ranges", {})

            if parameter_ranges:
                boundary_results = self.failure_detector.analyze_failure_boundaries(
                    parameter_ranges
                )
                failure_results["boundary_analysis"] = boundary_results

            # Combine results
            results = {"failure_detection": failure_results, "status": "completed"}

            return results

        except Exception as e:
            self.logger.error(f"Error in failure detection: {e}")
            return {"error": str(e), "status": "failed"}

    def _run_phase_mapping(self) -> Dict[str, Any]:
        """Run phase mapping (E5)."""
        try:
            # Run phase mapping
            phase_mapping_results = self.phase_mapper.map_phases()

            # Classify resonances if data available
            resonance_data = self.config.get("resonance_data", [])
            if resonance_data:
                resonance_classification = self.phase_mapper.classify_resonances(
                    resonance_data
                )
                phase_mapping_results["resonance_classification"] = (
                    resonance_classification
                )

            # Combine results
            results = {"phase_mapping": phase_mapping_results, "status": "completed"}

            return results

        except Exception as e:
            self.logger.error(f"Error in phase mapping: {e}")
            return {"error": str(e), "status": "failed"}

    def _run_performance_analysis(self) -> Dict[str, Any]:
        """Run performance analysis (E6)."""
        try:
            # Run performance analysis
            performance_results = self.performance_analyzer.analyze_performance()

            # Combine results
            results = {
                "performance_analysis": performance_results,
                "status": "completed",
            }

            return results

        except Exception as e:
            self.logger.error(f"Error in performance analysis: {e}")
            return {"error": str(e), "status": "failed"}

    def _assess_overall_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall results of Level E experiments."""
        # Check completion status
        completed_experiments = []
        failed_experiments = []

        for experiment_name, experiment_results in results.items():
            if experiment_name == "overall_assessment":
                continue

            if isinstance(experiment_results, dict):
                status = experiment_results.get("status", "unknown")
                if status == "completed":
                    completed_experiments.append(experiment_name)
                elif status == "failed":
                    failed_experiments.append(experiment_name)

        # Overall assessment
        total_experiments = len(completed_experiments) + len(failed_experiments)
        success_rate = (
            len(completed_experiments) / total_experiments
            if total_experiments > 0
            else 0
        )

        if success_rate >= 0.9:
            overall_status = "excellent"
        elif success_rate >= 0.7:
            overall_status = "good"
        elif success_rate >= 0.5:
            overall_status = "fair"
        else:
            overall_status = "poor"

        # Generate recommendations
        recommendations = self._generate_recommendations(results)

        return {
            "overall_status": overall_status,
            "success_rate": success_rate,
            "completed_experiments": completed_experiments,
            "failed_experiments": failed_experiments,
            "recommendations": recommendations,
        }

    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on results."""
        recommendations = []

        # Check sensitivity analysis results
        if (
            "E1_sensitivity" in results
            and results["E1_sensitivity"].get("status") == "completed"
        ):
            sensitivity_results = results["E1_sensitivity"].get(
                "sensitivity_analysis", {}
            )
            stability_metrics = sensitivity_results.get("stability_metrics", {})

            if not stability_metrics.get("is_converged", False):
                recommendations.append(
                    "Sensitivity analysis did not converge - consider increasing sample size"
                )

            if stability_metrics.get("dominance_ratio", 1) > 10:
                recommendations.append(
                    "High parameter dominance detected - consider parameter scaling"
                )

        # Check robustness results
        if (
            "E2_robustness" in results
            and results["E2_robustness"].get("status") == "completed"
        ):
            robustness_results = results["E2_robustness"]

            for noise_level, noise_results in robustness_results.get(
                "noise_robustness", {}
            ).items():
                if noise_results.get("degradation", {}).get("degradation", 0) > 0.5:
                    recommendations.append(
                        f"High degradation at noise level {noise_level} - consider noise reduction"
                    )

        # Check discretization results
        if (
            "E3_discretization" in results
            and results["E3_discretization"].get("status") == "completed"
        ):
            discretization_results = results["E3_discretization"]
            grid_results = discretization_results.get("grid_convergence", {})
            convergence_analysis = grid_results.get("convergence_analysis", {})

            if (
                convergence_analysis.get("overall_convergence", {}).get(
                    "overall_rate", 0
                )
                < 1.0
            ):
                recommendations.append(
                    "Poor convergence detected - consider grid refinement"
                )

        # Check failure detection results
        if (
            "E4_failures" in results
            and results["E4_failures"].get("status") == "completed"
        ):
            failure_results = results["E4_failures"].get("failure_detection", {})
            overall_assessment = failure_results.get("overall_assessment", {})

            if overall_assessment.get("status") == "critical":
                recommendations.append(
                    "Critical failures detected - review system parameters"
                )

        # Check performance results
        if (
            "E6_performance" in results
            and results["E6_performance"].get("status") == "completed"
        ):
            performance_results = results["E6_performance"].get(
                "performance_analysis", {}
            )
            scaling_analysis = performance_results.get("scaling_analysis", {})
            overall_scaling = scaling_analysis.get("overall_scaling", {})

            if overall_scaling.get("overall_assessment") == "poor":
                recommendations.append(
                    "Poor scaling performance - consider algorithm optimization"
                )

        return recommendations
