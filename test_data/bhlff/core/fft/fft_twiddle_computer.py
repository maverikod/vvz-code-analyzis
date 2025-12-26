"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

FFT twiddle factors computation for optimized FFT operations.

This module provides twiddle factors computation for efficient
spectral operations in the 7D phase field theory.

Physical Meaning:
    Twiddle factors are complex exponential factors used in FFT
    operations to avoid repeated computation during runtime.

Mathematical Foundation:
    Twiddle factors are W_N^k = exp(-2πik/N) where N is the
    FFT size and k is the frequency index.

Example:
    >>> twiddle_computer = FFTTwiddleComputer(domain, precision="float64")
    >>> twiddle_factors = twiddle_computer.compute_twiddle_factors(1)
"""

import numpy as np
from typing import Dict

from ..domain import Domain


class FFTTwiddleComputer:
    """
    FFT twiddle factors computer for optimized FFT operations.

    Physical Meaning:
        Computes complex exponential factors used in FFT operations
        for efficient spectral transformations.

    Mathematical Foundation:
        Computes twiddle factors W_N^k = exp(-2πik/N) for forward FFT
        and W_N^k = exp(2πik/N) for inverse FFT.

    Attributes:
        domain (Domain): Computational domain.
        precision (str): Numerical precision.
        _twiddle_cache (Dict): Cache for pre-computed twiddle factors.
    """

    def __init__(self, domain: Domain, precision: str = "float64") -> None:
        """
        Initialize FFT twiddle factors computer.

        Physical Meaning:
            Sets up the twiddle factors computer with specified precision
            for efficient computation of complex exponential factors.

        Args:
            domain (Domain): Computational domain for FFT operations.
            precision (str): Numerical precision ("float32", "float64").
        """
        self.domain = domain
        self.precision = precision
        self._twiddle_cache = {}

    def precompute_twiddle_factors(self) -> None:
        """
        Pre-compute twiddle factors for all FFT plans.

        Physical Meaning:
            Pre-computes complex exponential factors used in FFT
            operations to avoid repeated computation during runtime.

        Mathematical Foundation:
            Twiddle factors are W_N^k = exp(-2πik/N) where N is the
            FFT size and k is the frequency index.
        """
        # Pre-compute for all dimensions
        for dim in range(1, self.domain.dimensions + 1):
            self._twiddle_cache[f"{dim}d"] = self.compute_twiddle_factors(dim)

    def compute_twiddle_factors(
        self, dimensions: int, conjugate: bool = False
    ) -> np.ndarray:
        """
        Compute twiddle factors for given dimensions.

        Physical Meaning:
            Computes the complex exponential factors used in FFT
            operations for the specified number of dimensions.

        Mathematical Foundation:
            W_N^k = exp(-2πik/N) for forward FFT
            W_N^k = exp(2πik/N) for inverse FFT (conjugate=True)

        Args:
            dimensions (int): Number of dimensions.
            conjugate (bool): Whether to compute conjugate twiddle factors.

        Returns:
            np.ndarray: Twiddle factors.
        """
        if dimensions == 1:
            return self._compute_1d_twiddle_factors(conjugate)
        elif dimensions == 2:
            return self._compute_2d_twiddle_factors(conjugate)
        else:
            return self._compute_3d_twiddle_factors(conjugate)

    def _compute_1d_twiddle_factors(self, conjugate: bool = False) -> np.ndarray:
        """
        Compute 1D twiddle factors.

        Physical Meaning:
            Computes complex exponential factors for 1D FFT operations.

        Args:
            conjugate (bool): Whether to compute conjugate factors.

        Returns:
            np.ndarray: 1D twiddle factors.
        """
        N = self.domain.N
        k = np.arange(N)

        if conjugate:
            # For inverse FFT
            twiddle = np.exp(2j * np.pi * k / N)
        else:
            # For forward FFT
            twiddle = np.exp(-2j * np.pi * k / N)

        return twiddle.astype(self.precision)

    def _compute_2d_twiddle_factors(
        self, conjugate: bool = False
    ) -> Dict[str, np.ndarray]:
        """
        Compute 2D twiddle factors.

        Physical Meaning:
            Computes complex exponential factors for 2D FFT operations
            using row-column decomposition.

        Args:
            conjugate (bool): Whether to compute conjugate factors.

        Returns:
            Dict[str, np.ndarray]: 2D twiddle factors for rows and columns.
        """
        N = self.domain.N

        # Row twiddle factors
        row_twiddle = self._compute_1d_twiddle_factors(conjugate)

        # Column twiddle factors
        col_twiddle = self._compute_1d_twiddle_factors(conjugate)

        return {
            "row": row_twiddle,
            "column": col_twiddle,
        }

    def _compute_3d_twiddle_factors(
        self, conjugate: bool = False
    ) -> Dict[str, np.ndarray]:
        """
        Compute 3D twiddle factors.

        Physical Meaning:
            Computes complex exponential factors for 3D FFT operations
            using multi-dimensional decomposition.

        Args:
            conjugate (bool): Whether to compute conjugate factors.

        Returns:
            Dict[str, np.ndarray]: 3D twiddle factors for all dimensions.
        """
        N = self.domain.N

        # Compute twiddle factors for each dimension
        twiddle_1d = self._compute_1d_twiddle_factors(conjugate)

        return {
            "x": twiddle_1d,
            "y": twiddle_1d,
            "z": twiddle_1d,
        }

    def get_twiddle_cache(self) -> Dict:
        """
        Get the twiddle factors cache.

        Physical Meaning:
            Returns the pre-computed twiddle factors cache.

        Returns:
            Dict: Twiddle factors cache.
        """
        return self._twiddle_cache

    def get_twiddle_factor(self, dim1: int, dim2: int) -> np.ndarray:
        """
        Get twiddle factor for specific dimensions.

        Args:
            dim1 (int): First dimension.
            dim2 (int): Second dimension.

        Returns:
            np.ndarray: Twiddle factor.
        """
        key = f"twiddle_{dim1}_{dim2}"
        if key not in self._twiddle_cache:
            # Compute twiddle factor for these dimensions
            n = self.domain.N if dim1 < 3 else self.domain.N_phi
            if dim1 == 6 or dim2 == 6:  # temporal dimension
                n = self.domain.N_t
            self._twiddle_cache[key] = self._compute_1d_twiddle_factors(n)
        return self._twiddle_cache[key]

    def compute_inverse_twiddle_factors(self) -> Dict[str, np.ndarray]:
        """
        Compute inverse twiddle factors.

        Returns:
            Dict[str, np.ndarray]: Inverse twiddle factors.
        """
        inverse_factors = {}
        for key, factors in self._twiddle_cache.items():
            inverse_factors[f"inverse_{key}"] = np.conj(factors)
        return inverse_factors
