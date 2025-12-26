"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP block coefficients computation for 7D phase field theory.

This module implements amplitude-dependent coefficient computation
(stiffness and susceptibility) for BVP block processing, preserving
7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with vectorized operations.

Physical Meaning:
    Computes nonlinear material coefficients κ(|a|) and χ(|a|) that
    depend on field amplitude, representing material response in 7D
    BVP theory with proper 7D structure preservation.

Mathematical Foundation:
    - Stiffness: κ(|a|) = κ₀ + κ₂|a|²
    - Susceptibility: χ(|a|) = χ₀ + χ₂|a|²
    All computed element-wise on 7D blocks without broadcasting shortcuts.
"""

import numpy as np
from typing import Any


class BVPBlockCoefficients:
    """
    BVP block coefficients computation for 7D phase field theory.

    Physical Meaning:
        Computes amplitude-dependent material coefficients (stiffness and
        susceptibility) for BVP block processing, preserving 7D structure
        M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ with vectorized operations.

    Mathematical Foundation:
        Implements nonlinear coefficient computation:
        - κ(|a|) = κ₀ + κ₂|a|² (stiffness)
        - χ(|a|) = χ₀ + χ₂|a|² (susceptibility)
        All operations are vectorized, preserving 7D structure.
    """

    def __init__(self, kappa_0: float = 1.0, kappa_2: float = 0.1,
                 chi_0: float = 0.5, chi_2: float = 0.05):
        """
        Initialize BVP block coefficients computer.

        Args:
            kappa_0 (float): Base stiffness κ₀ > 0.
            kappa_2 (float): Nonlinear coupling coefficient κ₂ > 0.
            chi_0 (float): Base susceptibility χ₀.
            chi_2 (float): Nonlinear susceptibility coefficient χ₂.
        """
        self.kappa_0 = kappa_0
        self.kappa_2 = kappa_2
        self.chi_0 = chi_0
        self.chi_2 = chi_2

    def compute_stiffness(
        self, amplitude: np.ndarray, block_info: Any = None
    ) -> np.ndarray:
        """
        Compute stiffness κ(|a|) as amplitude-dependent tensor per block.

        Physical Meaning:
            Computes the nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|² according to
            7D BVP theory, where κ₀ is the base stiffness and κ₂ is the
            nonlinear coupling coefficient. Evaluated per block as amplitude-dependent
            tensor preserving 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            κ(|a|) = κ₀ + κ₂|a|²
            where κ₀ > 0 and κ₂ > 0 are material parameters.
            Computed element-wise on 7D block, ensuring correct shape without
            broadcasting shortcuts.

        Args:
            amplitude (np.ndarray): Field amplitude |a| (7D) with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            block_info: Block information (optional).

        Returns:
            np.ndarray: Stiffness κ(|a|) with same 7D shape as amplitude,
                computed element-wise without broadcasting.
        """
        # Verify 7D structure
        if amplitude.ndim != 7:
            raise ValueError(
                f"Expected 7D amplitude for stiffness computation, got {amplitude.ndim}D. "
                f"Shape: {amplitude.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Compute κ(|a|) = κ₀ + κ₂|a|² element-wise on 7D block
        # All operations are vectorized, preserving 7D structure
        # No broadcasting - amplitude already has correct 7D shape
        kappa = self.kappa_0 + self.kappa_2 * (amplitude ** 2)

        # Ensure positive stiffness (physical requirement) - vectorized operation
        kappa = np.maximum(kappa, 1e-10)

        return kappa

    def compute_susceptibility(
        self, amplitude: np.ndarray, block_info: Any = None
    ) -> np.ndarray:
        """
        Compute susceptibility χ(|a|) as amplitude-dependent tensor per block.

        Physical Meaning:
            Computes the nonlinear susceptibility χ(|a|) = χ₀ + χ₂|a|² according to
            7D BVP theory, representing the material response to the field.
            Evaluated per block as amplitude-dependent tensor preserving 7D structure
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            χ(|a|) = χ₀ + χ₂|a|²
            where χ₀ and χ₂ are material parameters.
            Computed element-wise on 7D block, ensuring correct shape without
            broadcasting shortcuts.

        Args:
            amplitude (np.ndarray): Field amplitude |a| (7D) with shape
                (N₀, N₁, N₂, N₃, N₄, N₅, N₆) representing spatial (0,1,2),
                phase (3,4,5), and temporal (6) dimensions.
            block_info: Block information (optional).

        Returns:
            np.ndarray: Susceptibility χ(|a|) with same 7D shape as amplitude,
                computed element-wise without broadcasting.
        """
        # Verify 7D structure
        if amplitude.ndim != 7:
            raise ValueError(
                f"Expected 7D amplitude for susceptibility computation, got {amplitude.ndim}D. "
                f"Shape: {amplitude.shape}. Level C operates in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ."
            )

        # Compute χ(|a|) = χ₀ + χ₂|a|² element-wise on 7D block
        # All operations are vectorized, preserving 7D structure
        # No broadcasting - amplitude already has correct 7D shape
        chi = self.chi_0 + self.chi_2 * (amplitude ** 2)

        return chi

