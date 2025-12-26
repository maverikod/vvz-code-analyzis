"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

U(1)³ Phase Structure Postulate package for BVP framework.

This package implements Postulate 4 of the BVP framework, which states that
BVP has U(1)³ phase structure with phase vector Θ_a (a=1..3) and
phase coherence is maintained across the field.

Theoretical Background:
    The U(1)³ phase structure represents three independent phase degrees
    of freedom in the BVP field. Phase coherence ensures that phase
    relationships are maintained across spatial and temporal scales.

Example:
    >>> from bhlff.core.bvp.u1_phase_structure import U1PhaseStructurePostulate
    >>> postulate = U1PhaseStructurePostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

from .u1_phase_structure_postulate import U1PhaseStructurePostulate
from .phase_analysis import PhaseAnalysis
from .coherence_analysis import CoherenceAnalysis

__all__ = ["U1PhaseStructurePostulate", "PhaseAnalysis", "CoherenceAnalysis"]
