"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Topological charge computation for BVP framework.

This module implements efficient computation of topological charges
using block processing and vectorization for large 7D domains.
"""

import numpy as np
from typing import Dict, Any, Tuple, List, Optional

# CUDA optimization imports
try:
    import cupy as cp

    CUDA_AVAILABLE = True
except ImportError:
    CUDA_AVAILABLE = False
    cp = np

from ...domain import Domain
from ..bvp_constants import BVPConstants


class ChargeComputation:
    """
    Computes topological charges using efficient algorithms.

    Physical Meaning:
        Computes topological charges using block processing and
        vectorization for maximum performance on large 7D domains.
    """

    def __init__(self, domain: Domain, config: Dict[str, Any], constants: BVPConstants):
        """
        Initialize charge computation.

        Physical Meaning:
            Sets up charge computation with domain information and
            configuration parameters for efficient computation.

        Args:
            domain (Domain): Computational domain.
            config (Dict[str, Any]): Configuration parameters.
            constants (BVPConstants): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants

        # Computation parameters
        self.winding_precision = config.get("winding_precision", 1e-6)
        self.charge_threshold = config.get("charge_threshold", 0.1)

    def compute_block_charge(self, phase_block: np.ndarray) -> List[float]:
        """
        Compute topological charge for a block of phase data.

        Physical Meaning:
            Computes topological charge using winding number computation
            for a block of phase data with vectorized operations.

        Mathematical Foundation:
            Q = (1/2π) ∮ ∇φ · dl computed using vectorized operations

        Args:
            phase_block (np.ndarray): Phase data block.

        Returns:
            List[float]: List of topological charges for the block.
        """
        try:
            # Use CUDA if available
            if CUDA_AVAILABLE and self.config.get("use_cuda", True):
                return self._compute_charge_cuda(phase_block)
            else:
                return self._compute_charge_cpu(phase_block)

        except Exception as e:
            # Fallback to CPU computation
            return self._compute_charge_cpu(phase_block)

    def _compute_charge_cuda(self, phase_block: np.ndarray) -> List[float]:
        """Compute charge using CUDA acceleration."""
        try:
            # Convert to CuPy array
            phase_gpu = cp.asarray(phase_block)

            # Compute gradients using CuPy
            gradients = []
            for axis in range(phase_gpu.ndim):
                grad = cp.gradient(phase_gpu, axis=axis)
                gradients.append(grad)

            # Compute winding number
            winding = self._compute_winding_cuda(phase_gpu, gradients)

            # Convert back to CPU
            charges = cp.asnumpy(winding)
            return charges.tolist()

        except Exception:
            # Fallback to CPU
            return self._compute_charge_cpu(phase_block)

    def _compute_charge_cpu(self, phase_block: np.ndarray) -> List[float]:
        """Compute charge using CPU computation."""
        # Compute gradients
        gradients = []
        for axis in range(phase_block.ndim):
            grad = np.gradient(phase_block, axis=axis)
            gradients.append(grad)

        # Compute winding number
        winding = self._compute_winding_cpu(phase_block, gradients)

        return winding.tolist()

    def _compute_winding_cuda(
        self, phase: cp.ndarray, gradients: List[cp.ndarray]
    ) -> cp.ndarray:
        """Compute winding number using CUDA."""
        # Compute phase differences for winding calculation
        phase_diff = cp.diff(phase, axis=0)

        # Handle phase wrapping
        phase_diff = cp.where(phase_diff > np.pi, phase_diff - 2 * np.pi, phase_diff)
        phase_diff = cp.where(phase_diff < -np.pi, phase_diff + 2 * np.pi, phase_diff)

        # Compute winding number
        winding = cp.sum(phase_diff, axis=0) / (2 * np.pi)

        return winding

    def _compute_winding_cpu(
        self, phase: np.ndarray, gradients: List[np.ndarray]
    ) -> np.ndarray:
        """Compute winding number using CPU."""
        # Compute phase differences for winding calculation
        phase_diff = np.diff(phase, axis=0)

        # Handle phase wrapping
        phase_diff = np.where(phase_diff > np.pi, phase_diff - 2 * np.pi, phase_diff)
        phase_diff = np.where(phase_diff < -np.pi, phase_diff + 2 * np.pi, phase_diff)

        # Compute winding number
        winding = np.sum(phase_diff, axis=0) / (2 * np.pi)

        return winding

    def find_charge_locations(
        self, phase_block: np.ndarray, block_offset: int = 0
    ) -> List[Tuple[int, ...]]:
        """
        Find locations of significant topological charges.

        Physical Meaning:
            Identifies locations where topological charges exceed
            the threshold for significant charge.

        Args:
            phase_block (np.ndarray): Phase data block.
            block_offset (int): Offset for block position.

        Returns:
            List[Tuple[int, ...]]: List of charge locations.
        """
        # Compute charges for the block
        charges = self.compute_block_charge(phase_block)

        # Find significant charges
        significant_charges = []
        for i, charge in enumerate(charges):
            if abs(charge) > self.charge_threshold:
                # Convert 1D index to multi-dimensional coordinates
                coords = np.unravel_index(i, phase_block.shape)
                # Add block offset
                coords = tuple(c + block_offset for c in coords)
                significant_charges.append(coords)

        return significant_charges

    def compute_charge_density(self, phase: np.ndarray) -> np.ndarray:
        """
        Compute topological charge density.

        Physical Meaning:
            Computes the local topological charge density throughout
            the field for detailed analysis.

        Mathematical Foundation:
            ρ = (1/2π) ∇²φ computed using finite differences

        Args:
            phase (np.ndarray): Phase field data.

        Returns:
            np.ndarray: Charge density field.
        """
        # Compute second derivatives for charge density
        second_derivatives = []
        for axis in range(phase.ndim):
            # Compute second derivative along this axis
            grad = np.gradient(phase, axis=axis)
            second_deriv = np.gradient(grad, axis=axis)
            second_derivatives.append(second_deriv)

        # Compute Laplacian
        laplacian = sum(second_derivatives)

        # Compute charge density
        charge_density = laplacian / (2 * np.pi)

        return charge_density

    def analyze_charge_distribution(self, charges: List[float]) -> Dict[str, Any]:
        """
        Analyze distribution of topological charges.

        Physical Meaning:
            Analyzes the statistical distribution of topological charges
            to understand the field's topological characteristics.

        Args:
            charges (List[float]): List of topological charges.

        Returns:
            Dict[str, Any]: Charge distribution analysis.
        """
        if not charges:
            return {
                "total_charges": 0,
                "mean_charge": 0.0,
                "std_charge": 0.0,
                "max_charge": 0.0,
                "min_charge": 0.0,
                "positive_charges": 0,
                "negative_charges": 0,
            }

        charges_array = np.array(charges)

        return {
            "total_charges": len(charges),
            "mean_charge": float(np.mean(charges_array)),
            "std_charge": float(np.std(charges_array)),
            "max_charge": float(np.max(charges_array)),
            "min_charge": float(np.min(charges_array)),
            "positive_charges": int(np.sum(charges_array > 0)),
            "negative_charges": int(np.sum(charges_array < 0)),
            "charge_variance": float(np.var(charges_array)),
            "charge_skewness": float(self._compute_skewness(charges_array)),
            "charge_kurtosis": float(self._compute_kurtosis(charges_array)),
        }

    def _compute_skewness(self, data: np.ndarray) -> float:
        """Compute skewness of charge distribution."""
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 3))

    def _compute_kurtosis(self, data: np.ndarray) -> float:
        """Compute kurtosis of charge distribution."""
        mean = np.mean(data)
        std = np.std(data)
        if std == 0:
            return 0.0
        return float(np.mean(((data - mean) / std) ** 4)) - 3.0
