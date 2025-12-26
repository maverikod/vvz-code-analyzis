"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

7D Domain class for BHLFF computational domain.

This module implements the computational domain for 7D phase field theory
simulations, providing grid management, coordinate systems, and boundary
condition handling for the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

Physical Meaning:
    The computational domain represents the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
    where:
    - ℝ³ₓ: 3 spatial coordinates (x, y, z) - conventional geometry
    - 𝕋³_φ: 3 phase coordinates (φ₁, φ₂, φ₃) - internal field states
    - ℝₜ: 1 temporal coordinate (t) - evolution dynamics

    Phase field simulations are performed in this 7D space-time.

Mathematical Foundation:
    The domain implements periodic boundary conditions in the 7D region
    M₇ = [0,L)³ × [0,2π)³ × [0,T) with uniform grid spacing:
    - Spatial: Δx = L/N for spatial coordinates
    - Phase: Δφ = 2π/N_φ for phase coordinates
    - Temporal: Δt = T/N_t for temporal coordinate
"""

import numpy as np
from typing import Tuple, Union, Dict
from dataclasses import dataclass
from typing import Optional


@dataclass
class Domain:
    """
    Computational domain for 7D phase field theory.

    Physical Meaning:
        Represents the computational space for phase field simulations
        in 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, providing grid management
        and coordinate systems for numerical computations.

    Mathematical Foundation:
        Implements periodic boundary conditions in the 7D region:
        M₇ = [0,L)³ × [0,2π)³ × [0,T) with uniform grid spacing:
        - Spatial: Δx = L/N for spatial coordinates
        - Phase: Δφ = 2π/N_φ for phase coordinates
        - Temporal: Δt = T/N_t for temporal coordinate

    Attributes:
        L (float): Spatial domain size in each spatial dimension.
        N (int): Number of grid points per spatial dimension.
        N_phi (int): Number of grid points per phase dimension.
        N_t (int): Number of grid points for temporal dimension.
        T (float): Temporal domain size.
        dimensions (int): Number of spatial dimensions (typically 3).
        dx (float): Spatial grid spacing Δx = L/N.
        dphi (float): Phase grid spacing Δφ = 2π/N_φ.
        dt (float): Temporal grid spacing Δt = T/N_t.
        shape (Tuple[int, ...]): 7D grid shape (N, N, N, N_phi, N_phi, N_phi, N_t).
        spatial_shape (Tuple[int, ...]): Spatial grid shape (N, N, N).
        phase_shape (Tuple[int, ...]): Phase grid shape (N_phi, N_phi, N_phi).
        coordinates (Dict[str, np.ndarray]): Grid coordinates for each dimension type.
    """

    L: float
    N: int
    N_phi: int = 32
    N_t: int = 64
    T: float = 1.0
    dimensions: int = 7
    temporal_config: Optional["TemporalConfig"] = None

    def __post_init__(self) -> None:
        """
        Initialize derived attributes after object creation.

        Physical Meaning:
            Computes grid spacing and coordinate arrays for 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ based on domain size and resolution parameters.
        """
        if self.L <= 0:
            raise ValueError("Domain size L must be positive")
        if self.N <= 0:
            raise ValueError("Number of grid points N must be positive")
        if self.N_phi <= 0:
            raise ValueError("Number of phase grid points N_phi must be positive")
        if self.N_t <= 0:
            raise ValueError("Number of temporal grid points N_t must be positive")
        if self.T <= 0:
            raise ValueError("Temporal domain size T must be positive")
        if self.dimensions != 7:
            raise ValueError("Dimensions must be 7 for 7D BVP theory")

        # Compute grid spacings
        self.dx = self.L / self.N
        self.dphi = 2 * np.pi / self.N_phi
        self.dt = self.T / self.N_t

        # Initialize temporal_config if not provided
        if self.temporal_config is None:
            from .config import TemporalConfig

            self.temporal_config = TemporalConfig(
                T_max=self.T, N_t=self.N_t, dt=self.dt
            )

        # Setup shapes for 7D BVP theory
        self.spatial_shape = tuple([self.N] * 3)  # 3 spatial dimensions
        self.phase_shape = tuple([self.N_phi] * 3)  # 3 phase dimensions
        self.shape = self.spatial_shape + self.phase_shape + (self.N_t,)  # 7D shape

        self._setup_coordinates()

    def get_differentials(self) -> Dict[str, float]:
        """
        Get differential elements for 7D space-time.

        Physical Meaning:
            Returns the differential elements dx, dphi, dt for
            the 7D space-time structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Returns:
            Dict[str, float]: Differential elements.
        """
        return {
            "dx": self.dx,
            "dy": self.dx,  # Same as dx for uniform grid
            "dz": self.dx,  # Same as dx for uniform grid
            "dphi": self.dphi,
            "dphi_1": self.dphi,  # Same as dphi for uniform grid
            "dphi_2": self.dphi,  # Same as dphi for uniform grid
            "dphi_3": self.dphi,  # Same as dphi for uniform grid
            "dt": self.dt,
        }

    def _setup_coordinates(self) -> None:
        """
        Setup coordinate arrays for 7D space-time domain.

        Physical Meaning:
            Creates coordinate arrays for grid points in the 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, used for source placement and field visualization.
        """
        self.coordinates = {}

        # Spatial coordinates ℝ³ₓ (always 3D in 7D BVP theory)
        x = np.linspace(0, self.L, self.N, endpoint=False)
        y = np.linspace(0, self.L, self.N, endpoint=False)
        z = np.linspace(0, self.L, self.N, endpoint=False)
        self.coordinates["x"], self.coordinates["y"], self.coordinates["z"] = (
            np.meshgrid(x, y, z, indexing="ij")
        )

        # Phase coordinates 𝕋³_φ
        phi1 = np.linspace(0, 2 * np.pi, self.N_phi, endpoint=False)
        phi2 = np.linspace(0, 2 * np.pi, self.N_phi, endpoint=False)
        phi3 = np.linspace(0, 2 * np.pi, self.N_phi, endpoint=False)
        self.coordinates["phi1"], self.coordinates["phi2"], self.coordinates["phi3"] = (
            np.meshgrid(phi1, phi2, phi3, indexing="ij")
        )

        # Temporal coordinate ℝₜ
        self.coordinates["t"] = np.linspace(0, self.T, self.N_t, endpoint=False)

    def get_wave_numbers(self) -> dict:
        """
        Get wave number arrays for 7D FFT operations.

        Physical Meaning:
            Computes the wave number arrays for 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ
            for FFT operations, where wave numbers are defined for each dimension type.

        Mathematical Foundation:
            Wave numbers are defined as:
            - Spatial: k = (2π/L)m for periodic boundary conditions
            - Phase: k_φ = m for periodic phase coordinates (m ∈ ℤ)
            - Temporal: k_t = (2π/T)m for temporal coordinates

        Returns:
            dict: Wave number arrays for each dimension type:
                - 'spatial': spatial wave numbers
                - 'phase': phase wave numbers
                - 'temporal': temporal wave numbers
        """
        wave_numbers = {}

        # Spatial wave numbers ℝ³ₓ
        if self.dimensions == 1:
            wave_numbers["spatial"] = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
        elif self.dimensions == 2:
            kx = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
            ky = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
            wave_numbers["spatial"] = np.meshgrid(kx, ky, indexing="ij")
        else:  # 3D
            kx = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
            ky = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
            kz = np.fft.fftfreq(self.N, self.dx) * 2 * np.pi
            wave_numbers["spatial"] = np.meshgrid(kx, ky, kz, indexing="ij")

        # Phase wave numbers 𝕋³_φ
        kphi1 = np.fft.fftfreq(self.N_phi, self.dphi)
        kphi2 = np.fft.fftfreq(self.N_phi, self.dphi)
        kphi3 = np.fft.fftfreq(self.N_phi, self.dphi)
        wave_numbers["phase"] = np.meshgrid(kphi1, kphi2, kphi3, indexing="ij")

        # Temporal wave numbers ℝₜ
        wave_numbers["temporal"] = np.fft.fftfreq(self.N_t, self.dt) * 2 * np.pi

        return wave_numbers

    def get_center_index(self) -> dict:
        """
        Get the index of the domain center for 7D space-time.

        Physical Meaning:
            Returns the grid indices corresponding to the center of each
            dimension type in the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ,
            used for placing point sources and analyzing field patterns.

        Returns:
            dict: Center indices for each dimension type:
                - 'spatial': spatial center indices
                - 'phase': phase center indices
                - 'temporal': temporal center index
        """
        center_indices = {}

        # Spatial center indices
        spatial_center = self.N // 2
        if self.dimensions == 1:
            center_indices["spatial"] = spatial_center
        else:
            center_indices["spatial"] = tuple([spatial_center] * self.dimensions)

        # Phase center indices
        phase_center = self.N_phi // 2
        center_indices["phase"] = tuple([phase_center] * 3)  # 3 phase dimensions

        # Temporal center index
        center_indices["temporal"] = self.N_t // 2

        return center_indices

    def get_volume(self) -> dict:
        """
        Get the domain volume for 7D space-time.

        Physical Meaning:
            Computes the total volume of each dimension type in the 7D space-time
            M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Returns:
            dict: Volume for each dimension type:
                - 'spatial': spatial volume L^d
                - 'phase': phase volume (2π)^3
                - 'temporal': temporal volume T
                - 'total': total 7D volume
        """
        volumes = {}
        volumes["spatial"] = self.L**self.dimensions
        volumes["phase"] = (2 * np.pi) ** 3  # 3 phase dimensions
        volumes["temporal"] = self.T
        volumes["total"] = volumes["spatial"] * volumes["phase"] * volumes["temporal"]
        return volumes

    def get_grid_spacing(self) -> dict:
        """
        Get the grid spacing for 7D space-time.

        Physical Meaning:
            Returns the uniform grid spacing for each dimension type
            in the 7D space-time M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Returns:
            dict: Grid spacing for each dimension type:
                - 'spatial': spatial grid spacing Δx = L/N
                - 'phase': phase grid spacing Δφ = 2π/N_φ
                - 'temporal': temporal grid spacing Δt = T/N_t
        """
        return {"spatial": self.dx, "phase": self.dphi, "temporal": self.dt}

    def get_coordinates(self, dim: int) -> np.ndarray:
        """
        Get coordinates for specific dimension.

        Physical Meaning:
            Returns coordinate array for the specified dimension in the 7D space-time.

        Args:
            dim (int): Dimension index:
                - 0, 1, 2: spatial coordinates (x, y, z)
                - 3, 4, 5: phase coordinates (φ₁, φ₂, φ₃)
                - 6: temporal coordinate (t)

        Returns:
            np.ndarray: Coordinate array for the specified dimension.

        Raises:
            ValueError: If dimension index is out of range.
        """
        if dim < 0 or dim >= 7:
            raise ValueError(f"Dimension {dim} out of range for 7D BVP theory")

        if dim < 3:  # Spatial coordinates
            coord_names = ["x", "y", "z"]
            return self.coordinates[coord_names[dim]]
        elif dim < 6:  # Phase coordinates
            coord_names = ["phi1", "phi2", "phi3"]
            return self.coordinates[coord_names[dim - 3]]
        else:  # Temporal coordinate
            return self.coordinates["t"]

    def __repr__(self) -> str:
        """String representation of the 7D domain."""
        return f"Domain7D(L={self.L}, N={self.N}, N_phi={self.N_phi}, N_t={self.N_t}, T={self.T}, dimensions={self.dimensions})"
