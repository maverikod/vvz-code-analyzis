"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Physical validator for BVP methods and results.

This module implements comprehensive physical validation for BVP methods,
ensuring that all results are consistent with the theoretical framework
and physical principles of the 7D phase field theory.
"""

from .validation import (
    PhysicalValidator,
    BVPPhysicalValidator,
    PhysicalConstraintsValidator,
    TheoreticalBoundsValidator,
)
