"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP constants package for advanced material properties.

This package provides modular components for BVP constants including
basic, advanced, and numerical constants with frequency-dependent calculations.

Physical Meaning:
    Contains material properties and frequency-dependent calculations
    including nonlinear admittance coefficients, renormalized coefficients,
    and frequency-dependent material properties.

Mathematical Foundation:
    Implements advanced field theory calculations:
    - Nonlinear admittance coefficients with quantum corrections
    - Renormalized coefficients with renormalization group flow
    - Frequency-dependent material properties using Drude-Lorentz models

Example:
    >>> from .bvp_constants_advanced import BVPConstantsAdvanced
    >>> constants = BVPConstantsAdvanced()
    >>> coeffs = constants.compute_nonlinear_admittance_coefficients(freq, amp)
"""

from .bvp_constants_advanced import BVPConstantsAdvanced
from .frequency_dependent_properties import FrequencyDependentProperties
from .nonlinear_coefficients import NonlinearCoefficients
from .renormalized_coefficients import RenormalizedCoefficients

__all__ = [
    "BVPConstantsAdvanced",
    "FrequencyDependentProperties",
    "NonlinearCoefficients",
    "RenormalizedCoefficients",
]
