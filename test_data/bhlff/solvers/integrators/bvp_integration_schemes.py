"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP integration schemes for BVP-modulated integrator.

This module provides integration schemes for the BVP-modulated time integrator
in the 7D phase field theory.

Physical Meaning:
    BVP integration schemes implement different temporal integration methods
    for the BVP-modulated evolution equation with various stability and
    accuracy properties.

Mathematical Foundation:
    Implements various time integration schemes for:
    ∂a/∂t = F_BVP(a, t) + modulation_terms

Example:
    >>> schemes = BVPIntegrationSchemes(domain, config)
    >>> field_next = schemes.rk4_step(field_current, dt)
"""

import numpy as np
from typing import Dict, Any

from ...core.domain import Domain


class BVPIntegrationSchemes:
    """
    BVP integration schemes for BVP-modulated integrator.

    Physical Meaning:
        Implements various time integration schemes for the BVP-modulated
        evolution equation with different stability and accuracy properties.

    Mathematical Foundation:
        Implements time integration schemes for:
        ∂a/∂t = F_BVP(a, t) + modulation_terms

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): BVP integrator configuration.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any]) -> None:
        """
        Initialize BVP integration schemes.

        Physical Meaning:
            Sets up the BVP integration schemes with domain and configuration
            for temporal integration.

        Args:
            domain (Domain): Computational domain for the schemes.
            config (Dict[str, Any]): BVP integrator configuration.
        """
        self.domain = domain
        self.config = config

    def rk4_step(self, field: np.ndarray, dt: float, evolution_func) -> np.ndarray:
        """
        Fourth-order Runge-Kutta step.

        Physical Meaning:
            Implements fourth-order Runge-Kutta time integration for
            BVP-modulated evolution with high accuracy.

        Mathematical Foundation:
            RK4 scheme:
            k1 = dt * F(a, t)
            k2 = dt * F(a + k1/2, t + dt/2)
            k3 = dt * F(a + k2/2, t + dt/2)
            k4 = dt * F(a + k3, t + dt)
            a_new = a + (k1 + 2*k2 + 2*k3 + k4) / 6

        Args:
            field (np.ndarray): Current field configuration.
            dt (float): Time step size.
            evolution_func: Function computing evolution terms.

        Returns:
            np.ndarray: Field at next time step.
        """
        # RK4 stages
        k1 = dt * evolution_func(field)
        k2 = dt * evolution_func(field + 0.5 * k1)
        k3 = dt * evolution_func(field + 0.5 * k2)
        k4 = dt * evolution_func(field + k3)

        # RK4 update
        field_new = field + (k1 + 2 * k2 + 2 * k3 + k4) / 6.0

        return field_new

    def euler_step(self, field: np.ndarray, dt: float, evolution_func) -> np.ndarray:
        """
        Forward Euler step.

        Physical Meaning:
            Implements forward Euler time integration for BVP-modulated
            evolution with first-order accuracy.

        Mathematical Foundation:
            Euler scheme:
            a_new = a + dt * F(a, t)

        Args:
            field (np.ndarray): Current field configuration.
            dt (float): Time step size.
            evolution_func: Function computing evolution terms.

        Returns:
            np.ndarray: Field at next time step.
        """
        # Forward Euler update
        field_new = field + dt * evolution_func(field)

        return field_new

    def crank_nicolson_step(
        self, field: np.ndarray, dt: float, evolution_func
    ) -> np.ndarray:
        """
        Crank-Nicolson step.

        Physical Meaning:
            Implements Crank-Nicolson time integration for BVP-modulated
            evolution with second-order accuracy and improved stability.

        Mathematical Foundation:
            Crank-Nicolson scheme:
            a_new = a + dt/2 * (F(a, t) + F(a_new, t + dt))

        Args:
            field (np.ndarray): Current field configuration.
            dt (float): Time step size.
            evolution_func: Function computing evolution terms.

        Returns:
            np.ndarray: Field at next time step.
        """
        # Predictor step (Euler)
        field_predictor = field + dt * evolution_func(field)

        # Corrector step (Crank-Nicolson)
        evolution_current = evolution_func(field)
        evolution_predictor = evolution_func(field_predictor)

        field_new = field + 0.5 * dt * (evolution_current + evolution_predictor)

        return field_new

    def adaptive_step(
        self, field: np.ndarray, dt: float, evolution_func, tolerance: float = 1e-6
    ) -> tuple:
        """
        Adaptive time step with error estimation.

        Physical Meaning:
            Implements adaptive time stepping for BVP-modulated evolution
            with automatic error control and step size adjustment.

        Mathematical Foundation:
            Uses embedded Runge-Kutta methods to estimate local truncation
            error and adjust step size accordingly.

        Args:
            field (np.ndarray): Current field configuration.
            dt (float): Initial time step size.
            evolution_func: Function computing evolution terms.
            tolerance (float): Error tolerance for adaptive stepping.

        Returns:
            tuple: (field_new, dt_new, error_estimate)
        """
        # Take full step
        field_full = self.rk4_step(field, dt, evolution_func)

        # Take two half steps
        field_half1 = self.rk4_step(field, dt / 2, evolution_func)
        field_half2 = self.rk4_step(field_half1, dt / 2, evolution_func)

        # Estimate error
        error_estimate = np.max(np.abs(field_full - field_half2))

        # Adjust step size based on error
        if error_estimate > tolerance:
            # Reduce step size
            dt_new = dt * (tolerance / error_estimate) ** 0.2
            dt_new = max(dt_new, dt * 0.1)  # Minimum reduction factor
        else:
            # Increase step size
            dt_new = dt * (tolerance / error_estimate) ** 0.2
            dt_new = min(dt_new, dt * 2.0)  # Maximum increase factor

        # Use higher accuracy result (two half steps)
        return field_half2, dt_new, error_estimate

    def get_scheme_info(self, scheme_name: str) -> Dict[str, Any]:
        """
        Get information about integration scheme.

        Physical Meaning:
            Returns information about the specified integration scheme
            including order of accuracy and stability properties.

        Args:
            scheme_name (str): Name of the integration scheme.

        Returns:
            Dict[str, Any]: Scheme information.
        """
        scheme_info = {
            "rk4": {
                "order": 4,
                "stability": "explicit",
                "accuracy": "high",
                "computational_cost": "high",
            },
            "euler": {
                "order": 1,
                "stability": "explicit",
                "accuracy": "low",
                "computational_cost": "low",
            },
            "crank_nicolson": {
                "order": 2,
                "stability": "implicit",
                "accuracy": "medium",
                "computational_cost": "medium",
            },
            "adaptive": {
                "order": "variable",
                "stability": "adaptive",
                "accuracy": "high",
                "computational_cost": "variable",
            },
        }

        return scheme_info.get(scheme_name, {})
