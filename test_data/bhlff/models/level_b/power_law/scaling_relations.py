"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Scaling relations calculator for critical exponents.

This module implements scaling relations for deriving critical exponents
from computed values, including 7D-specific scaling relations.

Physical Meaning:
    Computes derived critical exponents using scaling relations from
    critical phenomena theory, adapted for 7D phase field theory.

Mathematical Foundation:
    Implements scaling relations:
    - δ = (γ + β) / β: critical isotherm exponent
    - α = 2 - ν*d: specific heat exponent (d=7 for 7D)
    - d_eff = 2 - α - β: effective scaling dimension
"""

from typing import Dict
import numpy as np


class ScalingRelations:
    """
    Scaling relations calculator for critical exponents.

    Physical Meaning:
        Computes derived critical exponents using scaling relations
        from critical phenomena theory, adapted for 7D phase field theory.
    """

    @staticmethod
    def compute_critical_isotherm_exponent(beta: float, gamma: float) -> float:
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
            beta (float): Order parameter exponent β.
            gamma (float): Susceptibility exponent γ.

        Returns:
            float: Critical isotherm exponent δ.

        Raises:
            ValueError: If β ≤ 0 or computed δ is not finite.
        """
        # Validate β > 0 (no fixed fallback)
        if beta <= 0:
            raise ValueError(
                f"Cannot compute δ: β = {beta} ≤ 0. "
                f"Order parameter exponent must be positive."
            )

        delta = (gamma + beta) / beta

        # Validate result (no fixed fallback)
        if not np.isfinite(delta):
            raise ValueError(f"computed δ is not finite: {delta} (γ={gamma}, β={beta})")

        return float(delta)

    @staticmethod
    def compute_specific_heat_exponent(nu: float, d: int = 7) -> float:
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
            nu (float): Correlation length exponent ν.
            d (int): Space-time dimension (default: 7 for 7D).

        Returns:
            float: Specific heat exponent α.

        Raises:
            ValueError: If computed α is not finite.
        """
        alpha = 2 - nu * d

        # Validate result (no fixed fallback)
        if not np.isfinite(alpha):
            raise ValueError(f"computed α is not finite: {alpha} (ν={nu}, d={d})")

        return float(alpha)

    @staticmethod
    def compute_7d_scaling_dimension(alpha: float, beta: float) -> float:
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
            alpha (float): Specific heat exponent α.
            beta (float): Order parameter exponent β.

        Returns:
            float: Effective 7D scaling dimension.

        Raises:
            ValueError: If computed d_eff is not finite.
        """
        d_eff = 2 - alpha - beta

        # Validate result (no fixed bounds, but check finiteness)
        if not np.isfinite(d_eff):
            raise ValueError(
                f"computed d_eff is not finite: {d_eff} (α={alpha}, β={beta})"
            )

        return float(d_eff)

