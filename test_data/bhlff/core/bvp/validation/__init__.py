"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Validation package for BVP methods and results.

This package implements comprehensive physical validation for BVP methods,
ensuring that all results are consistent with the theoretical framework
and physical principles of the 7D phase field theory.
"""

from .base_validator import PhysicalValidator
from .bvp_validator import BVPPhysicalValidator
from .physical_constraints import PhysicalConstraintsValidator
from .theoretical_bounds import TheoreticalBoundsValidator
