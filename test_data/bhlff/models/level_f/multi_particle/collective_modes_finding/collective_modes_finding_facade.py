"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for collective modes finding.

This module provides the main CollectiveModesFinder facade class that
coordinates all collective modes finding components.
"""

from .collective_modes_finding_base import CollectiveModesFinderBase
from .collective_modes_finding_initialization import CollectiveModesFindingInitializationMixin
from .collective_modes_finding_matrices import CollectiveModesFindingMatricesMixin
from .collective_modes_finding_analysis import CollectiveModesFindingAnalysisMixin
from .collective_modes_finding_interactions import CollectiveModesFindingInteractionsMixin
from .collective_modes_finding_computations import CollectiveModesFindingComputationsMixin
from .collective_modes_finding_step import CollectiveModesFindingStepMixin


class CollectiveModesFinder(
    CollectiveModesFinderBase,
    CollectiveModesFindingInitializationMixin,
    CollectiveModesFindingMatricesMixin,
    CollectiveModesFindingAnalysisMixin,
    CollectiveModesFindingInteractionsMixin,
    CollectiveModesFindingComputationsMixin,
    CollectiveModesFindingStepMixin
):
    """
    Facade class for collective modes finding with all mixins.
    
    Physical Meaning:
        Finds collective modes in multi-particle systems
        through diagonalization of dynamics matrix.
        
    Mathematical Foundation:
        Implements collective modes finding:
        - Mode finding: diagonalization of dynamics matrix E⁻¹K
        - Dynamics matrix: E⁻¹K where E is energy matrix and K is stiffness matrix
    """
    pass

