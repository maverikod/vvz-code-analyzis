"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis for Power Balance postulate.

This module implements the analysis of boundary fluxes in 7D space-time,
providing radiation losses and reflection components for power balance validation.

Physical Meaning:
    Analyzes boundary fluxes in 7D space-time M₇, separating them into
    spatial (EM) and phase (weak) components for radiation loss and
    reflection analysis.

Mathematical Foundation:
    Separates boundary fluxes into:
    - EM radiation losses: outward flux from spatial boundaries
    - Weak radiation losses: outward flux from phase boundaries
    - Reflection: inward flux from all boundaries

Example:
    >>> boundary_analyzer = BoundaryAnalyzer(domain_7d)
    >>> radiation_losses = boundary_analyzer.compute_radiation_losses(envelope)
    >>> reflection = boundary_analyzer.compute_reflection(envelope)
"""

import numpy as np
from typing import Dict, Any, Tuple

from ....domain.domain_7d import Domain7D


class BoundaryAnalyzer:
    """
    Boundary flux analysis in 7D space-time.

    Physical Meaning:
        Analyzes boundary fluxes in 7D space-time M₇, separating them into
        spatial (EM) and phase (weak) components for radiation loss and
        reflection analysis according to the BVP theory.

    Mathematical Foundation:
        Separates boundary fluxes into:
        - EM radiation losses: P_rad = ∫_∂Ω₇ σ|E|² dS₇
        - Weak radiation losses: P_weak = ∫_∂Ω₇ σ_weak|W|² dS₇
        - Reflection: R = ∫_∂Ω₇ |r|²|E_inc|² dS₇
    """

    def __init__(self, domain_7d: Domain7D):
        """
        Initialize boundary analyzer.

        Args:
            domain_7d (Domain7D): 7D computational domain.
        """
        self.domain_7d = domain_7d

    def compute_radiation_losses(self, envelope: np.ndarray) -> float:
        """
        Compute EM/weak radiation and losses in 7D space-time.

        Physical Meaning:
            Computes the EM/weak radiation and losses in 7D space-time M₇,
            representing the energy radiated away from the system through
            electromagnetic and weak interactions. This includes contributions
            from all 7 dimensions according to the BVP theory.

        Mathematical Foundation:
            The radiation losses in 7D are computed as:
            P_rad = ∫_∂Ω₇ σ|E|² dS₇ + ∫_∂Ω₇ σ_weak|W|² dS₇
            where σ and σ_weak are the electromagnetic and weak conductivities,
            E and W are the electromagnetic and weak fields derived from
            the 7D BVP envelope, and the integral is over the 7D boundary.

        Args:
            envelope (np.ndarray): 7D envelope field with shape
                (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)

        Returns:
            float: Computed EM/weak radiation losses in 7D space-time.
        """
        # Get 7D boundary flux components
        outward_spatial, inward_spatial = self._split_boundary_flux_spatial(envelope)
        outward_phase, inward_phase = self._split_boundary_flux_phase(envelope)

        # EM radiation losses (outward flux from spatial boundaries)
        em_losses = float(outward_spatial)

        # Weak radiation losses (outward flux from phase boundaries)
        weak_losses = float(outward_phase)

        # Total radiation losses
        total_radiation_losses = em_losses + weak_losses

        return total_radiation_losses

    def compute_reflection(self, envelope: np.ndarray) -> float:
        """
        Compute reflection component in 7D space-time.

        Physical Meaning:
            Computes the reflection component in 7D space-time M₇,
            representing the energy reflected back from the boundaries
            due to impedance mismatch and boundary conditions. This includes
            reflections from both spatial and phase boundaries.

        Mathematical Foundation:
            The reflection in 7D is computed as:
            R = ∫_∂Ω₇ |r|²|E_inc|² dS₇
            where r is the reflection coefficient, E_inc is the
            incident field amplitude, and the integral is over the 7D boundary.

        Args:
            envelope (np.ndarray): 7D envelope field with shape
                (N_x, N_y, N_z, N_φ₁, N_φ₂, N_φ₃, N_t)

        Returns:
            float: Computed reflection component in 7D space-time.
        """
        # Get 7D boundary flux components
        outward_spatial, inward_spatial = self._split_boundary_flux_spatial(envelope)
        outward_phase, inward_phase = self._split_boundary_flux_phase(envelope)

        # Total reflection (inward flux from all boundaries)
        total_reflection = float(-inward_spatial - inward_phase)

        return total_reflection

    def _split_boundary_flux_spatial(self, envelope: np.ndarray) -> Tuple[float, float]:
        """
        Split spatial boundary flux into outward and inward components.

        Physical Meaning:
            Separates the flux through spatial boundaries (x, y, z) into
            outward (positive) and inward (negative) components for
            EM radiation analysis.

        Returns:
            Tuple[float, float]: (outward_spatial, inward_spatial)
        """
        a_t = envelope[..., -1]
        differentials = self.domain_7d.get_differentials()
        dx = differentials["dx"]
        dy = differentials["dy"]
        dz = differentials["dz"]
        dphi1 = differentials["dphi_1"]
        dphi2 = differentials["dphi_2"]
        dphi3 = differentials["dphi_3"]

        # Spatial gradients only
        grad_x = np.gradient(a_t, dx, axis=0)
        grad_y = np.gradient(a_t, dy, axis=1)
        grad_z = np.gradient(a_t, dz, axis=2)
        jx = np.imag(np.conj(a_t) * grad_x)
        jy = np.imag(np.conj(a_t) * grad_y)
        jz = np.imag(np.conj(a_t) * grad_z)

        # 7D surface elements for spatial faces
        dS_x = dy * dz * dphi1 * dphi2 * dphi3
        dS_y = dx * dz * dphi1 * dphi2 * dphi3
        dS_z = dx * dy * dphi1 * dphi2 * dphi3

        spatial_faces = [
            (-jx[0, ...], dS_x),  # -x face (n = -ex)
            (jx[-1, ...], dS_x),  # +x face
            (-jy[:, 0, ...], dS_y),
            (jy[:, -1, ...], dS_y),
            (-jz[:, :, 0, ...], dS_z),
            (jz[:, :, -1, ...], dS_z),
        ]

        outward = 0.0
        inward = 0.0
        for face_flux_density, dS in spatial_faces:
            face_flux = np.sum(face_flux_density) * dS
            if face_flux >= 0:
                outward += face_flux
            else:
                inward += face_flux

        return float(outward), float(inward)

    def _split_boundary_flux_phase(self, envelope: np.ndarray) -> Tuple[float, float]:
        """
        Split phase boundary flux into outward and inward components.

        Physical Meaning:
            Separates the flux through phase boundaries (φ₁, φ₂, φ₃) into
            outward (positive) and inward (negative) components for
            weak interaction analysis.

        Returns:
            Tuple[float, float]: (outward_phase, inward_phase)
        """
        a_t = envelope[..., -1]
        differentials = self.domain_7d.get_differentials()
        dx = differentials["dx"]
        dy = differentials["dy"]
        dz = differentials["dz"]
        dphi1 = differentials["dphi_1"]
        dphi2 = differentials["dphi_2"]
        dphi3 = differentials["dphi_3"]

        # Phase gradients only
        grad_phi1 = np.gradient(a_t, dphi1, axis=3)
        grad_phi2 = np.gradient(a_t, dphi2, axis=4)
        grad_phi3 = np.gradient(a_t, dphi3, axis=5)
        jphi1 = np.imag(np.conj(a_t) * grad_phi1)
        jphi2 = np.imag(np.conj(a_t) * grad_phi2)
        jphi3 = np.imag(np.conj(a_t) * grad_phi3)

        # 7D surface elements for phase faces
        dS_phi1 = dx * dy * dz * dphi2 * dphi3
        dS_phi2 = dx * dy * dz * dphi1 * dphi3
        dS_phi3 = dx * dy * dz * dphi1 * dphi2

        phase_faces = [
            (-jphi1[:, :, :, 0, ...], dS_phi1),  # -φ₁ face
            (jphi1[:, :, :, -1, ...], dS_phi1),  # +φ₁ face
            (-jphi2[:, :, :, :, 0, ...], dS_phi2),
            (jphi2[:, :, :, :, -1, ...], dS_phi2),
            (-jphi3[:, :, :, :, :, 0], dS_phi3),
            (jphi3[:, :, :, :, :, -1], dS_phi3),
        ]

        outward = 0.0
        inward = 0.0
        for face_flux_density, dS in phase_faces:
            face_flux = np.sum(face_flux_density) * dS
            if face_flux >= 0:
                outward += face_flux
            else:
                inward += face_flux

        return float(outward), float(inward)
