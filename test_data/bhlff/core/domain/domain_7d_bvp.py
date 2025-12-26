"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D BVP Domain implementation for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

This module implements the 7D BVP domain structure according to the theory,
providing proper separation of spatial, phase, and temporal coordinates.

Physical Meaning:
    Implements the 7D phase space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ where:
    - ℝ³ₓ: 3 spatial coordinates (x, y, z) - physical geometry
    - 𝕋³_φ: 3 phase parameters (φ₁, φ₂, φ₃) - internal field states
    - ℝₜ: 1 temporal coordinate (t) - evolution dynamics

Mathematical Foundation:
    The 7D domain represents the complete phase space-time structure
    of the BVP theory, where the field a(x,φ,t) ∈ ℂ³ is a U(1)³ phase vector
    that evolves in this 7D space-time.

Example:
    >>> domain = Domain7DBVP(L_spatial=1.0, N_spatial=64, N_phase=32, T=1.0, N_t=128)
    >>> print(f"Spatial shape: {domain.spatial_shape}")
    >>> print(f"Phase shape: {domain.phase_shape}")
    >>> print(f"Full 7D shape: {domain.shape}")
"""

import numpy as np
from typing import Tuple, Dict, Any
from dataclasses import dataclass
import logging


@dataclass
class Domain7DBVP:
    """
    7D BVP Domain for M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

    Physical Meaning:
        Represents the 7D phase space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
        where the BVP field a(x,φ,t) ∈ ℂ³ evolves according to the
        7D envelope equation.

    Mathematical Foundation:
        - Spatial coordinates: ℝ³ₓ with periodic boundary conditions
        - Phase coordinates: 𝕋³_φ with 2π periodicity
        - Temporal coordinate: ℝₜ with finite time interval

    Attributes:
        L_spatial (float): Spatial domain size in each spatial dimension.
        N_spatial (int): Number of grid points in each spatial dimension.
        N_phase (int): Number of grid points in each phase dimension.
        T (float): Temporal domain size.
        N_t (int): Number of temporal grid points.
        dimensions (int): Total dimensions (always 7 for BVP).
    """

    # Spatial domain parameters
    L_spatial: float = 1.0
    N_spatial: int = 64

    # Phase domain parameters
    N_phase: int = 32

    # Temporal domain parameters
    T: float = 1.0
    N_t: int = 128

    # Computed properties
    dimensions: int = 7

    def __post_init__(self):
        """Initialize computed properties."""
        self.logger = logging.getLogger(__name__)

        # Validate parameters
        self._validate_parameters()

        # Compute derived properties
        self._compute_derived_properties()

        self.logger.info(
            f"Domain7DBVP initialized: {self.spatial_shape} + {self.phase_shape} + {self.temporal_shape} = {self.shape}"
        )

    def _validate_parameters(self) -> None:
        """Validate domain parameters."""
        if self.L_spatial <= 0:
            raise ValueError(f"L_spatial must be positive, got {self.L_spatial}")
        if self.N_spatial <= 0:
            raise ValueError(f"N_spatial must be positive, got {self.N_spatial}")
        if self.N_phase <= 0:
            raise ValueError(f"N_phase must be positive, got {self.N_phase}")
        if self.T <= 0:
            raise ValueError(f"T must be positive, got {self.T}")
        if self.N_t <= 0:
            raise ValueError(f"N_t must be positive, got {self.N_t}")

    def _compute_derived_properties(self) -> None:
        """Compute derived properties."""
        # Grid spacing
        self.dx = self.L_spatial / self.N_spatial
        self.dphi = 2 * np.pi / self.N_phase
        self.dt = self.T / self.N_t

        # Coordinate arrays
        self.x = np.linspace(0, self.L_spatial, self.N_spatial, endpoint=False)
        self.y = np.linspace(0, self.L_spatial, self.N_spatial, endpoint=False)
        self.z = np.linspace(0, self.L_spatial, self.N_spatial, endpoint=False)
        self.phi1 = np.linspace(0, 2 * np.pi, self.N_phase, endpoint=False)
        self.phi2 = np.linspace(0, 2 * np.pi, self.N_phase, endpoint=False)
        self.phi3 = np.linspace(0, 2 * np.pi, self.N_phase, endpoint=False)
        self.t = np.linspace(0, self.T, self.N_t, endpoint=False)

        # Wave vectors
        self.kx = 2 * np.pi * np.fft.fftfreq(self.N_spatial, self.dx)
        self.ky = 2 * np.pi * np.fft.fftfreq(self.N_spatial, self.dx)
        self.kz = 2 * np.pi * np.fft.fftfreq(self.N_spatial, self.dx)
        self.kphi1 = 2 * np.pi * np.fft.fftfreq(self.N_phase, self.dphi)
        self.kphi2 = 2 * np.pi * np.fft.fftfreq(self.N_phase, self.dphi)
        self.kphi3 = 2 * np.pi * np.fft.fftfreq(self.N_phase, self.dphi)
        self.kt = 2 * np.pi * np.fft.fftfreq(self.N_t, self.dt)

        # Volume elements
        self.dV_spatial = self.dx**3
        self.dV_phase = self.dphi**3
        self.dV_temporal = self.dt
        self.dV_total = self.dV_spatial * self.dV_phase * self.dV_temporal

    @property
    def spatial_shape(self) -> Tuple[int, int, int]:
        """Spatial domain shape (N_x, N_y, N_z)."""
        return (self.N_spatial, self.N_spatial, self.N_spatial)

    @property
    def phase_shape(self) -> Tuple[int, int, int]:
        """Phase domain shape (N_φ₁, N_φ₂, N_φ₃)."""
        return (self.N_phase, self.N_phase, self.N_phase)

    @property
    def temporal_shape(self) -> Tuple[int]:
        """Temporal domain shape (N_t,)."""
        return (self.N_t,)

    @property
    def shape(self) -> Tuple[int, int, int, int, int, int, int]:
        """Full 7D domain shape (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)."""
        return (
            self.N_spatial,
            self.N_spatial,
            self.N_spatial,
            self.N_phase,
            self.N_phase,
            self.N_phase,
            self.N_t,
        )

    @property
    def size(self) -> int:
        """Get total number of grid points."""
        return np.prod(self.shape)

    def get_grid_spacing(self) -> Dict[str, float]:
        """
        Get grid spacing for all dimensions.

        Physical Meaning:
            Returns the grid spacing for spatial, phase, and temporal
            dimensions, representing the resolution of the computational grid.

        Returns:
            Dict[str, float]: Grid spacing for each dimension type.
        """
        return {"spatial": self.dx, "phase": self.dphi, "temporal": self.dt}

    def get_total_volume(self) -> float:
        """
        Get total volume of the 7D domain.

        Physical Meaning:
            Returns the total volume of the 7D space-time domain,
            representing the total computational space available.

        Returns:
            float: Total volume of the 7D domain.
        """
        return self.dV_total

    @property
    def spatial_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Spatial coordinate arrays (x, y, z)."""
        return (self.x, self.y, self.z)

    @property
    def phase_coordinates(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Phase coordinate arrays (φ₁, φ₂, φ₃)."""
        return (self.phi1, self.phi2, self.phi3)

    @property
    def temporal_coordinates(self) -> np.ndarray:
        """Temporal coordinate array (t)."""
        return self.t

    @property
    def spatial_wave_vectors(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Spatial wave vector arrays (k_x, k_y, k_z)."""
        return (self.kx, self.ky, self.kz)

    @property
    def phase_wave_vectors(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Phase wave vector arrays (k_φ₁, k_φ₂, k_φ₃)."""
        return (self.kphi1, self.kphi2, self.kphi3)

    @property
    def temporal_wave_vectors(self) -> np.ndarray:
        """Temporal wave vector array (k_t)."""
        return self.kt

    def get_coordinate_meshgrids(self) -> Tuple[np.ndarray, ...]:
        """
        Get coordinate meshgrids for all 7 dimensions.

        Physical Meaning:
            Returns meshgrids for all 7 coordinates, enabling
            evaluation of fields at specific points in M₇.

        Returns:
            Tuple[np.ndarray, ...]: 7D coordinate meshgrids (X, Y, Z, Φ₁, Φ₂, Φ₃, T).
        """
        X, Y, Z, PHI1, PHI2, PHI3, T = np.meshgrid(
            self.x,
            self.y,
            self.z,
            self.phi1,
            self.phi2,
            self.phi3,
            self.t,
            indexing="ij",
        )
        return (X, Y, Z, PHI1, PHI2, PHI3, T)

    def get_wave_vector_meshgrids(self) -> Tuple[np.ndarray, ...]:
        """
        Get wave vector meshgrids for all 7 dimensions.

        Physical Meaning:
            Returns meshgrids for all 7 wave vectors, enabling
            spectral operations in frequency space.

        Returns:
            Tuple[np.ndarray, ...]: 7D wave vector meshgrids (KX, KY, KZ, KΦ₁, KΦ₂, KΦ₃, KT).
        """
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            self.kx,
            self.ky,
            self.kz,
            self.kphi1,
            self.kphi2,
            self.kphi3,
            self.kt,
            indexing="ij",
        )
        return (KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT)

    def compute_wave_vector_magnitude(self) -> np.ndarray:
        """
        Compute 7D wave vector magnitude |k|.

        Physical Meaning:
            Computes the magnitude of the 7D wave vector, representing
            the spatial frequency of field components in M₇.

        Mathematical Foundation:
            |k|² = k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²

        Returns:
            np.ndarray: Wave vector magnitudes |k|.
        """
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = self.get_wave_vector_meshgrids()

        k_magnitude_squared = (
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )

        return np.sqrt(k_magnitude_squared)

    def get_volume_element(self, coordinate_type: str = "total") -> float:
        """
        Get volume element for specified coordinate type.

        Physical Meaning:
            Returns the volume element for integration over the specified
            coordinate subspace in M₇.

        Args:
            coordinate_type (str): Type of coordinates ('spatial', 'phase', 'temporal', 'total').

        Returns:
            float: Volume element.
        """
        if coordinate_type == "spatial":
            return self.dV_spatial
        elif coordinate_type == "phase":
            return self.dV_phase
        elif coordinate_type == "temporal":
            return self.dV_temporal
        elif coordinate_type == "total":
            return self.dV_total
        else:
            raise ValueError(f"Unknown coordinate type: {coordinate_type}")

    def __repr__(self) -> str:
        """String representation of domain."""
        return (
            f"Domain7DBVP("
            f"spatial=({self.N_spatial}³, L={self.L_spatial}), "
            f"phase=({self.N_phase}³, 2π), "
            f"temporal=({self.N_t}, T={self.T}))"
        )
