"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Critical exponents analysis module for power law analysis.

This module implements critical exponent analysis for the 7D phase field theory,
including computation of all standard critical exponents and universality class determination.

Physical Meaning:
    Analyzes critical behavior of the BVP field using complete 7D critical
    exponent analysis according to the 7D phase field theory.

Mathematical Foundation:
    Implements full critical exponent analysis:
    - ν: correlation length exponent
    - β: order parameter exponent
    - γ: susceptibility exponent
    - δ: critical isotherm exponent
    - η: anomalous dimension
    - α: specific heat exponent
    - z: dynamic exponent
"""

import numpy as np
from typing import Dict, Any, List
import logging

from bhlff.core.bvp import BVPCore
from .estimators import (
    estimate_nu_from_correlation_length as _est_nu,
    estimate_beta_from_tail as _est_beta,
    estimate_chi_from_variance as _est_gamma,
)
from .scaling_functions import (
    compute_correlation_scaling_function as _corr_scaling,
    compute_susceptibility_scaling_function as _sus_scaling,
    compute_order_parameter_scaling_function as _op_scaling,
    identify_critical_regions as _identify_regions,
)
from .anomalous_dimension import compute_anomalous_dimension as _est_eta
from .dynamic_exponent_calculator import DynamicExponentCalculator
from .scaling_relations import ScalingRelations
from .universality_classifier import UniversalityClassifier


class CriticalExponents:
    """
    Critical exponents analysis for BVP field.

    Physical Meaning:
        Computes the complete set of critical exponents for the 7D BVP field
        according to critical phenomena theory.
    """

    def __init__(self, bvp_core: BVPCore):
        """Initialize critical exponents analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.dynamic_calculator = DynamicExponentCalculator(bvp_core)
        self.scaling_relations = ScalingRelations()
        self.universality_classifier = UniversalityClassifier()

    def analyze_critical_behavior(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze critical behavior with full 7D critical exponents.

        Physical Meaning:
            Analyzes critical behavior of the BVP field using
            complete 7D critical exponent analysis according to
            the 7D phase field theory.
        """
        amplitude = np.abs(envelope)

        # Compute full set of critical exponents
        critical_exponents = self._compute_full_critical_exponents(amplitude)

        # Analyze critical regions
        critical_regions = self._identify_critical_regions(
            amplitude, critical_exponents
        )

        # Compute scaling dimension
        scaling_dimension = self._compute_7d_scaling_dimension(critical_exponents)

        # Determine universality class
        universality_class = self._determine_universality_class(critical_exponents)

        # Compute critical scaling functions
        critical_scaling = self._compute_critical_scaling_functions(
            amplitude, critical_exponents
        )

        return {
            "critical_exponents": critical_exponents,
            "critical_regions": critical_regions,
            "scaling_dimension": scaling_dimension,
            "universality_class": universality_class,
            "critical_scaling": critical_scaling,
        }

    def _compute_full_critical_exponents(
        self, amplitude: np.ndarray
    ) -> Dict[str, float]:
        """Compute full set of critical exponents."""
        # Compute correlation length exponent ν
        nu = self._compute_correlation_length_exponent(amplitude)

        # Compute order parameter exponent β
        beta = self._compute_order_parameter_exponent(amplitude)

        # Compute susceptibility exponent γ
        gamma = self._compute_susceptibility_exponent(amplitude)

        # Compute critical isotherm exponent δ
        delta = self._compute_critical_isotherm_exponent(amplitude)

        # Compute anomalous dimension η
        eta = self._compute_anomalous_dimension(amplitude)

        # Compute specific heat exponent α
        alpha = self._compute_specific_heat_exponent(amplitude)

        # Compute dynamic exponent z
        z = self._compute_dynamic_exponent(amplitude)

        return {
            "nu": float(nu),  # correlation length exponent
            "beta": float(beta),  # order parameter exponent
            "gamma": float(gamma),  # susceptibility exponent
            "delta": float(delta),  # critical isotherm exponent
            "eta": float(eta),  # anomalous dimension
            "alpha": float(alpha),  # specific heat exponent
            "z": float(z),  # dynamic exponent
        }

    def _compute_correlation_length_exponent(self, amplitude: np.ndarray) -> float:
        """Compute correlation length exponent ν."""
        return self.estimate_nu_from_correlation_length(amplitude)

    def _compute_order_parameter_exponent(self, amplitude: np.ndarray) -> float:
        """Compute order parameter exponent β."""
        return self.estimate_beta_from_tail(amplitude)

    def _compute_susceptibility_exponent(self, amplitude: np.ndarray) -> float:
        """
        Compute susceptibility exponent γ from actual susceptibility scaling.

        Physical Meaning:
            Computes susceptibility exponent γ from the scaling law
            χ ~ |A - A_c|^(-γ), where A is the order parameter and A_c
            is the critical point. This exponent characterizes how
            susceptibility diverges near the critical point.

        Mathematical Foundation:
            Susceptibility is defined as χ = ∂²F/∂h², where F is the
            free energy and h is the field. Near critical point,
            χ diverges as χ ~ |t|^(-γ) where t is the reduced control
            parameter. In BVP model, we use amplitude deviation from
            critical value as control parameter.

        Args:
            amplitude (np.ndarray): Field amplitude distribution

        Returns:
            float: Susceptibility exponent γ (bounded between 0.5 and 2.0)
        """
        return self.estimate_chi_from_variance(amplitude)

    # -------------------- Thin wrappers using helper modules --------------------
    def estimate_nu_from_correlation_length(self, amplitude: np.ndarray) -> float:
        return _est_nu(self.bvp_core, amplitude)

    def estimate_beta_from_tail(self, amplitude: np.ndarray) -> float:
        return _est_beta(amplitude)

    def estimate_chi_from_variance(self, amplitude: np.ndarray) -> float:
        return _est_gamma(amplitude)

    def _compute_critical_isotherm_exponent(self, amplitude: np.ndarray) -> float:
        """
        Compute critical isotherm exponent δ using scaling relation.

        Physical Meaning:
            Computes critical isotherm exponent δ from scaling relation
            δ = (γ + β) / β. This exponent characterizes the critical
            isotherm behavior M ~ H^(1/δ) at T = T_c.

        Mathematical Foundation:
            Uses scaling relation: δ = (γ + β) / β
            where:
            - γ: susceptibility exponent
            - β: order parameter exponent
            This follows from scaling theory in critical phenomena.

        Args:
            amplitude (np.ndarray): Field amplitude distribution.

        Returns:
            float: Critical isotherm exponent δ.

        Raises:
            ValueError: If β ≤ 0 or computed δ is not finite.
        """
        # Use scaling relation: δ = (γ + β) / β
        beta = self._compute_order_parameter_exponent(amplitude)
        gamma = self._compute_susceptibility_exponent(amplitude)

        return self.scaling_relations.compute_critical_isotherm_exponent(beta, gamma)

    def _compute_anomalous_dimension(self, amplitude: np.ndarray) -> float:
        """Compute anomalous dimension η."""
        return _est_eta(self.bvp_core, amplitude)

    def _compute_specific_heat_exponent(self, amplitude: np.ndarray) -> float:
        """
        Compute specific heat exponent α using 7D scaling relation.

        Physical Meaning:
            Computes specific heat exponent α from scaling relation α = 2 - ν*d,
            where d=7 for 7D phase field theory. Specific heat diverges as
            C ~ |t|^{-α} near criticality.

        Mathematical Foundation:
            Uses scaling relation: α = 2 - ν*d where:
            - ν: correlation length exponent
            - d: space-time dimension (7 for 7D BVP theory)
            This follows from hyperscaling relation in critical phenomena.

        Args:
            amplitude (np.ndarray): Field amplitude distribution.

        Returns:
            float: Specific heat exponent α.

        Raises:
            ValueError: If computed α is not finite or violates scaling bounds.
        """
        # Use scaling relation: α = 2 - ν*d
        nu = self._compute_correlation_length_exponent(amplitude)
        # Explicit 7D dimension for 7D phase field theory
        d = 7

        return self.scaling_relations.compute_specific_heat_exponent(nu, d)

    def _compute_dynamic_exponent(self, amplitude: np.ndarray) -> float:
        """
        Compute dynamic exponent z from block-wise correlation time scaling.

        Physical Meaning:
            Computes dynamic exponent z from the scaling of relaxation time
            τ ~ ξ^z, where ξ is correlation length. This characterizes
            critical slowing down near the critical point. Uses block-wise
            analysis to estimate z from temporal correlation structure.

        Mathematical Foundation:
            Dynamic exponent relates relaxation time to correlation length:
            τ ~ ξ^z. For BVP field, we estimate z from block-wise amplitude
            fluctuation correlations using robust regression on log-log scale.
            Estimates z from fitting log(τ) ~ z*log(ξ) across blocks.

        Args:
            amplitude (np.ndarray): Field amplitude distribution.

        Returns:
            float: Dynamic exponent z.

        Raises:
            ValueError: If insufficient block data or z is not finite.
        """
        return self.dynamic_calculator.compute_dynamic_exponent(amplitude)

    def _identify_critical_regions(
        self, amplitude: np.ndarray, critical_exponents: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Identify critical regions with scaling analysis."""
        return _identify_regions(amplitude, critical_exponents)

    def _compute_7d_scaling_dimension(
        self, critical_exponents: Dict[str, float]
    ) -> float:
        """
        Compute effective 7D scaling dimension using scaling relation.

        Physical Meaning:
            Computes effective scaling dimension d_eff from scaling relation
            d_eff = 2 - α - β. This characterizes the effective dimension
            of the critical system in 7D phase field theory.

        Mathematical Foundation:
            Uses hyperscaling relation: d_eff = 2 - α - β
            where α and β are critical exponents. For 7D BVP theory,
            this gives the effective dimension of critical fluctuations.

        Args:
            critical_exponents (Dict[str, float]): Dictionary of critical exponents.

        Returns:
            float: Effective 7D scaling dimension.

        Raises:
            KeyError: If required exponents are missing.
            ValueError: If computed d_eff is not finite.
        """
        # Require explicit values (no defaults)
        if "alpha" not in critical_exponents:
            raise KeyError("Missing 'alpha' exponent for scaling dimension computation")
        if "beta" not in critical_exponents:
            raise KeyError("Missing 'beta' exponent for scaling dimension computation")

        alpha = critical_exponents["alpha"]
        beta = critical_exponents["beta"]

        return self.scaling_relations.compute_7d_scaling_dimension(alpha, beta)

    def _determine_universality_class(
        self, critical_exponents: Dict[str, float]
    ) -> str:
        """
        Determine universality class from critical exponents.

        Physical Meaning:
            Determines universality class by comparing computed critical
            exponents with known theoretical values.

        Args:
            critical_exponents (Dict[str, float]): Dictionary of critical exponents.

        Returns:
            str: Universality class identifier.
        """
        return self.universality_classifier.determine_universality_class(
            critical_exponents
        )

    def _compute_critical_scaling_functions(
        self, amplitude: np.ndarray, critical_exponents: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute critical scaling functions."""
        # Compute scaling functions
        scaling_functions = {
            "correlation_scaling": self._compute_correlation_scaling_function(
                amplitude, critical_exponents
            ),
            "susceptibility_scaling": self._compute_susceptibility_scaling_function(
                amplitude, critical_exponents
            ),
            "order_parameter_scaling": self._compute_order_parameter_scaling_function(
                amplitude, critical_exponents
            ),
        }

        return scaling_functions

    def _compute_correlation_scaling_function(
        self, amplitude: np.ndarray, critical_exponents: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute correlation scaling function."""
        return _corr_scaling(self.bvp_core, amplitude, critical_exponents)

    def _compute_susceptibility_scaling_function(
        self, amplitude: np.ndarray, critical_exponents: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute susceptibility scaling function."""
        return _sus_scaling(amplitude, critical_exponents)

    def _compute_order_parameter_scaling_function(
        self, amplitude: np.ndarray, critical_exponents: Dict[str, float]
    ) -> Dict[str, Any]:
        """Compute order parameter scaling function."""
        return _op_scaling(amplitude, critical_exponents)
