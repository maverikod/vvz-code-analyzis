"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for phase envelope balance solver.

This module provides the main PhaseEnvelopeBalanceSolver facade class that
coordinates all phase envelope balance solver components.
"""

from .gravity_einstein_base import PhaseEnvelopeBalanceSolverBase
from .gravity_einstein_operators import PhaseEnvelopeBalanceSolverOperatorsMixin
from .gravity_einstein_solve import PhaseEnvelopeBalanceSolverSolveMixin
from .gravity_einstein_cosmology import PhaseEnvelopeBalanceSolverCosmologyMixin
from .gravity_einstein_helpers import PhaseEnvelopeBalanceSolverHelpersMixin


class PhaseEnvelopeBalanceSolver(
    PhaseEnvelopeBalanceSolverBase,
    PhaseEnvelopeBalanceSolverOperatorsMixin,
    PhaseEnvelopeBalanceSolverSolveMixin,
    PhaseEnvelopeBalanceSolverCosmologyMixin,
    PhaseEnvelopeBalanceSolverHelpersMixin
):
    """
    Facade class for phase envelope balance solver with all mixins.
    
    Physical Meaning:
        Solves the phase envelope balance equation D[Θ] = source where
        the balance operator D includes time memory (Γ,K) and spatial
        (−Δ)^β terms with c_φ(a,k), χ/κ bridge.
    """
    pass

