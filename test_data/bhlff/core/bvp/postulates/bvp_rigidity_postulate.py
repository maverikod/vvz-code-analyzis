"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Postulate 3: BVP Rigidity implementation.

This module implements the BVP Rigidity postulate for the BVP framework,
validating that the BVP field exhibits rigidity with dominant stiffness terms.

Physical Meaning:
    The BVP Rigidity postulate ensures that the BVP energy dominates in
    derivative (stiffness) terms, with large phase velocity c_φ. The carrier
    is weakly sensitive to local perturbations but changes the wave impedance
    of the medium through the envelope.

Mathematical Foundation:
    Validates that the BVP field exhibits rigidity by checking that the
    stiffness terms dominate over other energy contributions. The rigidity
    is quantified by the ratio of stiffness energy to total energy.

Example:
    >>> postulate = BVPPostulate3_BVPRigidity(domain_7d, config)
    >>> results = postulate.apply(envelope_7d)
    >>> print(f"BVP rigidity satisfied: {results['postulate_satisfied']}")
"""

import numpy as np
from typing import Dict, Any

from ...domain.domain_7d import Domain7D
from ..bvp_postulate_base import BVPPostulate


class BVPPostulate3_BVPRigidity(BVPPostulate):
    """
    Postulate 3: BVP Rigidity.

    Physical Meaning:
        BVP energy dominates in derivative (stiffness) terms; phase velocity c_φ
        is large; carrier is weakly sensitive to local perturbations but changes
        wave impedance of medium through envelope.

    Mathematical Foundation:
        Validates that the BVP field exhibits rigidity by checking that
        the stiffness terms dominate over other energy contributions.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize BVP Rigidity postulate.

        Physical Meaning:
            Sets up the postulate with the computational domain and
            configuration parameters, including the minimum required
            rigidity ratio.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - min_rigidity_ratio (float): Minimum required rigidity ratio (default: 0.8)
        """
        self.domain_7d = domain_7d
        self.config = config
        self.min_rigidity_ratio = config.get("min_rigidity_ratio", 0.8)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply BVP Rigidity postulate.

        Physical Meaning:
            Validates BVP rigidity by computing the ratio of stiffness energy
            to total energy and checking that it dominates. This ensures that
            the BVP field exhibits the characteristic rigidity with large
            phase velocity and weak sensitivity to local perturbations.

        Mathematical Foundation:
            Computes field gradients in all 6 spatial and phase dimensions,
            calculates the stiffness energy from these gradients, and
            validates that the stiffness energy dominates the total energy.

        Args:
            envelope (np.ndarray): 7D envelope field to validate.
                Shape: (N_x, N_y, N_z, N_φx, N_φy, N_φz, N_t)

        Returns:
            Dict[str, Any]: Validation results including:
                - postulate_satisfied (bool): Whether postulate is satisfied
                - stiffness_energy (float): Stiffness energy contribution
                - total_energy (float): Total field energy
                - rigidity_ratio (float): Ratio of stiffness to total energy
                - min_required_ratio (float): Minimum required rigidity ratio
        """
        # Compute field gradients
        grad_x = np.gradient(envelope, axis=0)
        grad_y = np.gradient(envelope, axis=1)
        grad_z = np.gradient(envelope, axis=2)

        # Compute phase gradients
        grad_phi_1 = np.gradient(envelope, axis=3)
        grad_phi_2 = np.gradient(envelope, axis=4)
        grad_phi_3 = np.gradient(envelope, axis=5)

        # Compute stiffness energy (derivative terms)
        stiffness_energy = (
            np.sum(np.abs(grad_x) ** 2)
            + np.sum(np.abs(grad_y) ** 2)
            + np.sum(np.abs(grad_z) ** 2)
            + np.sum(np.abs(grad_phi_1) ** 2)
            + np.sum(np.abs(grad_phi_2) ** 2)
            + np.sum(np.abs(grad_phi_3) ** 2)
        )

        # Compute total field energy
        total_energy = np.sum(np.abs(envelope) ** 2)

        # Compute rigidity ratio
        rigidity_ratio = stiffness_energy / (stiffness_energy + total_energy)

        # Check if rigidity is satisfied
        rigidity_satisfied = rigidity_ratio > self.min_rigidity_ratio

        return {
            "postulate_satisfied": rigidity_satisfied,
            "stiffness_energy": float(stiffness_energy),
            "total_energy": float(total_energy),
            "rigidity_ratio": float(rigidity_ratio),
            "min_required_ratio": self.min_rigidity_ratio,
        }
