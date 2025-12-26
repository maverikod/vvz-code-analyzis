"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Nonlinear terms for 7D BVP envelope equation.

This module implements the nonlinear stiffness and susceptibility terms
for the 7D BVP envelope equation, including amplitude-dependent
coefficients and quench effects.

Physical Meaning:
    The nonlinear terms represent the amplitude-dependent response of
    the medium to the BVP field, including nonlinear stiffness κ(|a|)
    and effective susceptibility χ(|a|) with quench effects.

Mathematical Foundation:
    Implements:
    - Nonlinear stiffness: κ(|a|) = κ₀ + κ₂|a|²
    - Effective susceptibility: χ(|a|) = χ' + iχ''(|a|)
    - Quench effects through amplitude-dependent terms

Example:
    >>> nonlinear = NonlinearTerms7D(config)
    >>> nonlinear.setup_terms()
    >>> kappa = nonlinear.compute_stiffness(amplitude)
    >>> chi = nonlinear.compute_susceptibility(amplitude)
"""

import numpy as np
from typing import Dict, Any, Callable

from ...domain.domain_7d import Domain7D


class NonlinearTerms7D:
    """
    7D nonlinear terms for BVP envelope equation.

    Physical Meaning:
        Implements the nonlinear stiffness and susceptibility terms
        that depend on the field amplitude, representing the nonlinear
        response of the medium to the BVP field.

    Mathematical Foundation:
        Provides amplitude-dependent functions for:
        - Nonlinear stiffness: κ(|a|) = κ₀ + κ₂|a|²
        - Effective susceptibility: χ(|a|) = χ' + iχ''(|a|)
        - Quench effects through amplitude-dependent terms
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize nonlinear terms.

        Physical Meaning:
            Sets up the nonlinear terms with the computational domain
            and configuration parameters, including the nonlinear
            coefficients and quench parameters.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters including:
                - kappa_0 (float): Linear stiffness coefficient
                - kappa_2 (float): Nonlinear stiffness coefficient
                - chi_prime (float): Real part of susceptibility
                - chi_double_prime_0 (float): Imaginary part coefficient
                - k0 (float): Wave number
        """
        self.domain_7d = domain_7d
        self.config = config

        # Extract parameters
        self.kappa_0 = config.get("kappa_0", 1.0)
        self.kappa_2 = config.get("kappa_2", 0.1)
        self.chi_prime = config.get("chi_prime", 1.0)
        self.chi_double_prime_0 = config.get("chi_double_prime_0", 0.1)
        self.k0 = config.get("k0", 1.0)

        # Initialize functions
        self.kappa_func = None
        self.chi_func = None

    def setup_terms(self) -> None:
        """
        Setup nonlinear stiffness and susceptibility terms.

        Physical Meaning:
            Initializes the nonlinear functions for stiffness and
            susceptibility based on the configuration parameters.
            These functions will be used to compute amplitude-dependent
            coefficients in the envelope equation.
        """
        # Nonlinear stiffness function: κ(|a|) = κ₀ + κ₂|a|²
        self.kappa_func = lambda amplitude: self.kappa_0 + self.kappa_2 * amplitude**2

        # Nonlinear susceptibility function: χ(|a|) = χ' + iχ''(|a|)
        self.chi_func = lambda amplitude: (
            self.chi_prime + 1j * self.chi_double_prime_0 * amplitude**2
        )

    def compute_stiffness(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear stiffness κ(|a|).

        Physical Meaning:
            Computes the amplitude-dependent stiffness coefficient
            κ(|a|) = κ₀ + κ₂|a|², representing the nonlinear response
            of the medium to the field amplitude.

        Mathematical Foundation:
            The nonlinear stiffness increases with field amplitude,
            representing the hardening of the medium under strong
            field excitation.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Nonlinear stiffness κ(|a|).
        """
        if self.kappa_func is None:
            self.setup_terms()

        return self.kappa_func(amplitude)

    def compute_susceptibility(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute effective susceptibility χ(|a|).

        Physical Meaning:
            Computes the amplitude-dependent susceptibility
            χ(|a|) = χ' + iχ''(|a|), representing the complex
            response of the medium including quench effects.

        Mathematical Foundation:
            The susceptibility has both real and imaginary parts,
            with the imaginary part representing losses and
            quench effects that depend on the field amplitude.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Complex susceptibility χ(|a|).
        """
        if self.chi_func is None:
            self.setup_terms()

        return self.chi_func(amplitude)

    def compute_stiffness_derivative(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute derivative of stiffness with respect to amplitude.

        Physical Meaning:
            Computes dκ/d|a| = 2κ₂|a|, needed for the Jacobian
            matrix in Newton-Raphson iterations.

        Mathematical Foundation:
            The derivative is used in the linearization of the
            nonlinear terms for iterative solution methods.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Derivative dκ/d|a|.
        """
        return 2 * self.kappa_2 * amplitude

    def compute_susceptibility_derivative(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute derivative of susceptibility with respect to amplitude.

        Physical Meaning:
            Computes dχ/d|a| = 2iχ''₀|a|, needed for the Jacobian
            matrix in Newton-Raphson iterations.

        Mathematical Foundation:
            The derivative is used in the linearization of the
            nonlinear terms for iterative solution methods.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Complex derivative dχ/d|a|.
        """
        return 2j * self.chi_double_prime_0 * amplitude

    def get_parameters(self) -> Dict[str, float]:
        """
        Get nonlinear term parameters.

        Physical Meaning:
            Returns the current values of all nonlinear parameters
            for monitoring and analysis purposes.

        Returns:
            Dict[str, float]: Dictionary containing all parameters.
        """
        return {
            "kappa_0": self.kappa_0,
            "kappa_2": self.kappa_2,
            "chi_prime": self.chi_prime,
            "chi_double_prime_0": self.chi_double_prime_0,
            "k0": self.k0,
        }

    def update_parameters(self, new_params: Dict[str, float]) -> None:
        """
        Update nonlinear term parameters.

        Physical Meaning:
            Updates the nonlinear parameters and reinitializes
            the nonlinear functions with the new values.

        Args:
            new_params (Dict[str, float]): New parameter values.
        """
        for key, value in new_params.items():
            if hasattr(self, key):
                setattr(self, key, value)

        # Reinitialize functions with new parameters
        self.setup_terms()
