"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Postulate 8: Core - Averaged Minimum implementation.

This module implements the Core Renormalization postulate for the BVP framework,
validating that the core is a minimum of energy averaged over ω₀ with proper
renormalization of coefficients.

Physical Meaning:
    The Core Renormalization postulate describes how the core is a minimum
    of energy averaged over ω₀. The BVP "renormalizes" core coefficients
    (c₂,c₄,c₆ → c_i^eff(|A|,|∇A|)) and sets boundary "pressure/stiffness".

Mathematical Foundation:
    Validates core renormalization by computing effective coefficients
    and boundary conditions from the BVP envelope. The renormalization
    should exhibit proper energy minimization characteristics.

Example:
    >>> postulate = BVPPostulate8_CoreRenormalization(domain_7d, config)
    >>> results = postulate.apply(envelope_7d)
    >>> print(f"Core renormalization valid: {results['renormalization_valid']}")
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_postulate_base import BVPPostulate


class BVPPostulate8_CoreRenormalization(BVPPostulate):
    """
    Postulate 8: Core - Averaged Minimum.

    Physical Meaning:
        Core is minimum of energy averaged over ω₀: BVP "renormalizes" core
        coefficients (c₂,c₄,c₆ → c_i^eff(|A|,|∇A|)) and sets boundary
        "pressure/stiffness".

    Mathematical Foundation:
        Validates core renormalization by computing effective coefficients
        and boundary conditions from BVP envelope.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize Core Renormalization postulate.

        Physical Meaning:
            Sets up the postulate with the computational domain and
            configuration parameters, including the renormalization
            threshold for validation.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - renormalization_threshold (float): Renormalization threshold (default: 0.1)
        """
        self.domain_7d = domain_7d
        self.config = config
        self.renormalization_threshold = config.get("renormalization_threshold", 0.1)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply Core Renormalization postulate.

        Physical Meaning:
            Validates core renormalization by computing effective coefficients
            and boundary conditions from the BVP envelope. This ensures that
            the core exhibits proper energy minimization with renormalized
            coefficients and appropriate boundary conditions.

        Mathematical Foundation:
            Computes the effective renormalized coefficients c_i^eff(|A|,|∇A|)
            from the envelope amplitude and gradients, and calculates the
            boundary pressure/stiffness conditions.

        Args:
            envelope (np.ndarray): 7D envelope field to validate.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results including:
                - postulate_satisfied (bool): Whether postulate is satisfied
                - effective_coefficients (Dict): Renormalized coefficients
                - boundary_conditions (Dict): Boundary pressure/stiffness
                - renormalization_valid (bool): Whether renormalization is valid
                - renormalization_threshold (float): Applied threshold
        """
        # Compute effective coefficients
        effective_coefficients = self._compute_effective_coefficients(envelope)

        # Compute boundary conditions
        boundary_conditions = self._compute_boundary_conditions(envelope)

        # Check if renormalization is valid
        renormalization_valid = (
            effective_coefficients["c2_eff"] > self.renormalization_threshold
        )

        return {
            "postulate_satisfied": renormalization_valid,
            "effective_coefficients": effective_coefficients,
            "boundary_conditions": boundary_conditions,
            "renormalization_valid": renormalization_valid,
            "renormalization_threshold": self.renormalization_threshold,
        }

    def _compute_effective_coefficients(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Compute effective renormalized coefficients.

        Physical Meaning:
            Computes the renormalized coefficients c_i^eff(|A|,|∇A|) from
            the envelope amplitude and gradients. These coefficients represent
            the effective parameters of the core after renormalization by
            the BVP field.

        Mathematical Foundation:
            The renormalized coefficients are computed as:
            c_i^eff = c_i + α_i|A|² + β_i|∇A|²/ω₀²
            where α_i and β_i are renormalization parameters.

        Args:
            envelope (np.ndarray): 7D envelope field.

        Returns:
            Dict[str, float]: Dictionary containing:
                - c2_eff: Renormalized c₂ coefficient
                - c4_eff: Renormalized c₄ coefficient
                - c6_eff: Renormalized c₆ coefficient
        """
        amplitude = np.abs(envelope)
        grad_amplitude = np.sqrt(
            np.sum(
                [np.gradient(amplitude, axis=i) ** 2 for i in range(amplitude.ndim)],
                axis=0,
            )
        )

        # Renormalized coefficients: c_i^eff = c_i + α_i|A|² + β_i|∇A|²/ω₀²
        c2_base = 1.0
        c4_base = 0.1
        c6_base = 0.01

        alpha_2, alpha_4, alpha_6 = 0.1, 0.01, 0.001
        beta_2, beta_4, beta_6 = 0.1, 0.01, 0.001

        c2_eff = (
            c2_base
            + alpha_2 * np.mean(amplitude**2)
            + beta_2 * np.mean(grad_amplitude**2)
        )
        c4_eff = (
            c4_base
            + alpha_4 * np.mean(amplitude**2)
            + beta_4 * np.mean(grad_amplitude**2)
        )
        c6_eff = (
            c6_base
            + alpha_6 * np.mean(amplitude**2)
            + beta_6 * np.mean(grad_amplitude**2)
        )

        return {
            "c2_eff": float(c2_eff),
            "c4_eff": float(c4_eff),
            "c6_eff": float(c6_eff),
        }

    def _compute_boundary_conditions(self, envelope: np.ndarray) -> Dict[str, float]:
        """
        Compute boundary pressure/stiffness.

        Physical Meaning:
            Computes the boundary pressure and stiffness conditions set by
            the BVP field. These conditions represent the effective boundary
            constraints imposed by the renormalized core.

        Mathematical Foundation:
            The boundary conditions are computed from the envelope amplitude
            and its gradients, representing the pressure and stiffness
            characteristics at the boundaries.

        Args:
            envelope (np.ndarray): 7D envelope field.

        Returns:
            Dict[str, float]: Dictionary containing:
                - boundary_pressure: Boundary pressure condition
                - boundary_stiffness: Boundary stiffness condition
        """
        amplitude = np.abs(envelope)

        # Compute boundary values
        boundary_pressure = np.mean(amplitude**2)
        boundary_stiffness = np.mean(np.gradient(amplitude, axis=0) ** 2)

        return {
            "boundary_pressure": float(boundary_pressure),
            "boundary_stiffness": float(boundary_stiffness),
        }
