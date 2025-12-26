"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Parameters class for BHLFF physics parameters.

This module implements parameter management for 7D phase field theory
simulations, including validation, default values, and parameter
combinations for different physical regimes.

Physical Meaning:
    Parameters control the physical behavior of the phase field system,
    including diffusion rates, fractional order, damping, and boundary
    conditions that determine the evolution of phase field configurations.

Mathematical Foundation:
    Parameters define the coefficients in the fractional Riesz operator
    L_β a = μ(-Δ)^β a + λa and related equations governing phase field
    dynamics in 7D space-time.
"""

from typing import Dict, Any
from dataclasses import dataclass
import numpy as np


@dataclass
class Parameters:
    """
    Physics parameters for 7D phase field theory.

    Physical Meaning:
        Encapsulates all physical parameters that control the behavior
        of the phase field system, including diffusion, fractional order,
        damping, and boundary conditions.

    Mathematical Foundation:
        Parameters define the coefficients in the fractional Riesz operator
        and related equations governing phase field dynamics.

    Attributes:
        mu (float): Diffusion coefficient μ > 0.
        beta (float): Fractional order β ∈ (0,2).
        lambda_param (float): Damping parameter λ ≥ 0.
        nu (float): Time evolution coefficient ν > 0.
        precision (str): Numerical precision ('float64').
        fft_plan (str): FFT planning strategy.
        tolerance (float): Convergence tolerance.
    """

    mu: float
    beta: float
    lambda_param: float = 0.0
    nu: float = 1.0
    precision: str = "float64"
    fft_plan: str = "MEASURE"
    tolerance: float = 1e-12

    def __post_init__(self) -> None:
        """
        Validate parameters after object creation.

        Physical Meaning:
            Ensures all parameters are within physically meaningful ranges
            and compatible with the mathematical framework.

        Raises:
            ValueError: If parameters are outside valid ranges.
        """
        self._validate_parameters()

    def _validate_parameters(self) -> None:
        """
        Validate all parameters for physical consistency.

        Physical Meaning:
            Checks that parameters satisfy the constraints required for
            well-posedness of the fractional Riesz equation and numerical
            stability of the solution.

        Raises:
            ValueError: If any parameter is invalid.
        """
        if self.mu <= 0:
            raise ValueError("Diffusion coefficient mu must be positive")

        if not (0 < self.beta < 2):
            raise ValueError("Fractional order beta must be in (0,2)")

        if self.lambda_param < 0:
            raise ValueError("Damping parameter lambda must be non-negative")

        if self.nu <= 0:
            raise ValueError("Time evolution coefficient nu must be positive")

        if self.precision not in ["float32", "float64"]:
            raise ValueError("Precision must be 'float32' or 'float64'")

        if self.fft_plan not in [
            "ESTIMATE",
            "MEASURE",
            "PATIENT",
            "EXHAUSTIVE",
        ]:
            raise ValueError("Invalid FFT plan strategy")

        if self.tolerance <= 0:
            raise ValueError("Tolerance must be positive")

    def get_spectral_coefficients(self, k_magnitude: np.ndarray) -> np.ndarray:
        """
        Compute spectral coefficients for the fractional operator.

        Physical Meaning:
            Computes the spectral representation D(k) = μ|k|^(2β) + λ
            of the fractional Riesz operator for FFT-based solution.

        Mathematical Foundation:
            The spectral coefficients are D(k) = μ|k|^(2β) + λ where
            |k| is the magnitude of the wave vector.

        Args:
            k_magnitude (np.ndarray): Magnitude of wave vectors |k|.

        Returns:
            np.ndarray: Spectral coefficients D(k).
        """
        return self.mu * (k_magnitude ** (2 * self.beta)) + self.lambda_param

    def get_time_coefficients(self, k_magnitude: np.ndarray) -> np.ndarray:
        """
        Compute time evolution coefficients.

        Physical Meaning:
            Computes the coefficients α_k = ν|k|^(2β) + λ for time
            evolution in the spectral domain.

        Mathematical Foundation:
            Time evolution coefficients are α_k = ν|k|^(2β) + λ for
            the equation ∂_t â + α_k â = ŝ.

        Args:
            k_magnitude (np.ndarray): Magnitude of wave vectors |k|.

        Returns:
            np.ndarray: Time evolution coefficients α_k.
        """
        return self.nu * (k_magnitude ** (2 * self.beta)) + self.lambda_param

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert parameters to dictionary.

        Physical Meaning:
            Provides a dictionary representation of parameters for
            serialization and configuration management.

        Returns:
            Dict[str, Any]: Dictionary of parameters.
        """
        return {
            "mu": self.mu,
            "beta": self.beta,
            "lambda": self.lambda_param,
            "nu": self.nu,
            "precision": self.precision,
            "fft_plan": self.fft_plan,
            "tolerance": self.tolerance,
        }

    @classmethod
    def from_dict(cls, params: Dict[str, Any]) -> "Parameters":
        """
        Create parameters from dictionary.

        Physical Meaning:
            Constructs a Parameters object from a dictionary representation,
            useful for loading configurations from files.

        Args:
            params (Dict[str, Any]): Dictionary of parameters.

        Returns:
            Parameters: Parameters object.
        """
        return cls(
            mu=params["mu"],
            beta=params["beta"],
            lambda_param=params.get("lambda", 0.0),
            nu=params.get("nu", 1.0),
            precision=params.get("precision", "float64"),
            fft_plan=params.get("fft_plan", "MEASURE"),
            tolerance=params.get("tolerance", 1e-12),
        )

    @classmethod
    def default_cosmic(cls) -> "Parameters":
        """
        Create default parameters for cosmic (homogeneous) regime.

        Physical Meaning:
            Provides default parameters for simulations in homogeneous
            "cosmic" media where power law tails A(r) ∝ r^(2β-3) are expected.

        Returns:
            Parameters: Default cosmic parameters.
        """
        return cls(
            mu=1.0,
            beta=1.0,
            lambda_param=0.0,
            nu=1.0,
        )

    @classmethod
    def default_matter(cls) -> "Parameters":
        """
        Create default parameters for matter (inhomogeneous) regime.

        Physical Meaning:
            Provides default parameters for simulations in inhomogeneous
            matter where resonator structures and boundaries are important.

        Returns:
            Parameters: Default matter parameters.
        """
        return cls(
            mu=1.0,
            beta=1.0,
            lambda_param=0.1,
            nu=1.0,
        )

    def __repr__(self) -> str:
        """String representation of parameters."""
        return (
            f"Parameters(mu={self.mu}, beta={self.beta}, "
            f"lambda={self.lambda_param}, nu={self.nu})"
        )
