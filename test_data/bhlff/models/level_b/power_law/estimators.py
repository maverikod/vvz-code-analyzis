"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Block-aware estimators for critical exponents (nu, beta, gamma).

This module provides facade interface for critical exponent estimators
that work on 7D blocks with CUDA acceleration.

Physical Meaning:
    Critical exponents characterize scaling behavior near phase transitions.
    Block-aware estimation preserves local structure and avoids artifacts
    from global flattening in 7D space-time.

Mathematical Foundation:
    - ν: correlation length exponent from ξ ~ |t|^{-ν}
    - β: order parameter exponent from CCDF tail ~ A^{-β}
    - γ: susceptibility exponent from χ ~ |t|^{-γ}
    All estimated using block-aware sampling and robust Theil-Sen regression.
"""

from __future__ import annotations

# Import estimators from specialized modules
from .nu_estimator import estimate_nu_from_correlation_length
from .beta_estimator import estimate_beta_from_tail
from .gamma_estimator import estimate_chi_from_variance

# Re-export for backward compatibility
__all__ = [
    "estimate_nu_from_correlation_length",
    "estimate_beta_from_tail",
    "estimate_chi_from_variance",
]
