"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base spectral derivatives implementation for 7D BHLFF Framework.

This module provides the base interface for spectral derivative operations
for the 7D phase field theory, including gradient, divergence, curl, and
higher-order derivatives.

Physical Meaning:
    Spectral derivatives implement mathematical differentiation operations
    in frequency space, providing efficient computation of derivatives
    for 7D phase field calculations with U(1)³ phase structure.

Mathematical Foundation:
    Implements spectral derivatives using the property that differentiation
    in real space corresponds to multiplication by ik in frequency space:
    - Gradient: ∇a → ik * â(k)
    - Divergence: ∇·a → ik · â(k)
    - Curl: ∇×a → ik × â(k)
    - Laplacian: Δa → -|k|² * â(k)

Example:
    >>> deriv = SpectralDerivatives(domain, precision="float64")
    >>> gradient = deriv.compute_gradient(field)
    >>> laplacian = deriv.compute_laplacian(field)
"""

import numpy as np
from typing import Any, Tuple, Dict, Optional
import logging
from abc import ABC, abstractmethod

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain import Domain


class SpectralDerivativesBase(ABC):
    """
    Abstract base class for spectral derivatives in 7D phase field calculations.

    Physical Meaning:
        Defines the interface for mathematical differentiation operations
        in 7D frequency space, providing efficient computation of derivatives
        for 7D phase field calculations with U(1)³ phase structure.

    Mathematical Foundation:
        Uses the property that differentiation in real space corresponds to
        multiplication by ik in frequency space for efficient computation.
    """

    def __init__(self, domain: "Domain", precision: str = "float64"):
        """
        Initialize spectral derivatives base.

        Physical Meaning:
            Sets up the base interface for spectral derivative operations
            with the computational domain and numerical precision.

        Args:
            domain (Domain): Computational domain for derivative operations.
            precision (str): Numerical precision for computations.
        """
        self.domain = domain
        self.precision = precision
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def compute_gradient(self, field: np.ndarray) -> Tuple[np.ndarray, ...]:
        """
        Compute gradient of field in spectral space.

        Physical Meaning:
            Computes the gradient ∇a of the phase field in 7D space-time,
            representing the spatial and phase variations of the field.

        Mathematical Foundation:
            Gradient in spectral space: ∇a → ik * â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            Tuple[np.ndarray, ...]: Gradient components in each dimension.
        """
        raise NotImplementedError("Subclasses must implement compute_gradient method")

    @abstractmethod
    def compute_divergence(self, field: np.ndarray) -> np.ndarray:
        """
        Compute divergence of vector field in spectral space.

        Physical Meaning:
            Computes the divergence ∇·a of the vector field in 7D space-time,
            representing the net flux of the field.

        Mathematical Foundation:
            Divergence in spectral space: ∇·a → ik · â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Vector field to differentiate.

        Returns:
            np.ndarray: Divergence of the field.
        """
        raise NotImplementedError("Subclasses must implement compute_divergence method")

    @abstractmethod
    def compute_curl(self, field: np.ndarray) -> Tuple[np.ndarray, ...]:
        """
        Compute curl of vector field in spectral space.

        Physical Meaning:
            Computes the curl ∇×a of the vector field in 7D space-time,
            representing the rotational component of the field.

        Mathematical Foundation:
            Curl in spectral space: ∇×a → ik × â(k)
            where k is the wave vector and â(k) is the spectral representation.

        Args:
            field (np.ndarray): Vector field to differentiate.

        Returns:
            Tuple[np.ndarray, ...]: Curl components in each dimension.
        """
        raise NotImplementedError("Subclasses must implement compute_curl method")

    @abstractmethod
    def compute_laplacian(self, field: np.ndarray) -> np.ndarray:
        """
        Compute Laplacian of field in spectral space.

        Physical Meaning:
            Computes the Laplacian Δa of the phase field in 7D space-time,
            representing the second-order spatial variations of the field.

        Mathematical Foundation:
            Laplacian in spectral space: Δa → -|k|² * â(k)
            where |k|² is the squared magnitude of the wave vector.

        Args:
            field (np.ndarray): Field to differentiate.

        Returns:
            np.ndarray: Laplacian of the field.
        """
        raise NotImplementedError("Subclasses must implement compute_laplacian method")

    def validate_field(self, field: np.ndarray) -> bool:
        """
        Validate field for derivative computation.

        Physical Meaning:
            Ensures that the field is suitable for derivative computation,
            checking for proper shape, finite values, and compatibility
            with the computational domain.

        Args:
            field (np.ndarray): Field to validate.

        Returns:
            bool: True if field is valid, False otherwise.
        """
        if field is None:
            self.logger.error("Field is None")
            return False

        if not isinstance(field, np.ndarray):
            self.logger.error("Field must be numpy array")
            return False

        if field.size == 0:
            self.logger.error("Field is empty")
            return False

        if not np.isfinite(field).all():
            self.logger.error("Field contains non-finite values")
            return False

        return True

    def __repr__(self) -> str:
        """String representation of spectral derivatives base."""
        return f"{self.__class__.__name__}(domain={self.domain.shape}, precision={self.precision})"
