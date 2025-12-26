"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D BVP Parameters implementation with nonlinear coefficients.

This module implements the 7D BVP parameters according to the theory,
including nonlinear stiffness and susceptibility coefficients.

Physical Meaning:
    Implements the 7D BVP parameters for the envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where κ(|a|) and χ(|a|) are nonlinear functions of field amplitude.

Mathematical Foundation:
    - κ(|a|) = κ₀ + κ₂|a|² (nonlinear stiffness)
    - χ(|a|) = χ' + iχ''(|a|) (effective susceptibility with quenches)
    - k₀: wave number
    - μ, β, λ: fractional Laplacian parameters

Example:
    >>> params = Parameters7DBVP(kappa_0=1.0, kappa_2=0.1, chi_prime=1.0, k0=1.0)
    >>> stiffness = params.compute_stiffness(field_amplitude)
    >>> susceptibility = params.compute_susceptibility(field_amplitude)
"""

import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging


@dataclass
class Parameters7DBVP:
    """
    7D BVP Parameters for envelope equation.

    Physical Meaning:
        Contains all parameters for the 7D BVP envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
        including nonlinear stiffness and susceptibility coefficients.

    Mathematical Foundation:
        - κ(|a|) = κ₀ + κ₂|a|² (nonlinear stiffness)
        - χ(|a|) = χ' + iχ''(|a|) (effective susceptibility with quenches)
        - k₀: wave number for temporal evolution
        - μ, β, λ: fractional Laplacian parameters for L_β = μ(-Δ)^β + λ

    Attributes:
        # Nonlinear stiffness parameters
        kappa_0 (float): Linear stiffness coefficient κ₀.
        kappa_2 (float): Nonlinear stiffness coefficient κ₂.

        # Susceptibility parameters
        chi_prime (float): Real part of susceptibility χ'.
        chi_double_prime_0 (float): Base imaginary part of susceptibility χ''₀.
        chi_double_prime_2 (float): Nonlinear imaginary part coefficient χ''₂.

        # Wave number
        k0 (float): Wave number k₀.

        # Fractional Laplacian parameters
        mu (float): Diffusion coefficient μ > 0.
        beta (float): Fractional order β ∈ (0,2).
        lambda_param (float): Damping parameter λ ≥ 0.
        nu (float): Temporal diffusion coefficient ν.

        # Numerical parameters
        precision (str): Numerical precision ('float64' or 'float32').
        max_iterations (int): Maximum Newton-Raphson iterations.
        tolerance (float): Convergence tolerance.
        damping_factor (float): Damping factor for Newton-Raphson.
    """

    # Nonlinear stiffness parameters
    kappa_0: float = 1.0
    kappa_2: float = 0.1

    # Susceptibility parameters
    chi_prime: float = 1.0
    chi_double_prime_0: float = 0.1
    chi_double_prime_2: float = 0.01

    # Wave number
    k0: float = 1.0

    # Fractional Laplacian parameters
    mu: float = 1.0
    beta: float = 1.0
    lambda_param: float = 0.0
    nu: float = 1.0

    # Numerical parameters
    precision: str = "float64"
    max_iterations: int = 100
    tolerance: float = 1e-8
    damping_factor: float = 0.5
    use_cuda: bool = True  # Use CUDA acceleration if available

    def __post_init__(self):
        """Initialize and validate parameters."""
        self.logger = logging.getLogger(__name__)
        self._validate_parameters()
        self.logger.info(
            f"Parameters7DBVP initialized with kappa_0={self.kappa_0}, chi_prime={self.chi_prime}"
        )

    def _validate_parameters(self) -> None:
        """Validate parameter values."""
        if self.kappa_0 <= 0:
            raise ValueError(f"kappa_0 must be positive, got {self.kappa_0}")
        if self.kappa_2 < 0:
            raise ValueError(f"kappa_2 must be non-negative, got {self.kappa_2}")
        if self.chi_prime <= 0:
            raise ValueError(f"chi_prime must be positive, got {self.chi_prime}")
        if self.chi_double_prime_0 < 0:
            raise ValueError(
                f"chi_double_prime_0 must be non-negative, got {self.chi_double_prime_0}"
            )
        if self.chi_double_prime_2 < 0:
            raise ValueError(
                f"chi_double_prime_2 must be non-negative, got {self.chi_double_prime_2}"
            )
        if self.k0 <= 0:
            raise ValueError(f"k0 must be positive, got {self.k0}")
        if self.mu <= 0:
            raise ValueError(f"mu must be positive, got {self.mu}")
        if not 0 < self.beta < 2:
            raise ValueError(f"beta must be in (0,2), got {self.beta}")
        if self.lambda_param < 0:
            raise ValueError(
                f"lambda_param must be non-negative, got {self.lambda_param}"
            )
        if self.nu <= 0:
            raise ValueError(f"nu must be positive, got {self.nu}")
        if self.precision not in ["float32", "float64"]:
            raise ValueError(
                f"precision must be 'float32' or 'float64', got {self.precision}"
            )
        if self.max_iterations <= 0:
            raise ValueError(
                f"max_iterations must be positive, got {self.max_iterations}"
            )
        if self.tolerance <= 0:
            raise ValueError(f"tolerance must be positive, got {self.tolerance}")
        if not 0 < self.damping_factor <= 1:
            raise ValueError(
                f"damping_factor must be in (0,1], got {self.damping_factor}"
            )

    def compute_stiffness(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|².

        Physical Meaning:
            Computes the nonlinear stiffness coefficient that depends
            on the field amplitude, representing the local "rigidity"
            of the phase field.

        Mathematical Foundation:
            κ(|a|) = κ₀ + κ₂|a|²
            where κ₀ is the linear stiffness and κ₂|a|² is the nonlinear contribution.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Nonlinear stiffness κ(|a|).
        """
        return self.kappa_0 + self.kappa_2 * amplitude**2

    def compute_susceptibility(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute nonlinear susceptibility χ(|a|) = χ' + iχ''(|a|).

        Physical Meaning:
            Computes the complex susceptibility that depends on field amplitude,
            representing the local response of the phase field to external
            excitations, including quench effects.

        Mathematical Foundation:
            χ(|a|) = χ' + iχ''(|a|)
            where χ' is the real part and χ''(|a|) = χ''₀ + χ''₂|a|² is the imaginary part.

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Complex susceptibility χ(|a|).
        """
        chi_double_prime = (
            self.chi_double_prime_0 + self.chi_double_prime_2 * amplitude**2
        )
        return self.chi_prime + 1j * chi_double_prime

    def compute_stiffness_derivative(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute derivative of stiffness with respect to amplitude.

        Physical Meaning:
            Computes dκ/d|a| = 2κ₂|a| for Newton-Raphson iterations.

        Mathematical Foundation:
            dκ/d|a| = 2κ₂|a|

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Stiffness derivative dκ/d|a|.
        """
        return 2 * self.kappa_2 * amplitude

    def compute_susceptibility_derivative(self, amplitude: np.ndarray) -> np.ndarray:
        """
        Compute derivative of susceptibility with respect to amplitude.

        Physical Meaning:
            Computes dχ/d|a| = i2χ''₂|a| for Newton-Raphson iterations.

        Mathematical Foundation:
            dχ/d|a| = i2χ''₂|a|

        Args:
            amplitude (np.ndarray): Field amplitude |a|.

        Returns:
            np.ndarray: Susceptibility derivative dχ/d|a|.
        """
        return 1j * 2 * self.chi_double_prime_2 * amplitude

    def get_fractional_laplacian_coefficients(self) -> Dict[str, float]:
        """
        Get coefficients for fractional Laplacian L_β = μ(-Δ)^β + λ.

        Physical Meaning:
            Returns the coefficients for the fractional Laplacian operator
            used in the linearized version of the BVP equation.

        Returns:
            Dict[str, float]: Fractional Laplacian coefficients.
        """
        return {
            "mu": self.mu,
            "beta": self.beta,
            "lambda_param": self.lambda_param,
            "nu": self.nu,
        }

    def get_numerical_parameters(self) -> Dict[str, Any]:
        """
        Get numerical parameters for solvers.

        Returns:
            Dict[str, Any]: Numerical parameters.
        """
        return {
            "precision": self.precision,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
            "damping_factor": self.damping_factor,
        }

    def get_physical_parameters(self) -> Dict[str, float]:
        """
        Get physical parameters for the BVP equation.

        Returns:
            Dict[str, float]: Physical parameters.
        """
        return {
            "kappa_0": self.kappa_0,
            "kappa_2": self.kappa_2,
            "chi_prime": self.chi_prime,
            "chi_double_prime_0": self.chi_double_prime_0,
            "chi_double_prime_2": self.chi_double_prime_2,
            "k0": self.k0,
        }

    def __repr__(self) -> str:
        """String representation of parameters."""
        return (
            f"Parameters7DBVP("
            f"κ₀={self.kappa_0}, κ₂={self.kappa_2}, "
            f"χ'={self.chi_prime}, χ''₀={self.chi_double_prime_0}, "
            f"k₀={self.k0}, μ={self.mu}, β={self.beta})"
        )
