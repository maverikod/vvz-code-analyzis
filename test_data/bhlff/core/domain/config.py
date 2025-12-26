"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Configuration classes for 7D space-time domain.

This module contains configuration dataclasses for the 7D space-time structure,
providing type-safe configuration for spatial, phase, and temporal coordinates.

Physical Meaning:
    These configuration classes define the structure and parameters for the
    7D space-time domain M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ, ensuring proper setup
    of coordinate systems and grid parameters.

Mathematical Foundation:
    The configuration classes define:
    - Spatial coordinates: x ∈ ℝ³ with extents L_x, L_y, L_z
    - Phase coordinates: φ ∈ 𝕋³ with periodic boundaries
    - Temporal coordinate: t ∈ ℝ with evolution parameters

Example:
    >>> spatial_config = SpatialConfig(L_x=2.0, N_x=128)
    >>> phase_config = PhaseConfig(N_phi_1=64)
    >>> temporal_config = TemporalConfig(T_max=5.0, N_t=500)
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class SpatialConfig:
    """
    Configuration for spatial coordinates ℝ³ₓ.

    Physical Meaning:
        Defines the spatial extent and resolution for the 3D spatial
        coordinates (x, y, z) in the 7D space-time structure.

    Mathematical Foundation:
        Spatial domain: x ∈ [0, L_x], y ∈ [0, L_y], z ∈ [0, L_z]
        with N_x, N_y, N_z grid points respectively.
    """

    L_x: float = 1.0  # Spatial extent in x
    L_y: float = 1.0  # Spatial extent in y
    L_z: float = 1.0  # Spatial extent in z
    N_x: int = 64  # Grid points in x
    N_y: int = 64  # Grid points in y
    N_z: int = 64  # Grid points in z


@dataclass
class PhaseConfig:
    """
    Configuration for phase coordinates 𝕋³_φ.

    Physical Meaning:
        Defines the phase extent and resolution for the 3D phase
        coordinates (φ₁, φ₂, φ₃) in the 7D space-time structure.
        Phase coordinates are periodic with U(1)³ symmetry.

    Mathematical Foundation:
        Phase domain: φ₁ ∈ [0, 2π), φ₂ ∈ [0, 2π), φ₃ ∈ [0, 2π)
        with N_phi_1, N_phi_2, N_phi_3 grid points respectively.
    """

    phi_1_max: float = 2.0 * np.pi  # Phase extent in φ₁
    phi_2_max: float = 2.0 * np.pi  # Phase extent in φ₂
    phi_3_max: float = 2.0 * np.pi  # Phase extent in φ₃
    N_phi_1: int = 32  # Grid points in φ₁
    N_phi_2: int = 32  # Grid points in φ₂
    N_phi_3: int = 32  # Grid points in φ₃


@dataclass
class TemporalConfig:
    """
    Configuration for temporal coordinate ℝₜ.

    Physical Meaning:
        Defines the temporal extent and resolution for the temporal
        coordinate t in the 7D space-time structure, controlling
        the evolution dynamics of the BVP field.

    Mathematical Foundation:
        Temporal domain: t ∈ [0, T_max] with N_t time steps
        and time step size dt = T_max / (N_t - 1).
    """

    T_max: float = 1.0  # Temporal extent
    N_t: int = 100  # Time steps
    dt: float = 0.01  # Time step size
