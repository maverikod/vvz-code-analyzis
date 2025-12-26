"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Advanced power law analysis for BVP framework.

This module implements comprehensive power law analysis for the
7D BVP field, including scaling regions, critical exponents,
and correlation functions according to the theoretical framework.

Physical Meaning:
    Analyzes power law behavior in the BVP field, including
    scaling regions, critical exponents, and correlation
    functions according to the theoretical framework.

Mathematical Foundation:
    Implements power law analysis with proper scaling behavior
    and critical exponent computation for 7D phase field theory.

Example:
    >>> analyzer = PowerLawAnalysis(domain_7d, config)
    >>> results = analyzer.analyze_power_law(field)
    >>> print(f"Critical exponent: {results['critical_exponent']}")
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
from scipy.optimize import curve_fit
from scipy.stats import linregress

from ..domain import Domain
from .bvp_constants import BVPConstants
from .memory_decorator import memory_protected_class_method


class PowerLawAnalysis:
    """
    Advanced power law analysis for BVP framework.

    Physical Meaning:
        Analyzes power law behavior in the BVP field, including
        scaling regions, critical exponents, and correlation
        functions according to the theoretical framework.

    Mathematical Foundation:
        Implements power law analysis with proper scaling behavior
        and critical exponent computation for 7D phase field theory.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ):
        """
        Initialize power law analyzer.

        Physical Meaning:
            Sets up the power law analyzer with the computational domain
            and configuration parameters for analyzing scaling behavior
            in the BVP field.

        Args:
            domain (Domain): Computational domain for analysis.
            config (Dict[str, Any]): Analysis configuration including:
                - scaling_range: Range of scales to analyze
                - critical_threshold: Threshold for critical behavior
                - correlation_length: Characteristic correlation length
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants or BVPConstants(config)
        self._setup_analysis_parameters()

    def _setup_analysis_parameters(self) -> None:
        """
        Setup analysis parameters.

        Physical Meaning:
            Initializes parameters for power law analysis based on
            the domain properties and configuration.
        """
        # Scaling analysis parameters
        self.scaling_range = self.config.get("scaling_range", (0.1, 10.0))
        self.critical_threshold = self.config.get("critical_threshold", 0.5)
        self.correlation_length = self.config.get("correlation_length", 1.0)

        # Analysis precision
        self.min_points = self.config.get("min_points", 10)
        self.max_points = self.config.get("max_points", 1000)
        self.tolerance = self.config.get("tolerance", 1e-6)

    @memory_protected_class_method(
        memory_threshold=0.8, shape_param="field", dtype_param="field"
    )
    def analyze_power_law(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Analyze power law behavior in the field.

        Physical Meaning:
            Computes power law exponents and scaling behavior
            in the BVP field according to the theoretical framework.

        Mathematical Foundation:
            Analyzes the scaling behavior C(r) ~ r^(-α) where
            α is the critical exponent and C(r) is the correlation function.

        Args:
            field (np.ndarray): BVP field for analysis.

        Returns:
            Dict[str, Any]: Analysis results including:
                - critical_exponent: Critical exponent α
                - scaling_region: Range of scales with power law behavior
                - correlation_function: Computed correlation function
                - quality_metrics: Quality of the power law fit
        """
        # Compute correlation function
        correlation_func = self._compute_correlation_function(field)

        # Analyze scaling behavior
        scaling_analysis = self._analyze_scaling_behavior(correlation_func)

        # Compute critical exponent
        critical_exponent = self._compute_critical_exponent(
            correlation_func, scaling_analysis
        )

        # Compute quality metrics
        quality_metrics = self._compute_quality_metrics(
            correlation_func, scaling_analysis
        )

        return {
            "critical_exponent": critical_exponent,
            "scaling_region": scaling_analysis["scaling_region"],
            "correlation_function": correlation_func,
            "quality_metrics": quality_metrics,
            "scaling_analysis": scaling_analysis,
        }

    def _compute_correlation_function(self, field: np.ndarray) -> np.ndarray:
        """
        Compute correlation function for power law analysis.

        Physical Meaning:
            Computes the spatial correlation function C(r) which
            characterizes the scaling behavior of the BVP field.

        Mathematical Foundation:
            C(r) = ⟨φ(x)φ(x+r)⟩ where φ is the field and r is the distance.

        Args:
            field (np.ndarray): BVP field for analysis.

        Returns:
            np.ndarray: Correlation function C(r).
        """
        # Compute field magnitude
        field_magnitude = np.abs(field)

        # Compute spatial correlation function
        # For 7D field, we need to handle all dimensions
        correlation_func = np.zeros(self.domain.shape[0])  # Use first spatial dimension

        for r in range(self.domain.shape[0]):
            # Compute correlation at distance r
            correlation_sum = 0.0
            count = 0

            for i in range(self.domain.shape[0] - r):
                # Compute correlation between points at distance r
                correlation_sum += np.mean(field_magnitude[i] * field_magnitude[i + r])
                count += 1

            if count > 0:
                correlation_func[r] = correlation_sum / count

        return correlation_func

    def _analyze_scaling_behavior(self, correlation_func: np.ndarray) -> Dict[str, Any]:
        """
        Analyze scaling behavior in correlation function.

        Physical Meaning:
            Identifies regions of power law behavior in the
            correlation function and determines scaling properties.

        Mathematical Foundation:
            Identifies regions where C(r) ~ r^(-α) with
            constant exponent α.

        Args:
            correlation_func (np.ndarray): Correlation function.

        Returns:
            Dict[str, Any]: Scaling analysis results.
        """
        # Find scaling region
        scaling_region = self._find_scaling_region(correlation_func)

        # Compute scaling properties
        scaling_properties = self._compute_scaling_properties(
            correlation_func, scaling_region
        )

        return {
            "scaling_region": scaling_region,
            "scaling_properties": scaling_properties,
        }

    def _find_scaling_region(self, correlation_func: np.ndarray) -> Tuple[int, int]:
        """
        Find region of power law behavior.

        Physical Meaning:
            Identifies the range of distances where the correlation
            function exhibits power law behavior.

        Args:
            correlation_func (np.ndarray): Correlation function.

        Returns:
            Tuple[int, int]: Start and end indices of scaling region.
        """
        # Find region with significant correlation
        significant_indices = np.where(correlation_func > self.critical_threshold)[0]

        if len(significant_indices) < self.min_points:
            return (0, min(len(correlation_func), self.min_points))

        # Find largest continuous region
        start_idx = significant_indices[0]
        end_idx = significant_indices[-1]

        # Ensure minimum size
        if end_idx - start_idx < self.min_points:
            end_idx = min(start_idx + self.min_points, len(correlation_func))

        return (start_idx, end_idx)

    def _compute_scaling_properties(
        self, correlation_func: np.ndarray, scaling_region: Tuple[int, int]
    ) -> Dict[str, Any]:
        """
        Compute scaling properties in the scaling region.

        Physical Meaning:
            Computes the scaling properties including the power law
            exponent and scaling quality in the identified region.

        Args:
            correlation_func (np.ndarray): Correlation function.
            scaling_region (Tuple[int, int]): Scaling region indices.

        Returns:
            Dict[str, Any]: Scaling properties.
        """
        start_idx, end_idx = scaling_region

        # Extract scaling region
        r_values = np.arange(start_idx, end_idx)
        c_values = correlation_func[start_idx:end_idx]

        # Remove zero and negative values
        valid_mask = (c_values > 0) & (r_values > 0)
        r_values = r_values[valid_mask]
        c_values = c_values[valid_mask]

        if len(r_values) < 2:
            return {"exponent": 0.0, "quality": 0.0}

        # Compute power law fit
        try:
            # Linear fit in log space: log(C) = -α*log(r) + const
            log_r = np.log(r_values)
            log_c = np.log(c_values)

            slope, intercept, r_value, p_value, std_err = linregress(log_r, log_c)

            return {
                "exponent": -slope,  # Negative slope is the exponent
                "quality": r_value**2,  # R-squared
                "p_value": p_value,
                "std_error": std_err,
            }
        except:
            return {"exponent": 0.0, "quality": 0.0}

    def _compute_critical_exponent(
        self, correlation_func: np.ndarray, scaling_analysis: Dict[str, Any]
    ) -> float:
        """
        Compute critical exponent from scaling analysis.

        Physical Meaning:
            Computes the critical exponent α from the power law
            behavior C(r) ~ r^(-α) in the scaling region.

        Args:
            correlation_func (np.ndarray): Correlation function.
            scaling_analysis (Dict[str, Any]): Scaling analysis results.

        Returns:
            float: Critical exponent α.
        """
        scaling_properties = scaling_analysis.get("scaling_properties", {})
        return scaling_properties.get("exponent", 0.0)

    def _compute_quality_metrics(
        self, correlation_func: np.ndarray, scaling_analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Compute quality metrics for the power law analysis.

        Physical Meaning:
            Computes metrics to assess the quality of the power law
            fit and scaling behavior identification.

        Args:
            correlation_func (np.ndarray): Correlation function.
            scaling_analysis (Dict[str, Any]): Scaling analysis results.

        Returns:
            Dict[str, float]: Quality metrics.
        """
        scaling_properties = scaling_analysis.get("scaling_properties", {})

        return {
            "r_squared": scaling_properties.get("quality", 0.0),
            "p_value": scaling_properties.get("p_value", 1.0),
            "std_error": scaling_properties.get("std_error", 0.0),
            "scaling_region_size": len(scaling_analysis.get("scaling_region", (0, 0))),
        }

    def get_analysis_parameters(self) -> Dict[str, Any]:
        """
        Get current analysis parameters.

        Physical Meaning:
            Returns the current parameters used for power law analysis.

        Returns:
            Dict[str, Any]: Analysis parameters.
        """
        return {
            "scaling_range": self.scaling_range,
            "critical_threshold": self.critical_threshold,
            "correlation_length": self.correlation_length,
            "min_points": self.min_points,
            "max_points": self.max_points,
            "tolerance": self.tolerance,
        }


# Backward compatibility
from .power_law import PowerLawCore

__all__ = ["PowerLawAnalysis", "PowerLawCore"]
