"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Main BVP Postulates interface implementation.

This module provides the unified interface for all 9 BVP postulates,
coordinating their application and validation.

Theoretical Background:
    The BVP postulates form the foundation of the BVP framework,
    providing operational models for validating field properties
    and ensuring physical consistency.

Example:
    >>> postulates = BVPPostulates(domain, constants)
    >>> results = postulates.apply_all_postulates(envelope)
"""

import numpy as np
from typing import Dict, Any, List

from ..domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate
from .carrier_primacy_postulate import CarrierPrimacyPostulate
from .scale_separation_postulate import ScaleSeparationPostulate
from .bvp_rigidity_postulate import BVPRigidityPostulate
from .u1_phase_structure import U1PhaseStructurePostulate
from .quenches_postulate import QuenchesPostulate
from .tail_resonatorness_postulate import TailResonatornessPostulate
from .transition_zone_postulate import TransitionZonePostulate
from .core_renormalization_postulate import CoreRenormalizationPostulate
from .postulates.power_balance.power_balance_postulate import PowerBalancePostulate


class BVPPostulates:
    """
    Unified interface for all BVP postulates.

    Physical Meaning:
        Provides a unified interface to apply all 9 BVP postulates
        and validate BVP framework compliance.

    Mathematical Foundation:
        Coordinates the application of postulates 1-9:
        1. Carrier Primacy
        2. Scale Separation
        3. BVP Rigidity
        4. U(1)³ Phase Structure
        5. Quenches
        6. Tail Resonatorness
        7. Transition Zone
        8. Core Renormalization
        9. Power Balance
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize BVP postulates interface.

        Physical Meaning:
            Sets up all 9 BVP postulates with domain and constants
            for comprehensive field validation.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants

        # Initialize all 9 BVP postulates
        self.carrier_primacy = CarrierPrimacyPostulate(domain, constants)
        self.scale_separation = ScaleSeparationPostulate(domain, constants)
        self.bvp_rigidity = BVPRigidityPostulate(domain, constants)
        self.u1_phase_structure = U1PhaseStructurePostulate(domain, constants)
        self.quenches = QuenchesPostulate(domain, constants)
        self.tail_resonatorness = TailResonatornessPostulate(domain, constants)
        self.transition_zone = TransitionZonePostulate(domain, constants)
        self.core_renormalization = CoreRenormalizationPostulate(domain, constants)
        self.power_balance = PowerBalancePostulate(domain, constants)

    def apply_all_postulates(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Apply all BVP postulates to the envelope.

        Physical Meaning:
            Applies all 9 BVP postulates to verify that the envelope
            satisfies the BVP framework requirements.

        Args:
            envelope (np.ndarray): BVP envelope in 7D space-time.

        Returns:
            Dict[str, Any]: Results from all postulates.
        """
        results = {}

        # Apply all 9 BVP postulates
        results["carrier_primacy"] = self.carrier_primacy.apply(envelope)
        results["scale_separation"] = self.scale_separation.apply(envelope)
        results["bvp_rigidity"] = self.bvp_rigidity.apply(envelope)
        results["u1_phase_structure"] = self.u1_phase_structure.apply(envelope)
        results["quenches"] = self.quenches.apply(envelope)
        results["tail_resonatorness"] = self.tail_resonatorness.apply(envelope)
        results["transition_zone"] = self.transition_zone.apply(envelope)
        results["core_renormalization"] = self.core_renormalization.apply(envelope)
        results["power_balance"] = self.power_balance.apply(envelope)

        # Check overall satisfaction
        all_satisfied = all(
            result.get("postulate_satisfied", False) for result in results.values()
        )
        results["all_postulates_satisfied"] = all_satisfied

        return results

    def validate_bvp_framework(self, envelope: np.ndarray) -> bool:
        """
        Validate BVP framework compliance.

        Physical Meaning:
            Checks if the envelope satisfies all BVP postulates,
            indicating proper BVP framework compliance.

        Args:
            envelope (np.ndarray): BVP envelope to validate.

        Returns:
            bool: True if all postulates are satisfied.
        """
        results = self.apply_all_postulates(envelope)
        return results["all_postulates_satisfied"]

    def get_postulate_summary(self, envelope: np.ndarray) -> Dict[str, bool]:
        """
        Get summary of postulate satisfaction.

        Physical Meaning:
            Provides a quick overview of which postulates are
            satisfied and which need attention.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, bool]: Postulate satisfaction status.
        """
        results = self.apply_all_postulates(envelope)

        summary = {}
        for postulate_name, result in results.items():
            if postulate_name != "all_postulates_satisfied":
                summary[postulate_name] = result.get("postulate_satisfied", False)

        return summary

    def get_failed_postulates(self, envelope: np.ndarray) -> List[str]:
        """
        Get list of failed postulates.

        Physical Meaning:
            Identifies which postulates are not satisfied,
            helping to diagnose field issues.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            List[str]: List of failed postulate names.
        """
        summary = self.get_postulate_summary(envelope)
        return [name for name, satisfied in summary.items() if not satisfied]

    def get_postulate_quality_scores(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Get quality scores for each postulate.

        Physical Meaning:
            Provides quantitative measures of how well each
            postulate is satisfied.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, float]: Quality scores (0.0 to 1.0).
        """
        results = self.apply_all_postulates(envelope)

        quality_scores = {}
        for postulate_name, result in results.items():
            if postulate_name != "all_postulates_satisfied":
                # Extract quality measures from results
                quality_score = self._extract_quality_score(result)
                quality_scores[postulate_name] = quality_score

        return quality_scores

    def _extract_quality_score(self, result: Dict[str, Any]) -> float:
        """
        Extract quality score from postulate result.

        Physical Meaning:
            Computes a normalized quality score (0.0 to 1.0)
            from postulate analysis results.

        Args:
            result (Dict[str, Any]): Postulate result.

        Returns:
            float: Quality score.
        """
        # Look for quality measures in the result
        quality_measures = []

        # Check for common quality indicators
        for key, value in result.items():
            if isinstance(value, (int, float)) and "quality" in key.lower():
                quality_measures.append(value)
            elif isinstance(value, dict) and "quality" in key.lower():
                quality_measures.append(value.get("quality", 0.0))

        # Return average quality or default
        if quality_measures:
            return np.mean(quality_measures)
        else:
            # Default based on satisfaction
            return 1.0 if result.get("postulate_satisfied", False) else 0.0
