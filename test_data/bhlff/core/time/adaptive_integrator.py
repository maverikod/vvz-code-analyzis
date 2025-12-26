"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Adaptive integrator for 7D phase field dynamics.

This module implements the adaptive integrator for solving dynamic phase field
equations in 7D space-time with automatic error control and time step adjustment.

Physical Meaning:
    Adaptive integrator provides automatic time step control to maintain
    accuracy while ensuring numerical stability of phase field evolution
    in 7D space-time with optimal performance.

Mathematical Foundation:
    Uses embedded Runge-Kutta methods with error estimation and automatic
    step size adjustment for optimal performance and accuracy control.
"""

from .adaptive.adaptive_integrator import AdaptiveIntegrator
