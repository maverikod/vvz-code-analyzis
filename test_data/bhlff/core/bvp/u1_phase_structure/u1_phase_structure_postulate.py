"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

U(1)³ Phase Structure Postulate implementation for BVP framework.

This module implements Postulate 4 of the BVP framework, which states that
BVP has U(1)³ phase structure with phase vector Θ_a (a=1..3) and
phase coherence is maintained across the field.

Theoretical Background:
    The U(1)³ phase structure represents three independent phase degrees
    of freedom in the BVP field. Phase coherence ensures that phase
    relationships are maintained across spatial and temporal scales.

Example:
    >>> postulate = U1PhaseStructurePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain import Domain
from ..bvp_constants import BVPConstants
from ..bvp_postulate_base import BVPPostulate
from .phase_analysis import PhaseAnalysis
from .coherence_analysis import CoherenceAnalysis


class U1PhaseStructurePostulate(BVPPostulate):
    """
    Postulate 4: U(1)³ Phase Structure.

    Physical Meaning:
        BVP has U(1)³ phase structure with phase vector Θ_a (a=1..3)
        and phase coherence is maintained across the field.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize U(1)³ phase structure postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            analyzing U(1)³ phase structure properties.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.phase_coherence_threshold = constants.get_quench_parameter(
            "phase_coherence_threshold"
        )
        self.phase_variance_threshold = constants.get_quench_parameter(
            "phase_variance_threshold"
        )

        # Initialize analyzers
        self._phase_analyzer = PhaseAnalysis(domain)
        self._coherence_analyzer = CoherenceAnalysis(domain)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply U(1)³ phase structure postulate.

        Physical Meaning:
            Verifies that BVP field exhibits U(1)³ phase structure
            with proper phase coherence and phase vector properties.

        Mathematical Foundation:
            Analyzes phase components Θ_a (a=1..3) and their
            coherence properties across the field.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including phase structure analysis,
                phase coherence, and U(1)³ validation.
        """
        # Analyze phase structure
        phase_structure = self._phase_analyzer.analyze_phase_structure(envelope)

        # Analyze phase coherence
        phase_coherence = self._coherence_analyzer.analyze_phase_coherence(envelope)

        # Check U(1)³ properties
        u1_properties = self._check_u1_properties(phase_structure, phase_coherence)

        # Validate U(1)³ phase structure
        satisfies_postulate = self._validate_u1_phase_structure(u1_properties)

        return {
            "phase_structure": phase_structure,
            "phase_coherence": phase_coherence,
            "u1_properties": u1_properties,
            "satisfies_postulate": satisfies_postulate,
            "postulate_satisfied": satisfies_postulate,
        }

    def _check_u1_properties(
        self, phase_structure: Dict[str, Any], phase_coherence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check U(1)³ properties of the field.

        Physical Meaning:
            Verifies that field exhibits proper U(1)³ phase
            structure with adequate coherence.

        Args:
            phase_structure (Dict[str, Any]): Phase structure analysis.
            phase_coherence (Dict[str, Any]): Phase coherence analysis.

        Returns:
            Dict[str, Any]: U(1)³ properties.
        """
        # Check phase component independence
        phase_stats = phase_structure["phase_statistics"]
        independent_components = True

        for i in range(3):
            component_stats = phase_stats[f"component_{i}"]
            phase_variance = component_stats["phase_variance"]

            # Check if component has sufficient variance
            if phase_variance < self.phase_variance_threshold:
                independent_components = False
                break

        # Check phase coherence
        mean_local_coherence = phase_coherence["mean_local_coherence"]
        global_coherence = phase_coherence["global_coherence"]

        adequate_coherence = (
            mean_local_coherence > self.phase_coherence_threshold
            and global_coherence > self.phase_coherence_threshold
        )

        # Overall U(1)³ properties
        has_u1_structure = independent_components and adequate_coherence

        return {
            "independent_components": independent_components,
            "adequate_coherence": adequate_coherence,
            "has_u1_structure": has_u1_structure,
            "structure_quality": (mean_local_coherence + global_coherence) / 2,
        }

    def _validate_u1_phase_structure(self, u1_properties: Dict[str, Any]) -> bool:
        """
        Validate U(1)³ phase structure postulate.

        Physical Meaning:
            Checks that field exhibits proper U(1)³ phase
            structure for BVP framework validity.

        Args:
            u1_properties (Dict[str, Any]): U(1)³ properties.

        Returns:
            bool: True if U(1)³ phase structure is satisfied.
        """
        return u1_properties["has_u1_structure"]

    def __repr__(self) -> str:
        """String representation of U(1)³ phase structure postulate."""
        return (
            f"U1PhaseStructurePostulate("
            f"domain={self.domain}, "
            f"coherence_threshold={self.phase_coherence_threshold:.3f})"
        )
