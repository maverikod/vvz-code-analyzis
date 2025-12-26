"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Adaptive integrator package for 7D phase field dynamics.

This package implements the adaptive integrator for solving dynamic phase field
equations in 7D space-time with automatic error control and time step adjustment.
"""

from .adaptive_integrator import AdaptiveIntegrator
from .error_estimation import ErrorEstimation
from .runge_kutta import RungeKuttaMethods

__all__ = ["AdaptiveIntegrator", "ErrorEstimation", "RungeKuttaMethods"]
