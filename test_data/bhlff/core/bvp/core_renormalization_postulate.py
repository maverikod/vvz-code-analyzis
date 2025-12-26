"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core Renormalization Postulate implementation for BVP framework.

This module implements the core functionality of Postulate 8 of the BVP framework,
which states that the core is a minimum of ω₀-averaged energy where BVP "renormalizes"
core coefficients c_i^eff(|A|,|∇A|) and sets boundary "pressure/stiffness".

Theoretical Background:
    The core represents an energy minimum with renormalized coefficients
    that depend on envelope amplitude and gradient. This renormalization
    is controlled by BVP field dynamics and sets boundary conditions.

Example:
    >>> postulate = CoreRenormalizationPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any

from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate
from .core_region_analyzer import CoreRegionAnalyzer
from .core_renormalization_analyzer import CoreRenormalizationAnalyzer


class CoreRenormalizationPostulate(BVPPostulate):
    """
    Postulate 8: Core - Averaged Minimum.

    Physical Meaning:
        Core is minimum of ω₀-averaged energy: BVP "renormalizes"
        core coefficients c_i^eff(|A|,|∇A|) and sets boundary
        "pressure/stiffness".
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize core renormalization postulate.

        Physical Meaning:
            Sets up the postulate for analyzing core energy minimization
            and coefficient renormalization.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.renormalization_threshold = constants.get_quench_parameter(
            "renormalization_threshold"
        )
        self.core_radius = constants.get_physical_parameter("core_radius")

        # Initialize helper components
        self.region_analyzer = CoreRegionAnalyzer(domain, constants)
        self.renormalization_analyzer = CoreRenormalizationAnalyzer(domain, constants)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply core renormalization postulate.

        Physical Meaning:
            Verifies that the core represents a minimum of
            ω₀-averaged energy with renormalized coefficients
            and proper boundary conditions.

        Mathematical Foundation:
            Analyzes core energy minimization and coefficient
            renormalization c_i^eff(|A|,|∇A|) from BVP envelope.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including renormalized coefficients,
                core energy, and boundary conditions.
        """
        # Identify core region
        core_region = self.region_analyzer.identify_core_region(envelope)

        # Compute renormalized coefficients
        renormalized_coefficients = (
            self.renormalization_analyzer.compute_renormalized_coefficients(
                envelope, core_region
            )
        )

        # Analyze core energy minimization
        energy_analysis = (
            self.renormalization_analyzer.analyze_core_energy_minimization(
                envelope, core_region
            )
        )

        # Compute boundary pressure/stiffness
        boundary_conditions = self.renormalization_analyzer.compute_boundary_conditions(
            envelope, core_region
        )

        # Validate core renormalization
        is_renormalized = self._validate_core_renormalization(
            renormalized_coefficients, energy_analysis
        )

        return {
            "core_region": core_region,
            "renormalized_coefficients": renormalized_coefficients,
            "energy_analysis": energy_analysis,
            "boundary_conditions": boundary_conditions,
            "is_renormalized": is_renormalized,
            "postulate_satisfied": is_renormalized,
        }

    def _validate_core_renormalization(
        self,
        renormalized_coefficients: Dict[str, float],
        energy_analysis: Dict[str, Any],
    ) -> bool:
        """
        Validate core renormalization postulate.

        Physical Meaning:
            Checks that the core exhibits proper renormalization
            of coefficients and energy minimization.

        Args:
            renormalized_coefficients (Dict[str, float]): Renormalized coefficients.
            energy_analysis (Dict[str, Any]): Energy analysis results.

        Returns:
            bool: True if core renormalization is valid.
        """
        # Check that renormalized coefficients are computed
        if not renormalized_coefficients:
            return False

        # Check energy minimization
        energy_minimized = energy_analysis.get("energy_minimized", False)
        if not energy_minimized:
            return False

        # Check renormalization threshold
        renormalization_strength = renormalized_coefficients.get(
            "renormalization_strength", 0.0
        )
        if renormalization_strength < self.renormalization_threshold:
            return False

        return True
