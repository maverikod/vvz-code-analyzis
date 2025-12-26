"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Gravitational potential evolution for large-scale structure models in 7D phase field theory.

This module implements gravitational potential evolution methods for
large-scale structure formation, including Poisson equation
and FFT-based solvers.

Theoretical Background:
    Gravitational potential evolution in large-scale structure formation
    involves solving the Poisson equation with density field
    and gravitational effects.

Mathematical Foundation:
    Implements Poisson equation:
    ∇²Φ = 4πGρ

Example:
    >>> evolution = PotentialEvolution(evolution_params)
    >>> potential = evolution.solve_poisson_equation(density_field)
"""

import numpy as np
from typing import Dict, Any, Optional


class PotentialEvolution:
    """
    Gravitational potential evolution for large-scale structure models.

    Physical Meaning:
        Implements gravitational potential evolution methods for
        large-scale structure formation, including Poisson
        equation and FFT-based solvers.

    Mathematical Foundation:
        Implements Poisson equation:
        ∇²Φ = 4πGρ

    Attributes:
        evolution_params (dict): Evolution parameters
        G (float): Gravitational constant
    """

    def __init__(self, evolution_params: Dict[str, Any]):
        """
        Initialize potential evolution.

        Physical Meaning:
            Sets up the potential evolution with evolution
            parameters and physical constants.

        Args:
            evolution_params: Evolution parameters
        """
        self.evolution_params = evolution_params
        self.cosmology_params = evolution_params.get("cosmology", {})

        # Physical parameters
        self.G = self.cosmology_params.get("G", 6.67430e-11)  # Gravitational constant

    def solve_poisson_equation(self, density: np.ndarray) -> np.ndarray:
        """
        Solve Poisson equation for gravitational potential using FFT-based solver.

        Physical Meaning:
            Solves the Poisson equation ∇²Φ = 4πGρ to find
            the gravitational potential using spectral methods
            for 7D phase field theory.

        Mathematical Foundation:
            ∇²Φ = 4πGρ
            In spectral space: -k²Φ̂ = 4πGρ̂
            Therefore: Φ̂ = -4πGρ̂/k²

        Args:
            density: Density field

        Returns:
            Gravitational potential from 7D BVP theory
        """
        if density is None:
            return np.zeros_like(density)

        # Compute source term
        source = 4 * np.pi * self.G * density

        # FFT-based Poisson solver for 7D phase field theory
        # Transform to spectral space
        source_spectral = np.fft.fftn(source)

        # Compute wave vectors for 3D spatial coordinates
        # In 7D phase space-time, we use 3D spatial coordinates (x,y,z)
        # and 3D phase coordinates (φ1,φ2,φ3) plus time t
        shape = density.shape
        kx = np.fft.fftfreq(shape[0], d=1.0)
        ky = np.fft.fftfreq(shape[1], d=1.0) if len(shape) > 1 else np.array([0])
        kz = np.fft.fftfreq(shape[2], d=1.0) if len(shape) > 2 else np.array([0])

        # Create wave vector grid
        if len(shape) == 3:
            KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
            k_squared = KX**2 + KY**2 + KZ**2
        elif len(shape) == 2:
            KX, KY = np.meshgrid(kx, ky, indexing="ij")
            k_squared = KX**2 + KY**2
        else:
            k_squared = kx**2

        # Avoid division by zero at k=0
        k_squared[k_squared == 0] = 1.0

        # Solve in spectral space: Φ̂ = -4πGρ̂/k²
        potential_spectral = -source_spectral / k_squared

        # Transform back to real space
        potential = np.fft.ifftn(potential_spectral).real

        return potential
