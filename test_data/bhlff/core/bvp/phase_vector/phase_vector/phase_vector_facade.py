"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for phase vector.

This module provides the main PhaseVector facade class that
coordinates all phase vector components.
"""

from .phase_vector_base import PhaseVectorBase
from .phase_vector_components import PhaseVectorComponentsMixin
from .phase_vector_electroweak import PhaseVectorElectroweakMixin
from .phase_vector_topology import PhaseVectorTopologyMixin
from .phase_vector_cuda import PhaseVectorCUDAMixin
from .phase_vector_memory import PhaseVectorMemoryMixin


class PhaseVector(
    PhaseVectorBase,
    PhaseVectorComponentsMixin,
    PhaseVectorElectroweakMixin,
    PhaseVectorTopologyMixin,
    PhaseVectorCUDAMixin,
    PhaseVectorMemoryMixin
):
    """
    Facade class for U(1)³ phase vector structure with all mixins.
    
    Physical Meaning:
        Implements the three-component phase vector Θ_a (a=1..3)
        that represents the fundamental phase structure of the BVP field.
        Each component corresponds to a different U(1) symmetry group.
        
    Mathematical Foundation:
        The phase vector Θ = (Θ₁, Θ₂, Θ₃) represents three independent
        U(1) phase degrees of freedom with weak hierarchical coupling
        to SU(2)/core through invariant mixed terms.
    """
    pass

