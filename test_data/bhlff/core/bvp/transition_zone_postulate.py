"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Transition Zone Postulate implementation for BVP framework.

This module implements Postulate 7 of the BVP framework, which states that
the transition zone is a nonlinear interface that sets nonlinear admittance
Y_tr(ω,|A|) and generates effective EM/weak currents J(ω) from envelope.

Theoretical Background:
    The transition zone acts as a nonlinear interface between core and tail,
    with admittance that depends on both frequency and amplitude. This
    nonlinearity generates effective electromagnetic and weak currents.

Example:
    >>> postulate = TransitionZonePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any
from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate


class TransitionZonePostulate(BVPPostulate):
    """
    Postulate 7: Transition Zone = Nonlinear Interface.

    Physical Meaning:
        Transition zone sets nonlinear admittance Y_tr(ω,|A|)
        and generates effective EM/weak currents J(ω) from envelope.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize transition zone postulate.

        Physical Meaning:
            Sets up the postulate for analyzing nonlinear interface
            behavior in the transition zone.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.nonlinear_threshold = constants.get_quench_parameter("nonlinear_threshold")
        self.current_threshold = constants.get_quench_parameter("current_threshold")

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply transition zone postulate.

        Physical Meaning:
            Verifies that the transition zone exhibits nonlinear
            admittance characteristics and generates effective
            EM/weak currents from the envelope.

        Mathematical Foundation:
            Analyzes nonlinear admittance Y_tr(ω,|A|) and
            computes effective currents J(ω) as functionals
            of the envelope amplitude.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including nonlinear admittance,
                effective currents, and transition zone properties.
        """
        # Compute nonlinear admittance
        nonlinear_admittance = self._compute_nonlinear_admittance(envelope)

        # Generate effective currents
        effective_currents = self._generate_effective_currents(envelope)

        # Analyze transition zone properties
        transition_properties = self._analyze_transition_zone_properties(envelope)

        # Validate nonlinear interface
        is_nonlinear_interface = self._validate_nonlinear_interface(
            nonlinear_admittance, effective_currents
        )

        return {
            "nonlinear_admittance": nonlinear_admittance,
            "effective_currents": effective_currents,
            "transition_properties": transition_properties,
            "is_nonlinear_interface": is_nonlinear_interface,
            "postulate_satisfied": is_nonlinear_interface,
        }

    def _compute_nonlinear_admittance(
        self, envelope: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Compute nonlinear admittance Y_tr(ω,|A|).

        Physical Meaning:
            Calculates admittance that depends on both frequency
            and amplitude, representing nonlinear interface behavior.

        Mathematical Foundation:
            Y_tr(ω,|A|) = Y_0(ω) * (1 + α|A|² + β|A|⁴)

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, np.ndarray]: Nonlinear admittance components.
        """
        amplitude = np.abs(envelope)

        # Nonlinear admittance depends on amplitude
        # Y_tr(ω,|A|) = Y_0(ω) * (1 + α|A|² + β|A|⁴)
        alpha = self.constants.get_envelope_parameter("nonlinear_alpha")
        beta = self.constants.get_envelope_parameter("nonlinear_beta")

        nonlinear_factor = 1 + alpha * amplitude**2 + beta * amplitude**4
        base_admittance = self._compute_base_admittance(envelope)

        nonlinear_admittance = base_admittance * nonlinear_factor

        return {
            "base_admittance": base_admittance,
            "nonlinear_factor": nonlinear_factor,
            "total_admittance": nonlinear_admittance,
        }

    def _compute_base_admittance(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute base linear admittance.

        Physical Meaning:
            Calculates linear component of admittance from
            envelope gradient and amplitude using full transmission line theory.

        Mathematical Foundation:
            Base admittance Y_0 = (1/Z_0) * (∇A/A) where:
            - Z_0 is characteristic impedance
            - ∇A is envelope gradient
            - A is envelope amplitude

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            np.ndarray: Base linear admittance.
        """
        amplitude = np.abs(envelope)

        # Compute spatial gradient of envelope amplitude
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)

        # Get characteristic impedance from material properties
        vacuum_permeability = self.constants.get_physical_constant(
            "vacuum_permeability"
        )
        vacuum_permittivity = self.constants.get_physical_constant(
            "vacuum_permittivity"
        )
        z0_characteristic = np.sqrt(vacuum_permeability / vacuum_permittivity)

        # Compute base admittance using transmission line theory
        # Y_0 = (1/Z_0) * (∇A/A)
        base_admittance = gradient / (z0_characteristic * (amplitude + 1e-12))

        return base_admittance

    def _generate_effective_currents(
        self, envelope: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Generate effective EM/weak currents J(ω) from envelope.

        Physical Meaning:
            Computes electromagnetic and weak currents as functionals
            of the envelope amplitude and phase.

        Mathematical Foundation:
            - EM current: gradient of phase
            - Weak current: nonlinear function of amplitude
            - Mixed current: product of EM and weak currents

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, np.ndarray]: Effective current components.
        """
        amplitude = np.abs(envelope)
        phase = np.angle(envelope)

        # EM current as gradient of phase
        em_current = np.gradient(phase, self.domain.dx, axis=0)

        # Weak current as nonlinear function of amplitude
        weak_current = amplitude**2 * np.gradient(amplitude, self.domain.dx, axis=0)

        # Mixed electroweak current
        mixed_current = em_current * weak_current

        return {
            "em_current": em_current,
            "weak_current": weak_current,
            "mixed_current": mixed_current,
        }

    def _analyze_transition_zone_properties(
        self, envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze properties of the transition zone.

        Physical Meaning:
            Computes transition zone boundaries, nonlinearity strength,
            and current generation efficiency.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Transition zone properties.
        """
        amplitude = np.abs(envelope)

        # Compute transition zone boundaries
        boundaries = self._compute_transition_boundaries(amplitude)

        # Analyze nonlinearity strength
        nonlinearity_strength = self._compute_nonlinearity_strength(amplitude)

        # Compute current generation efficiency
        current_efficiency = self._compute_current_efficiency(amplitude)

        return {
            "boundaries": boundaries,
            "nonlinearity_strength": nonlinearity_strength,
            "current_efficiency": current_efficiency,
        }

    def _compute_transition_boundaries(self, amplitude: np.ndarray) -> Dict[str, float]:
        """
        Compute boundaries of the transition zone.

        Physical Meaning:
            Identifies inner and outer boundaries of transition zone
            based on amplitude gradient thresholds.

        Args:
            amplitude (np.ndarray): Envelope amplitude.

        Returns:
            Dict[str, float]: Boundary parameters.
        """
        # Find regions where amplitude changes significantly
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)
        gradient_magnitude = np.abs(gradient)

        # Define boundaries based on gradient thresholds
        inner_boundary = np.percentile(gradient_magnitude, 25)
        outer_boundary = np.percentile(gradient_magnitude, 75)

        return {
            "inner_boundary": inner_boundary,
            "outer_boundary": outer_boundary,
            "transition_width": outer_boundary - inner_boundary,
        }

    def _compute_nonlinearity_strength(self, amplitude: np.ndarray) -> float:
        """
        Compute strength of nonlinearity in transition zone.

        Physical Meaning:
            Quantifies nonlinearity strength based on amplitude
            variation relative to mean amplitude.

        Args:
            amplitude (np.ndarray): Envelope amplitude.

        Returns:
            float: Nonlinearity strength measure.
        """
        # Nonlinearity strength based on amplitude variation
        amplitude_variance = np.var(amplitude)
        return amplitude_variance / (np.mean(amplitude) + 1e-12)

    def _compute_current_efficiency(self, amplitude: np.ndarray) -> float:
        """
        Compute efficiency of current generation.

        Physical Meaning:
            Calculates efficiency of current generation based on
            amplitude gradients relative to mean amplitude.

        Args:
            amplitude (np.ndarray): Envelope amplitude.

        Returns:
            float: Current generation efficiency.
        """
        # Current generation efficiency based on amplitude gradients
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)
        gradient_magnitude = np.abs(gradient)
        return np.mean(gradient_magnitude) / (np.mean(amplitude) + 1e-12)

    def _validate_nonlinear_interface(
        self,
        nonlinear_admittance: Dict[str, np.ndarray],
        effective_currents: Dict[str, np.ndarray],
    ) -> bool:
        """
        Validate that the transition zone is a nonlinear interface.

        Physical Meaning:
            Checks nonlinearity strength and current generation
            to confirm nonlinear interface behavior.

        Args:
            nonlinear_admittance (Dict[str, np.ndarray]): Nonlinear admittance.
            effective_currents (Dict[str, np.ndarray]): Effective currents.

        Returns:
            bool: True if nonlinear interface behavior is confirmed.
        """
        # Check nonlinearity strength
        nonlinear_factor = nonlinear_admittance["nonlinear_factor"]
        nonlinearity_strength = np.mean(np.abs(nonlinear_factor - 1))

        # Check current generation
        em_current = effective_currents["em_current"]
        current_magnitude = np.mean(np.abs(em_current))

        return (
            nonlinearity_strength > self.nonlinear_threshold
            and current_magnitude > self.current_threshold
        )
