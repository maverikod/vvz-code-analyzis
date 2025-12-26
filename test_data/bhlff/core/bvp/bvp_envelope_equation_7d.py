"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Legacy BVP envelope equation module - DEPRECATED.

This module is deprecated. Use the new modular structure:
- bhlff.core.bvp.envelope_equation.BVPEnvelopeEquation7D
- Individual modules in bhlff.core.bvp.envelope_equation.*

The envelope equation has been refactored into separate modules following
the 1 class = 1 file principle and size limits.

Physical Meaning:
    This legacy module contained the complete 7D envelope equation implementation
    in a single file, which violated project standards. The implementation has
    been moved to individual modules for better maintainability.

Example:
    # OLD (deprecated):
    # from bhlff.core.bvp.bvp_envelope_equation_7d import BVPEnvelopeEquation7D

    # NEW (recommended):
    from bhlff.core.bvp.envelope_equation import BVPEnvelopeEquation7D
"""

# Import from the new modular structure
from .envelope_equation import BVPEnvelopeEquation7D
from .envelope_equation import DerivativeOperators7D, NonlinearTerms7D

# Re-export for backward compatibility
__all__ = ["BVPEnvelopeEquation7D", "DerivativeOperators7D", "NonlinearTerms7D"]
