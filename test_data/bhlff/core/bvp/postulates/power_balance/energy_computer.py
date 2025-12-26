"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Energy computation for Power Balance postulate.

This module implements the computation of core energy growth in 7D space-time,
providing the energy component for power balance validation.

Physical Meaning:
    Computes the growth of static core energy in 7D space-time M₇,
    representing the energy stored in the core region of the BVP field.
    This includes contributions from all 7 dimensions.

Mathematical Foundation:
    The core energy growth in 7D is computed as:
    E_core = ∫_core (1/2)[f_φ²|∇_xΘ|² + f_φ²|∇_φΘ|² + β₄(ΔΘ)² + γ₆|∇Θ|⁶ + ...] dV₇

Example:
    >>> energy_computer = EnergyComputer(domain_7d, config)
    >>> core_energy_growth = energy_computer.compute_core_energy_growth(envelope)
"""

import numpy as np
from typing import Dict, Any

from ....domain.domain_7d import Domain7D


class EnergyComputer:
    """
    Core energy computation in 7D space-time.

    Physical Meaning:
        Computes the growth of static core energy in 7D space-time M₇,
        representing the energy stored in the core region of the BVP field.
        This includes contributions from all 7 dimensions according to
        the 7D phase field theory.

    Mathematical Foundation:
        The core energy growth in 7D is computed as:
        E_core = ∫_core (1/2)[f_φ²|∇_xΘ|² + f_φ²|∇_φΘ|² + β₄(ΔΘ)² + γ₆|∇Θ|⁶ + ...] dV₇
        where Θ is the 7D phase vector, f_φ is the phase field constant,
        and the integral includes all 7 dimensions.
    """

    def __init__(self, domain_7d: Domain7D, config: Dict[str, Any]):
        """
        Initialize energy computer.

        Args:
            domain_7d (Domain7D): 7D computational domain.
            config (Dict[str, Any]): Configuration parameters.
        """
        self.domain_7d = domain_7d
        self.config = config

    def compute_core_energy_growth(self, envelope: np.ndarray) -> float:
        """
        Compute growth of static core energy in 7D space-time.

        Physical Meaning:
            Computes the growth of static core energy in 7D space-time M₇,
            representing the energy stored in the core region of the BVP field.
            This includes contributions from all 7 dimensions according to
            the 7D phase field theory.

        Mathematical Foundation:
            The core energy growth in 7D is computed as:
            E_core = ∫_core (1/2)[f_φ²|∇_xΘ|² + f_φ²|∇_φΘ|² + β₄(ΔΘ)² + γ₆|∇Θ|⁶ + ...] dV₇
            where Θ is the 7D phase vector, f_φ is the phase field constant,
            and the integral includes all 7 dimensions.

        Args:
            envelope (np.ndarray): 7D envelope field with shape
                (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)

        Returns:
            float: Computed core energy growth in 7D space-time.
        """
        differentials = self.domain_7d.get_differentials()
        dx = differentials["dx"]
        dy = differentials["dy"]
        dz = differentials["dz"]
        dphi1 = differentials["dphi_1"]
        dphi2 = differentials["dphi_2"]
        dphi3 = differentials["dphi_3"]
        dt = self.domain_7d.temporal_config.dt

        # Use last and previous time slices (if available)
        a_t = envelope[..., -1]
        if envelope.shape[-1] > 1:
            a_prev = envelope[..., -2]
        else:
            a_prev = np.zeros_like(a_t)

        # 7D energy density parameters from theory
        f_phi = float(self.config.get("f_phi", 1.0))  # Phase field constant
        k0 = float(self.config.get("k0", 1.0))  # Wave number
        beta4 = float(self.config.get("beta4", 0.1))  # Fourth-order coefficient
        gamma6 = float(self.config.get("gamma6", 0.01))  # Sixth-order coefficient

        e_t = self._energy_density_7d(
            a_t, dx, dy, dz, dphi1, dphi2, dphi3, f_phi, k0, beta4, gamma6
        )
        e_prev = self._energy_density_7d(
            a_prev, dx, dy, dz, dphi1, dphi2, dphi3, f_phi, k0, beta4, gamma6
        )

        # Define core region as high-amplitude region
        amp_t = np.abs(a_t)
        core_mask = amp_t > (0.5 * np.max(amp_t) if np.max(amp_t) > 0 else 0)

        # 7D volume element
        dV7 = dx * dy * dz * dphi1 * dphi2 * dphi3
        E_core_t = np.sum(e_t[core_mask]) * dV7
        E_core_prev = np.sum(e_prev[core_mask]) * dV7

        dE_dt = (E_core_t - E_core_prev) / (dt if dt > 0 else 1.0)
        return float(dE_dt)

    def _energy_density_7d(
        self,
        a: np.ndarray,
        dx: float,
        dy: float,
        dz: float,
        dphi1: float,
        dphi2: float,
        dphi3: float,
        f_phi: float,
        k0: float,
        beta4: float,
        gamma6: float,
    ) -> np.ndarray:
        """
        Compute 7D energy density according to theory.

        Physical Meaning:
            Implements the 7D energy functional:
            E[Θ] = f_φ²|∇_xΘ|² + f_φ²|∇_φΘ|² + β₄(ΔΘ)² + γ₆|∇Θ|⁶

        Args:
            a (np.ndarray): 7D field array.
            dx, dy, dz (float): Spatial differentials.
            dphi1, dphi2, dphi3 (float): Phase differentials.
            f_phi (float): Phase field constant.
            k0 (float): Wave number.
            beta4 (float): Fourth-order coefficient.
            gamma6 (float): Sixth-order coefficient.

        Returns:
            np.ndarray: 7D energy density array.
        """
        # Spatial gradients (axes 0,1,2)
        grad_x = np.gradient(a, dx, axis=0)
        grad_y = np.gradient(a, dy, axis=1)
        grad_z = np.gradient(a, dz, axis=2)

        # Phase gradients (axes 3,4,5) - U(1)³ structure
        grad_phi1 = np.gradient(a, dphi1, axis=3)
        grad_phi2 = np.gradient(a, dphi2, axis=4)
        grad_phi3 = np.gradient(a, dphi3, axis=5)

        # Spatial gradient magnitude squared
        grad_spatial_sq = (
            np.abs(grad_x) ** 2 + np.abs(grad_y) ** 2 + np.abs(grad_z) ** 2
        )

        # Phase gradient magnitude squared
        grad_phase_sq = (
            np.abs(grad_phi1) ** 2 + np.abs(grad_phi2) ** 2 + np.abs(grad_phi3) ** 2
        )

        # Total gradient magnitude
        grad_total_sq = grad_spatial_sq + grad_phase_sq

        # Laplacian (second derivatives)
        laplacian_x = np.gradient(grad_x, dx, axis=0)
        laplacian_y = np.gradient(grad_y, dy, axis=1)
        laplacian_z = np.gradient(grad_z, dz, axis=2)
        laplacian_phi1 = np.gradient(grad_phi1, dphi1, axis=3)
        laplacian_phi2 = np.gradient(grad_phi2, dphi2, axis=4)
        laplacian_phi3 = np.gradient(grad_phi3, dphi3, axis=5)

        laplacian_sq = (
            np.abs(laplacian_x) ** 2
            + np.abs(laplacian_y) ** 2
            + np.abs(laplacian_z) ** 2
            + np.abs(laplacian_phi1) ** 2
            + np.abs(laplacian_phi2) ** 2
            + np.abs(laplacian_phi3) ** 2
        )

        # 7D energy density according to theory (no mass term)
        energy_density = (
            f_phi**2 * grad_spatial_sq
            + f_phi**2 * grad_phase_sq  # f_φ²|∇_xΘ|²
            + beta4 * laplacian_sq  # f_φ²|∇_φΘ|²
            + gamma6 * (grad_total_sq**3)  # β₄(ΔΘ)²
            # No mass term k₀²|a|² - removed according to 7D BVP theory
        )

        return energy_density
