"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Runge-Kutta methods module for adaptive integrator.

This module implements embedded Runge-Kutta methods for adaptive integration,
including RK4(5) method with error estimation.

Physical Meaning:
    Uses embedded Runge-Kutta method to compute both fourth-order
    accurate solution and fifth-order error estimate for adaptive control.

Mathematical Foundation:
    Implements embedded RK4(5) method:
    - k1 = dt * f(t, y)
    - k2 = dt * f(t + dt/2, y + k1/2)
    - k3 = dt * f(t + dt/2, y + k2/2)
    - k4 = dt * f(t + dt, y + k3)
    - y4 = y + (k1 + 2*k2 + 2*k3 + k4)/6  (4th order)
    - y5 = y + (7*k1 + 32*k3 + 12*k4 + 32*k5 + 7*k6)/90  (5th order)
    - error = |y5 - y4|
"""

import numpy as np
from typing import Tuple, Callable
import logging


class RungeKuttaMethods:
    """
    Runge-Kutta methods for adaptive integration.

    Physical Meaning:
        Implements embedded Runge-Kutta methods for adaptive integration
        with error estimation and step size control.
    """

    def __init__(self):
        """Initialize Runge-Kutta methods."""
        self.logger = logging.getLogger(__name__)

    def embedded_rk_step(
        self, field: np.ndarray, source: np.ndarray, dt: float, compute_rhs: Callable
    ) -> Tuple[np.ndarray, float]:
        """
        Perform embedded Runge-Kutta step with full error estimation.

        Physical Meaning:
            Uses embedded Runge-Kutta method to compute both fourth-order
            accurate solution and fifth-order error estimate for adaptive control.
            Implements the full Dormand-Prince RK4(5) method with proper
            Butcher tableau coefficients.

        Mathematical Foundation:
            Implements embedded Dormand-Prince RK4(5) method:
            - k1 = dt * f(t, y)
            - k2 = dt * f(t + c2*dt, y + a21*k1)
            - k3 = dt * f(t + c3*dt, y + a31*k1 + a32*k2)
            - k4 = dt * f(t + c4*dt, y + a41*k1 + a42*k2 + a43*k3)
            - k5 = dt * f(t + c5*dt, y + a51*k1 + a52*k2 + a53*k3 + a54*k4)
            - k6 = dt * f(t + c6*dt, y + a61*k1 + a62*k2 + a63*k3 + a64*k4 + a65*k5)
            - k7 = dt * f(t + c7*dt, y + a71*k1 + a72*k2 + a73*k3 + a74*k4 + a75*k5 + a76*k6)
            - y4 = y + b1*k1 + b2*k2 + b3*k3 + b4*k4 + b5*k5 + b6*k6 + b7*k7  (4th order)
            - y5 = y + b1^*k1 + b2^*k2 + b3^*k3 + b4^*k4 + b5^*k5 + b6^*k6 + b7^*k7  (5th order)
            - error = |y5 - y4|
        """
        # Dormand-Prince RK4(5) Butcher tableau coefficients
        c = np.array([0, 1 / 5, 3 / 10, 4 / 5, 8 / 9, 1, 1])

        a = np.array(
            [
                [0, 0, 0, 0, 0, 0, 0],
                [1 / 5, 0, 0, 0, 0, 0, 0],
                [3 / 40, 9 / 40, 0, 0, 0, 0, 0],
                [44 / 45, -56 / 15, 32 / 9, 0, 0, 0, 0],
                [19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729, 0, 0, 0],
                [9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656, 0, 0],
                [35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0],
            ]
        )

        # 4th order coefficients
        b4 = np.array([35 / 384, 0, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84, 0])

        # 5th order coefficients
        b5 = np.array(
            [
                5179 / 57600,
                0,
                7571 / 16695,
                393 / 640,
                -92097 / 339200,
                187 / 2100,
                1 / 40,
            ]
        )

        # Compute k1
        k1 = compute_rhs(field, source)

        # Compute k2
        field_temp = field + dt * (a[1, 0] * k1)
        k2 = compute_rhs(field_temp, source)

        # Compute k3
        field_temp = field + dt * (a[2, 0] * k1 + a[2, 1] * k2)
        k3 = compute_rhs(field_temp, source)

        # Compute k4
        field_temp = field + dt * (a[3, 0] * k1 + a[3, 1] * k2 + a[3, 2] * k3)
        k4 = compute_rhs(field_temp, source)

        # Compute k5
        field_temp = field + dt * (
            a[4, 0] * k1 + a[4, 1] * k2 + a[4, 2] * k3 + a[4, 3] * k4
        )
        k5 = compute_rhs(field_temp, source)

        # Compute k6
        field_temp = field + dt * (
            a[5, 0] * k1 + a[5, 1] * k2 + a[5, 2] * k3 + a[5, 3] * k4 + a[5, 4] * k5
        )
        k6 = compute_rhs(field_temp, source)

        # Compute k7
        field_temp = field + dt * (
            a[6, 0] * k1
            + a[6, 1] * k2
            + a[6, 2] * k3
            + a[6, 3] * k4
            + a[6, 4] * k5
            + a[6, 5] * k6
        )
        k7 = compute_rhs(field_temp, source)

        # Fourth-order solution
        field_4th = field + dt * (
            b4[0] * k1
            + b4[1] * k2
            + b4[2] * k3
            + b4[3] * k4
            + b4[4] * k5
            + b4[5] * k6
            + b4[6] * k7
        )

        # Fifth-order solution
        field_5th = field + dt * (
            b5[0] * k1
            + b5[1] * k2
            + b5[2] * k3
            + b5[3] * k4
            + b5[4] * k5
            + b5[5] * k6
            + b5[6] * k7
        )

        # Compute error estimate using Richardson extrapolation
        error_estimate = self._compute_richardson_error(field_4th, field_5th, dt)

        return field_4th, error_estimate

    def _compute_richardson_error(
        self, field_4th: np.ndarray, field_5th: np.ndarray, dt: float
    ) -> float:
        """
        Compute error estimate using Richardson extrapolation.

        Physical Meaning:
            Uses Richardson extrapolation to provide a more accurate
            error estimate for adaptive step size control.
        """
        # Compute error difference
        error_diff = field_5th - field_4th

        # Compute field magnitude for normalization
        field_magnitude = np.linalg.norm(field_4th)

        if field_magnitude < 1e-15:
            # Avoid division by zero for very small fields
            error_estimate = np.linalg.norm(error_diff)
        else:
            # Richardson extrapolation error estimate
            # For RK4(5), the error scales as h^5, so p = 1
            richardson_factor = 1.0 / (1.0 - (0.5) ** 1)  # h_4th/h_5th = 0.5
            error_estimate = (
                richardson_factor * np.linalg.norm(error_diff) / field_magnitude
            )

        # Apply error bounds
        min_error = 1e-15
        max_error = 1.0

        error_estimate = max(min_error, min(error_estimate, max_error))

        return float(error_estimate)
