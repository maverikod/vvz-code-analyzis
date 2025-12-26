"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Particle inversion and validation for 7D phase field theory.

This module provides a unified interface for particle parameter
inversion and validation using the 7D BVP framework.

Theoretical Background:
    The particle inversion and validation module implements the
    reconstruction of fundamental model parameters from observable
    properties of elementary particles and their validation against
    experimental data.

Example:
    >>> inversion = ParticleInversion(observables, priors)
    >>> results = inversion.invert_parameters()
    >>> validation = ParticleValidation(results, criteria)
    >>> validation_results = validation.validate_parameters()
"""

from .particle_inversion import ParticleInversion
from .particle_validation import ParticleValidation

__all__ = ["ParticleInversion", "ParticleValidation"]
