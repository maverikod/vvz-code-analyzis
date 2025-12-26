"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Power law core analysis module for Level B.

This module implements core power law analysis operations for Level B
of the 7D phase field theory, focusing on power law behavior and scaling.

Physical Meaning:
    Analyzes power law characteristics of the BVP field distribution,
    identifying scaling behavior, critical exponents, and correlation
    functions in the 7D space-time.

Mathematical Foundation:
    Implements power law analysis including:
    - Power law exponent computation
    - Scaling region identification
    - Correlation function analysis
    - Critical behavior analysis

Example:
    >>> core = PowerLawCore(bvp_core)
    >>> exponents = core.compute_power_law_exponents(envelope)
"""

from .power_law.power_law_core import PowerLawCore
