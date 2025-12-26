"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for particle validation.

This module provides the main ParticleValidation facade class that
coordinates all particle validation components.
"""

from .particle_validation_base import ParticleValidationBase
from .particle_validation_main import ParticleValidationMainMixin
from .particle_validation_constraints import ParticleValidationConstraintsMixin
from .particle_validation_experimental import ParticleValidationExperimentalMixin
from .particle_validation_aggregation import ParticleValidationAggregationMixin


class ParticleValidation(
    ParticleValidationBase,
    ParticleValidationMainMixin,
    ParticleValidationConstraintsMixin,
    ParticleValidationExperimentalMixin,
    ParticleValidationAggregationMixin
):
    """
    Facade class for particle validation with all mixins.
    
    Physical Meaning:
        Validates the inverted parameters against experimental
        data and theoretical constraints.
    """
    pass

