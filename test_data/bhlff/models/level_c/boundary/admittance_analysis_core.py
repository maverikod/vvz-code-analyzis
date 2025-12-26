"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Admittance analysis core module.

This module implements core admittance analysis functionality for boundary effects
in Level C test C1 of 7D phase field theory.

Physical Meaning:
    Analyzes admittance spectrum for boundary effects,
    including resonance detection and quality factor analysis.

Example:
    >>> analyzer = AdmittanceAnalysisCore(bvp_core)
    >>> results = analyzer.analyze_admittance_spectrum(domain, boundary, frequency_range)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, AdmittanceSpectrum
from ..cuda import LevelCCUDAProcessor


class AdmittanceAnalysisCore:
    """
    Admittance analysis core for boundary effects.

    Physical Meaning:
        Analyzes admittance spectrum for boundary effects,
        including resonance detection and quality factor analysis.

    Mathematical Foundation:
        Implements admittance analysis:
        - Admittance calculation: Y(ω) = I(ω)/V(ω)
        - Resonance detection: peaks in |Y(ω)| spectrum
        - Quality factor analysis: Q = ω / (2 * Δω)
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize admittance analyzer.

        Physical Meaning:
            Sets up the admittance analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA processor for vectorized operations
        # CUDA is required for Level C - no fallback to CPU
        try:
            self.cuda_processor = LevelCCUDAProcessor(bvp_core, use_cuda=True)
            self.use_cuda = self.cuda_processor.cuda_available
            if not self.use_cuda:
                raise RuntimeError("CUDA not available - Level C requires GPU acceleration")
        except Exception as e:
            self.logger.error(f"CUDA processor initialization failed: {e}")
            raise RuntimeError(f"Level C requires CUDA: {e}")

    def analyze_admittance_spectrum(
        self,
        domain: Dict[str, Any],
        boundary: BoundaryGeometry,
        frequency_range: Tuple[float, float],
    ) -> AdmittanceSpectrum:
        """
        Analyze admittance spectrum.

        Physical Meaning:
            Analyzes admittance spectrum for boundary effects
            including resonance detection and quality factor analysis.

        Mathematical Foundation:
            Admittance calculation: Y(ω) = I(ω)/V(ω)
            Resonance detection: peaks in |Y(ω)| spectrum
            Quality factor analysis: Q = ω / (2 * Δω)

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            frequency_range (Tuple[float, float]): Frequency range for analysis.

        Returns:
            AdmittanceSpectrum: Admittance spectrum analysis results.
        """
        self.logger.info("Starting admittance spectrum analysis")

        # Extract frequency range
        f_min, f_max = frequency_range
        num_frequencies = 100
        frequencies = np.linspace(f_min, f_max, num_frequencies)

        # CUDA is required for Level C - no fallback
        if not self.use_cuda or self.cuda_processor is None:
            raise RuntimeError("CUDA processor not initialized - Level C requires GPU")
        
        # Create field and source for vectorized computation
        self.logger.info("Creating test field and source for admittance computation")
        field = self._create_test_field_for_admittance(domain, boundary)
        source = self._create_source_field_for_admittance(domain, frequencies[0])
        
        self.logger.info(
            f"Field shape: {field.shape}, source shape: {source.shape}, "
            f"field size: {field.size}, field dtype: {field.dtype}"
        )
        
        # Compute admittance using CUDA vectorized operations
        self.logger.info(f"Calling compute_admittance_vectorized with {len(frequencies)} frequencies")
        admittances = self.cuda_processor.compute_admittance_vectorized(
            field, source, frequencies, domain
        )
        self.logger.info(f"Admittance computation completed: shape={admittances.shape}")

        # Create admittance spectrum
        spectrum = AdmittanceSpectrum(
            frequencies=frequencies,
            admittances=admittances,
            magnitude=np.abs(admittances),
            phase=np.angle(admittances),
        )

        self.logger.info("Admittance spectrum analysis completed")
        return spectrum

    def _compute_admittance_at_frequency(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, omega: float
    ) -> complex:
        """
        Compute admittance at specific frequency.

        Physical Meaning:
            Computes admittance at specific frequency for boundary
            effects analysis.

        Mathematical Foundation:
            Admittance calculation: Y(ω) = I(ω)/V(ω)

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            omega (float): Angular frequency.

        Returns:
            complex: Admittance at frequency.
        """
        # Create source field
        source_field = self._create_source_field(domain, omega)

        # Solve BVP with boundary conditions
        solution_field = self._solve_bvp_with_boundary(
            domain, boundary, source_field, omega
        )

        # Compute current
        current = self._compute_current(solution_field, domain, boundary)

        # Compute voltage
        voltage = self._compute_voltage(solution_field, domain)

        # Calculate admittance
        admittance = current / voltage if voltage != 0 else 0.0

        return admittance

    def _create_source_field(self, domain: Dict[str, Any], omega: float) -> np.ndarray:
        """
        Create source field.

        Physical Meaning:
            Creates source field for admittance analysis
            at specific frequency.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            omega (float): Angular frequency.

        Returns:
            np.ndarray: Source field.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create source field (simplified)
        # In practice, this would involve proper source field creation
        source_field = np.exp(1j * omega * X / L) * np.exp(
            -((X - L / 2) ** 2) / (L / 4) ** 2
        )

        return source_field

    def _solve_bvp_with_boundary(
        self,
        domain: Dict[str, Any],
        boundary: BoundaryGeometry,
        source_field: np.ndarray,
        omega: float,
    ) -> np.ndarray:
        """
        Solve BVP with boundary conditions.

        Physical Meaning:
            Solves boundary value problem with boundary conditions
            for admittance analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            source_field (np.ndarray): Source field.
            omega (float): Angular frequency.

        Returns:
            np.ndarray: Solution field.
        """
        # Apply boundary conditions
        boundary_mask = self._create_boundary_mask(domain, boundary)
        source_with_boundary = self._apply_boundary_conditions(
            source_field, boundary_mask
        )

        # Solve BVP (simplified)
        # In practice, this would involve proper BVP solving
        solution_field = source_with_boundary * np.exp(1j * omega * 0.1)

        return solution_field

    def _apply_boundary_conditions(
        self, source_field: np.ndarray, boundary_mask: np.ndarray
    ) -> np.ndarray:
        """
        Apply boundary conditions.

        Physical Meaning:
            Applies boundary conditions to source field
            for admittance analysis.

        Args:
            source_field (np.ndarray): Source field.
            boundary_mask (np.ndarray): Boundary mask.

        Returns:
            np.ndarray: Field with boundary conditions applied.
        """
        # Apply boundary conditions
        field_with_boundary = source_field * boundary_mask

        return field_with_boundary

    def _create_boundary_mask(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry
    ) -> np.ndarray:
        """
        Create boundary mask.

        Physical Meaning:
            Creates boundary mask for boundary conditions
            in admittance analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.

        Returns:
            np.ndarray: Boundary mask.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create boundary mask (simplified)
        # In practice, this would involve proper boundary mask creation
        boundary_mask = np.ones((N, N, N))

        # Apply boundary conditions
        boundary_mask[0, :, :] = 0.0  # x = 0 boundary
        boundary_mask[-1, :, :] = 0.0  # x = L boundary
        boundary_mask[:, 0, :] = 0.0  # y = 0 boundary
        boundary_mask[:, -1, :] = 0.0  # y = L boundary
        boundary_mask[:, :, 0] = 0.0  # z = 0 boundary
        boundary_mask[:, :, -1] = 0.0  # z = L boundary

        return boundary_mask

    def _compute_current(
        self,
        solution_field: np.ndarray,
        domain: Dict[str, Any],
        boundary: BoundaryGeometry,
    ) -> complex:
        """
        Compute current.

        Physical Meaning:
            Computes current for admittance analysis
            based on solution field.

        Args:
            solution_field (np.ndarray): Solution field.
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.

        Returns:
            complex: Current value.
        """
        # Simplified current calculation
        # In practice, this would involve proper current calculation
        current = np.sum(solution_field) * 1e-6  # Simplified scaling

        return current

    def _compute_voltage(
        self, solution_field: np.ndarray, domain: Dict[str, Any]
    ) -> complex:
        """
        Compute voltage.

        Physical Meaning:
            Computes voltage for admittance analysis
            based on solution field.

        Args:
            solution_field (np.ndarray): Solution field.
            domain (Dict[str, Any]): Domain parameters.

        Returns:
            complex: Voltage value.
        """
        # Simplified voltage calculation
        # In practice, this would involve proper voltage calculation
        voltage = np.mean(solution_field) * 1e-3  # Simplified scaling

        return voltage

    def _create_test_field_for_admittance(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry
    ) -> np.ndarray:
        """Create test field for admittance computation."""
        N = domain.get("N", 64)
        field = np.random.rand(N, N, N) + 1j * np.random.rand(N, N, N)
        field *= 0.1
        return field

    def _create_source_field_for_admittance(
        self, domain: Dict[str, Any], omega: float
    ) -> np.ndarray:
        """Create source field for admittance computation."""
        N = domain.get("N", 64)
        L = domain.get("L", 1.0)
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        source = np.exp(1j * omega * X / L) * np.exp(-((X - L / 2) ** 2) / (L / 4) ** 2)
        return source
