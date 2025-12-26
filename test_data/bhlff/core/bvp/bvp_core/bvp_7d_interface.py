"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP 7D interface module.

This module implements the 7D interface for the BVP framework,
providing access to 7D envelope equation solving and postulate validation.

Physical Meaning:
    Provides the interface to 7D space-time operations in the BVP framework,
    including solving the full 7D envelope equation and validating all
    9 BVP postulates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Mathematical Foundation:
    Implements operations for:
    - Solving the 7D envelope equation in full space-time
    - Validating all 9 BVP postulates in 7D
    - Accessing 7D domain and components

Example:
    >>> interface = BVPCore7DInterface(domain_7d, config)
    >>> envelope_7d = interface.solve_envelope_7d(source_7d)
    >>> validation = interface.validate_postulates_7d(envelope_7d)
"""

import numpy as np
from typing import Dict, Any, Optional

from ...domain.domain_7d import Domain7D
from ..bvp_envelope_equation_7d import BVPEnvelopeEquation7D
from ..bvp_postulates_7d import BVPPostulates7D


class BVPCore7DInterface:
    """
    BVP 7D interface for space-time operations.

    Physical Meaning:
        Provides the interface to 7D space-time operations in the BVP framework,
        including solving the full 7D envelope equation and validating all
        9 BVP postulates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Mathematical Foundation:
        Implements operations for working with the full 7D space-time
        structure of the BVP framework, including envelope solving and
        postulate validation.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize BVP 7D interface.

        Physical Meaning:
            Sets up the 7D interface with the 7D computational domain
            and configuration parameters, initializing the 7D envelope
            equation solver and postulates validator.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters.
        """
        self.domain_7d = domain_7d
        self.config = config

        # Initialize 7D components
        self._setup_7d_components()

    def _setup_7d_components(self) -> None:
        """
        Setup 7D components for envelope equation and postulates.

        Physical Meaning:
            Initializes the 7D envelope equation solver and postulates
            validator for working with the full 7D space-time structure.
        """
        # Initialize 7D envelope equation solver
        self._envelope_equation_7d = BVPEnvelopeEquation7D(self.domain_7d, self.config)

        # Initialize 7D postulates validator
        self._postulates_7d = BVPPostulates7D(self.domain_7d, self.config)

    def solve_envelope_7d(self, source_7d: np.ndarray) -> np.ndarray:
        """
        Solve 7D BVP envelope equation.

        Physical Meaning:
            Solves the full 7D envelope equation in space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            using the 7D envelope equation solver. This provides the complete
            solution including spatial, phase, and temporal evolution.

        Mathematical Foundation:
            Solves the 7D envelope equation:
            ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
            in the full 7D space-time M₇.

        Args:
            source_7d (np.ndarray): 7D source term s(x,φ,t).
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            np.ndarray: 7D envelope solution a(x,φ,t).
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Raises:
            RuntimeError: If 7D domain is not available.
        """
        if self._envelope_equation_7d is None:
            raise RuntimeError("7D domain not available for 7D envelope equation")

        return self._envelope_equation_7d.solve_envelope(source_7d)

    def validate_postulates_7d(self, envelope_7d: np.ndarray) -> Dict[str, Any]:
        """
        Validate all 9 BVP postulates for 7D field.

        Physical Meaning:
            Validates all 9 BVP postulates to ensure the 7D field
            satisfies the fundamental properties of the BVP framework.
            This comprehensive validation ensures physical consistency
            and theoretical correctness in 7D space-time.

        Mathematical Foundation:
            Applies all 9 BVP postulates to the 7D envelope field:
            1. Carrier Primacy
            2. Scale Separation
            3. BVP Rigidity
            4. U(1)³ Phase Structure
            5. Quenches
            6. Tail Resonatorness
            7. Transition Zone
            8. Core Renormalization
            9. Power Balance

        Args:
            envelope_7d (np.ndarray): 7D BVP envelope field.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results from all postulates including:
                - postulate_results: Results from each postulate
                - overall_satisfied: Whether all postulates are satisfied
                - satisfaction_count: Number of satisfied postulates
                - total_postulates: Total number of postulates

        Raises:
            RuntimeError: If 7D postulates are not available.
        """
        if self._postulates_7d is None:
            raise RuntimeError("7D postulates not available")

        return self._postulates_7d.validate_all_postulates(envelope_7d)

    def get_7d_domain(self) -> Domain7D:
        """
        Get the 7D domain.

        Physical Meaning:
            Returns the 7D computational domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            for accessing spatial, phase, and temporal configurations.

        Returns:
            Domain7D: The 7D space-time domain.
        """
        return self.domain_7d

    def get_7d_envelope_equation(self) -> BVPEnvelopeEquation7D:
        """
        Get the 7D envelope equation solver.

        Physical Meaning:
            Returns the 7D envelope equation solver for direct access
            to 7D envelope equation operations and parameters.

        Returns:
            BVPEnvelopeEquation7D: The 7D envelope equation solver.
        """
        return self._envelope_equation_7d

    def get_7d_postulates(self) -> BVPPostulates7D:
        """
        Get the 7D postulates validator.

        Physical Meaning:
            Returns the 7D postulates validator for direct access
            to individual postulate validation and analysis.

        Returns:
            BVPPostulates7D: The 7D postulates validator.
        """
        return self._postulates_7d

    def get_7d_parameters(self) -> Dict[str, Any]:
        """
        Get 7D interface parameters.

        Physical Meaning:
            Returns the current parameters of the 7D interface
            including envelope equation and postulates parameters.

        Returns:
            Dict[str, Any]: Dictionary containing all 7D parameters.
        """
        params = {}

        if self._envelope_equation_7d is not None:
            params["envelope_equation"] = self._envelope_equation_7d.get_parameters()

        if self._postulates_7d is not None:
            params["postulates"] = {
                "total_postulates": len(self._postulates_7d.postulates),
                "domain_7d": str(self.domain_7d),
            }

        return params
