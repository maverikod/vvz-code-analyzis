"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for residual computation in BVP envelope equation.

This module provides the abstract base class for residual computation
in the 7D BVP envelope equation, defining the common interface for
all residual computer implementations.

Physical Meaning:
    Provides the fundamental interface for computing residuals of the
    7D BVP envelope equation with different domain types and configurations.
    The residual represents how well the current solution satisfies
    the nonlinear envelope equation.

Mathematical Foundation:
    Defines the interface for computing the residual:
    R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s(x,φ,t)
    where κ(|a|) and χ(|a|) are nonlinear coefficients.

Example:
    >>> class MyResidualComputer(ResidualComputerBase):
    ...     def compute_residual(self, envelope, source):
    ...         # Implementation
    ...         pass
"""

import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Union, Optional

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain import Domain
    from ...domain.domain_7d import Domain7D
    from ..bvp_constants import BVPConstants


class ResidualComputerBase(ABC):
    """
    Abstract base class for residual computation in BVP envelope equation.

    Physical Meaning:
        Provides common interface for computing residuals of the
        7D BVP envelope equation with different domain types and configurations.
        The residual represents how well the current solution satisfies
        the nonlinear envelope equation.

    Mathematical Foundation:
        Defines the interface for computing the residual:
        R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s(x,φ,t)
        where κ(|a|) and χ(|a|) are nonlinear coefficients.
    """

    def __init__(
        self,
        domain: Union["Domain", "Domain7D"],
        config_or_constants: Union[Dict[str, Any], "BVPConstants"],
    ):
        """
        Initialize residual computer base.

        Physical Meaning:
            Sets up the base residual computer with the computational domain
            and configuration parameters or constants for computing residuals
            of the 7D envelope equation.

        Args:
            domain (Union[Domain, Domain7D]): Computational domain.
            config_or_constants (Union[Dict[str, Any], BVPConstants]):
                Configuration parameters or BVP constants instance.
        """
        self.domain = domain
        self.config_or_constants = config_or_constants
        self._setup_parameters()

    @abstractmethod
    def _setup_parameters(self) -> None:
        """
        Setup envelope equation parameters.

        Physical Meaning:
            Initializes the parameters needed for computing residuals
            of the envelope equation, including stiffness and susceptibility
            coefficients.
        """
        raise NotImplementedError("Subclasses must implement _setup_parameters method")

    @abstractmethod
    def compute_residual(self, envelope: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute residual of the envelope equation.

        Physical Meaning:
            Computes the residual R = ∇·(κ(|a|)∇a) + k₀²χ(|a|)a - s(x,φ,t)
            for the current envelope solution, representing how well
            the solution satisfies the equation.

        Mathematical Foundation:
            The residual measures how well the current solution satisfies
            the envelope equation and is used in Newton-Raphson iterations.

        Args:
            envelope (np.ndarray): Current envelope solution in 7D space-time.
            source (np.ndarray): Source term s(x,φ,t) in 7D space-time.

        Returns:
            np.ndarray: Residual R = L(a) - s in 7D space-time.
        """
        raise NotImplementedError("Subclasses must implement compute_residual method")

    @abstractmethod
    def _compute_div_kappa_grad(
        self, envelope: np.ndarray, kappa: np.ndarray
    ) -> np.ndarray:
        """
        Compute divergence of kappa times gradient.

        Physical Meaning:
            Computes the divergence of κ times the gradient of the envelope
            using appropriate finite difference methods for the domain type.

        Mathematical Foundation:
            Computes ∇·(κ∇a) = ∂/∂x(κ∂a/∂x) + ∂/∂y(κ∂a/∂y) + ∂/∂z(κ∂a/∂z) +
                              ∂/∂φ₁(κ∂a/∂φ₁) + ∂/∂φ₂(κ∂a/∂φ₂) + ∂/∂φ₃(κ∂a/∂φ₃) +
                              ∂/∂t(κ∂a/∂t)
            using appropriate finite differences for the domain.

        Args:
            envelope (np.ndarray): Envelope field in 7D space-time.
            kappa (np.ndarray): Nonlinear stiffness in 7D space-time.

        Returns:
            np.ndarray: ∇·(κ∇a) term in 7D space-time.
        """
        raise NotImplementedError(
            "Subclasses must implement _compute_div_kappa_grad method"
        )

    def compute_residual_norm(self, residual: np.ndarray) -> float:
        """
        Compute norm of residual for convergence checking.

        Physical Meaning:
            Computes the L2 norm of the residual vector for monitoring
            convergence of the Newton-Raphson iterations.

        Args:
            residual (np.ndarray): Residual vector.

        Returns:
            float: L2 norm of the residual.
        """
        return float(np.linalg.norm(residual))

    def analyze_residual_components(
        self, envelope: np.ndarray, source: np.ndarray, **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze components of the residual.

        Physical Meaning:
            Analyzes the individual components of the residual to understand
            the relative contributions of different terms in the equation.

        Args:
            envelope (np.ndarray): Current envelope solution.
            source (np.ndarray): Source term.
            **kwargs: Additional arguments for specific implementations.

        Returns:
            Dict[str, Any]: Dictionary containing residual component analysis.
        """
        # Default implementation - can be overridden by subclasses
        residual = self.compute_residual(envelope, source)
        residual_norm = self.compute_residual_norm(residual)
        source_norm = np.linalg.norm(source)

        return {
            "total_residual_norm": residual_norm,
            "source_norm": float(source_norm),
            "relative_residual": (
                float(residual_norm / source_norm) if source_norm > 0 else 0.0
            ),
        }

    def __repr__(self) -> str:
        """String representation of residual computer."""
        return f"{self.__class__.__name__}(domain={self.domain})"
