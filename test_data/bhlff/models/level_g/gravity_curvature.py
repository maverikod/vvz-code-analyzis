"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

VBP envelope curvature calculations for gravitational effects in 7D phase field theory.

This module implements comprehensive calculations of VBP envelope curvature
including envelope curvature descriptors, anisotropy measures, and focusing rates.

Theoretical Background:
    In 7D BVP theory, gravity arises from the curvature of the VBP (Wave Basis Substrate)
    envelope, not from spacetime curvature. The effective metric g_eff[Θ] is derived
    from the phase field Θ(x,φ,t) and dispersion relations c_φ(a,k), χ/κ bridge.

Mathematical Foundation:
    Envelope curvature: K_env = invariants from ∇Θ, c_φ(a,k), A^{ij}=χ'/κ δ^{ij}
    Effective metric: g_eff[Θ] with g00=-1/c_φ^2, gij=A^{ij} (isotropic case)
    Anisotropy index: measures deviation from isotropic envelope

Example:
    >>> envelope_calc = VBPEnvelopeCurvatureCalculator(domain, params)
    >>> curvature_descriptors = envelope_calc.compute_envelope_curvature(phase_field)
"""

import numpy as np
from typing import Dict, Any, Tuple, Optional
from .cosmology import EnvelopeEffectiveMetric


class VBPEnvelopeCurvatureCalculator:
    """
    Calculator for VBP envelope curvature descriptors.

    Physical Meaning:
        Computes envelope curvature descriptors from the VBP (Wave Basis Substrate)
        phase field configuration. Gravity arises from the curvature of the phase
        envelope, not from spacetime curvature. The effective metric g_eff[Θ] is
        derived from phase field gradients and dispersion relations.

    Mathematical Foundation:
        Implements envelope curvature calculation from phase field Θ(x,φ,t):
        K_env = invariants from ∇Θ, c_φ(a,k), A^{ij}=χ'/κ δ^{ij}
        Effective metric: g_eff[Θ] with g00=-1/c_φ^2, gij=A^{ij} (isotropic)
    """

    def __init__(self, domain: "Domain", params: Dict[str, Any]):
        """
        Initialize curvature calculator.

        Physical Meaning:
            Sets up the computational framework for curvature
            calculations with appropriate numerical parameters.

        Args:
            domain: Computational domain
            params: Physical parameters
        """
        self.domain = domain
        self.params = params
        self._setup_curvature_parameters()

        # Initialize EnvelopeEffectiveMetric for integration
        self.envelope_metric = EnvelopeEffectiveMetric(params)

    def _setup_curvature_parameters(self) -> None:
        """
        Setup parameters for curvature calculations.

        Physical Meaning:
            Initializes numerical parameters for curvature
            calculations including resolution and precision.
        """
        self.resolution = self.params.get("resolution", 256)
        self.domain_size = self.params.get("domain_size", 100.0)
        self.precision = self.params.get("precision", 1e-12)
        self.derivative_order = self.params.get("derivative_order", 4)

    def compute_envelope_curvature(self, phase_field: np.ndarray) -> Dict[str, Any]:
        """
        Compute VBP envelope curvature descriptors.

        Physical Meaning:
            Calculates envelope curvature descriptors from the phase field Θ(x,φ,t).
            The curvature describes the distortion of the VBP envelope, which gives
            rise to gravitational effects. This replaces classical Riemann tensor
            calculations with VBP-specific curvature measures.

        Mathematical Foundation:
            K_env = invariants from ∇Θ, c_φ(a,k), A^{ij}=χ'/κ δ^{ij}
            Effective metric: g_eff[Θ] with g00=-1/c_φ^2, gij=A^{ij} (isotropic)

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            Dictionary containing envelope curvature descriptors
        """
        # Compute phase field gradients
        phase_gradients = self._compute_phase_gradients(phase_field)

        # Compute effective metric from phase field
        g_eff = self._compute_effective_metric(phase_field, phase_gradients)

        # Compute envelope curvature invariants
        curvature_invariants = self._compute_envelope_invariants(phase_gradients, g_eff)

        # Compute anisotropy index
        anisotropy_index = self._compute_anisotropy_index(g_eff)

        # Compute focusing rate
        focusing_rate = self._compute_focusing_rate(phase_gradients, g_eff)

        return {
            "envelope_curvature_scalar": curvature_invariants["scalar"],
            "anisotropy_index": anisotropy_index,
            "focusing_rate": focusing_rate,
            "effective_metric": g_eff,
            "phase_gradients": phase_gradients,
            "curvature_invariants": curvature_invariants,
        }

    def compute_envelope_effective_metric(self, phase_field: np.ndarray) -> np.ndarray:
        """
        Compute effective metric using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes the effective metric g_eff[Θ] using the integrated
            EnvelopeEffectiveMetric for VBP envelope dynamics.

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            Effective metric tensor g_eff[Θ]
        """
        return self.envelope_metric.compute_envelope_curvature_metric(phase_field)

    def compute_anisotropic_envelope_metric(
        self, phase_field: np.ndarray
    ) -> np.ndarray:
        """
        Compute anisotropic effective metric using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes an anisotropic effective metric g_eff[Θ] using the integrated
            EnvelopeEffectiveMetric for VBP envelope dynamics with anisotropy.

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            Anisotropic effective metric tensor g_eff[Θ]
        """
        phase_gradients = self._compute_phase_gradients(phase_field)
        envelope_invariants = self._compute_envelope_invariants(phase_gradients, None)

        anisotropy_measure = envelope_invariants.get("anisotropy", 0.0)
        chi_kappa = self.params.get("chi_kappa", 1.0)

        anisotropic_invariants = {
            "A_xx": chi_kappa * (1.0 + 0.1 * anisotropy_measure),
            "A_yy": chi_kappa * (1.0 - 0.05 * anisotropy_measure),
            "A_zz": chi_kappa * (1.0 + 0.02 * anisotropy_measure),
        }

        return self.envelope_metric.compute_anisotropic_metric(anisotropic_invariants)

    def compute_cosmological_scale_factor(self, t: float) -> float:
        """
        Compute cosmological scale factor using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes the cosmological scale factor using the integrated
            EnvelopeEffectiveMetric for VBP envelope dynamics.

        Args:
            t: Cosmological time

        Returns:
            Scale factor from VBP envelope dynamics
        """
        return self.envelope_metric.compute_scale_factor(t)

    def _compute_phase_gradients(
        self, phase_field: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """
        Compute gradients of the phase field.

        Physical Meaning:
            Calculates the gradients of the phase field Θ(x,φ,t) with respect to
            spatial coordinates x and phase coordinates φ. These gradients are
            fundamental for computing envelope curvature.

        Mathematical Foundation:
            ∇_x Θ = ∂Θ/∂x^i, ∇_φ Θ = ∂Θ/∂φ^j
            where x^i are spatial coordinates and φ^j are phase coordinates

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            Dictionary containing phase field gradients
        """
        # Compute spatial gradients (3D)
        spatial_gradients = np.gradient(phase_field, axis=(0, 1, 2))

        # Compute phase gradients (3D phase space)
        phase_gradients = np.gradient(phase_field, axis=(3, 4, 5))

        # Compute time gradient
        time_gradient = np.gradient(phase_field, axis=6)

        return {
            "spatial": spatial_gradients,
            "phase": phase_gradients,
            "time": time_gradient,
        }

    def _compute_effective_metric(
        self, phase_field: np.ndarray, phase_gradients: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """
        Compute effective metric from phase field.

        Physical Meaning:
            Calculates the effective metric g_eff[Θ] from the phase field configuration.
            This metric describes the geometry of the VBP envelope and replaces
            the classical spacetime metric in 7D BVP theory.

        Mathematical Foundation:
            g_eff[Θ] with g00=-1/c_φ^2, gij=A^{ij}=χ'/κ δ^{ij} (isotropic case)
            where c_φ is the phase velocity and χ/κ is the bridge parameter

        Args:
            phase_field: Phase field configuration
            phase_gradients: Phase field gradients

        Returns:
            Effective metric tensor g_eff[Θ]
        """
        # Get parameters
        c_phi = self.params.get("c_phi", 1.0)  # Phase velocity
        chi_kappa = self.params.get("chi_kappa", 1.0)  # Bridge parameter

        # Initialize 7D effective metric
        g_eff = np.zeros((7, 7))

        # Time component: g00 = -1/c_φ^2
        g_eff[0, 0] = -1.0 / (c_phi**2)

        # Spatial components: gij = A^{ij} = χ'/κ δ^{ij} (isotropic)
        for i in range(1, 4):
            g_eff[i, i] = chi_kappa

        # Phase components: gαβ (phase space metric)
        for alpha in range(4, 7):
            g_eff[alpha, alpha] = 1.0  # Unit phase space metric

        # Add phase field dependent corrections
        phase_amplitude = np.mean(np.abs(phase_field))
        correction_factor = 1.0 + 0.1 * phase_amplitude  # Small correction

        for i in range(7):
            g_eff[i, i] *= correction_factor

        return g_eff

    def _compute_envelope_invariants(
        self, phase_gradients: Dict[str, np.ndarray], g_eff: np.ndarray
    ) -> Dict[str, float]:
        """
        Compute envelope curvature invariants.

        Physical Meaning:
            Calculates scalar invariants of the envelope curvature that are
            independent of coordinate system choice. These replace classical
            curvature invariants like Ricci scalar in GR.

        Mathematical Foundation:
            K_env_scalar = invariants from ∇Θ, c_φ(a,k), A^{ij}
            These are constructed from phase field gradients and effective metric

        Args:
            phase_gradients: Phase field gradients
            g_eff: Effective metric

        Returns:
            Dictionary containing envelope curvature invariants
        """
        # Compute scalar curvature from phase gradients
        spatial_grads = phase_gradients["spatial"]
        phase_grads = phase_gradients["phase"]

        # Scalar invariant: sum of squared gradients (ensure real and non-negative)
        spatial_invariant = np.sum(
            [np.sum(np.abs(grad) ** 2) for grad in spatial_grads]
        )
        phase_invariant = np.sum([np.sum(np.abs(grad) ** 2) for grad in phase_grads])

        # Combined envelope curvature scalar (ensure real and non-negative)
        envelope_scalar = np.real(spatial_invariant + phase_invariant)

        # Anisotropy measure (ensure real and non-negative)
        anisotropy_measure = np.real(
            np.std([np.sum(np.abs(grad) ** 2) for grad in spatial_grads])
        )

        # Focusing measure (ensure real and non-negative)
        focusing_measure = np.real(
            np.sum([np.sum(np.abs(grad)) for grad in spatial_grads])
        )

        return {
            "scalar": envelope_scalar,
            "anisotropy": anisotropy_measure,
            "focusing": focusing_measure,
            "spatial_invariant": np.real(spatial_invariant),
            "phase_invariant": np.real(phase_invariant),
        }

    def _compute_anisotropy_index(self, g_eff: np.ndarray) -> float:
        """
        Compute anisotropy index of the effective metric.

        Physical Meaning:
            Calculates the anisotropy index which measures deviation from
            isotropic envelope configuration. This is a key descriptor
            of envelope geometry in 7D BVP theory.

        Mathematical Foundation:
            Anisotropy index = std(g_ii) / mean(g_ii) for spatial components
            where g_ii are diagonal components of the effective metric

        Args:
            g_eff: Effective metric tensor

        Returns:
            Anisotropy index (dimensionless)
        """
        # Extract spatial diagonal components (indices 1,2,3)
        spatial_diagonals = [g_eff[i, i] for i in range(1, 4)]

        # Compute anisotropy index
        mean_diagonal = np.mean(spatial_diagonals)
        std_diagonal = np.std(spatial_diagonals)

        if mean_diagonal > 0:
            anisotropy_index = std_diagonal / mean_diagonal
        else:
            anisotropy_index = 0.0

        return anisotropy_index

    def _compute_focusing_rate(
        self, phase_gradients: Dict[str, np.ndarray], g_eff: np.ndarray
    ) -> float:
        """
        Compute focusing rate of the envelope.

        Physical Meaning:
            Calculates the focusing rate which describes how the envelope
            focuses or defocuses wavefronts. This is related to the
            energy argument ΔE≤0 for envelope stability.

        Mathematical Foundation:
            Focusing rate = -∇·(∇Θ/|∇Θ|) where Θ is the phase field
            Positive values indicate focusing, negative values indicate defocusing

        Args:
            phase_gradients: Phase field gradients
            g_eff: Effective metric

        Returns:
            Focusing rate
        """
        spatial_grads = phase_gradients["spatial"]

        # Compute divergence of normalized gradients
        focusing_rate = 0.0

        for i, grad in enumerate(spatial_grads):
            # Compute gradient magnitude
            grad_magnitude = np.sqrt(np.sum(grad**2))

            if grad_magnitude > 1e-12:  # Avoid division by zero
                # Normalize gradient
                normalized_grad = grad / grad_magnitude

                # Compute divergence (simplified)
                divergence = np.sum(np.gradient(normalized_grad, axis=i))
                focusing_rate -= divergence

        return focusing_rate

    def compute_envelope_invariants(self, phase_field: np.ndarray) -> Dict[str, float]:
        """
        Compute envelope curvature invariants from phase field.

        Physical Meaning:
            Calculates scalar invariants of the envelope curvature that are
            independent of coordinate system choice. These replace classical
            curvature invariants like Ricci scalar in GR.

        Mathematical Foundation:
            K_env_scalar = invariants from ∇Θ, c_φ(a,k), A^{ij}
            These are constructed from phase field gradients and effective metric

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            Dictionary containing envelope curvature invariants
        """
        # Compute phase field gradients
        phase_gradients = self._compute_phase_gradients(phase_field)

        # Compute effective metric
        g_eff = self._compute_effective_metric(phase_field, phase_gradients)

        # Compute invariants
        invariants = self._compute_envelope_invariants(phase_gradients, g_eff)

        return invariants

    def compute_envelope_effective_metric(self, phase_field: np.ndarray) -> np.ndarray:
        """
        Compute effective metric using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes the effective metric g_eff[Θ] using the integrated
            EnvelopeEffectiveMetric class, incorporating envelope curvature
            and phase field dynamics.

        Mathematical Foundation:
            Uses EnvelopeEffectiveMetric.compute_envelope_curvature_metric()
            to compute g_eff[Θ] = f(∇Θ, c_φ(a,k), A^{ij}) from phase field.

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            7x7 effective metric tensor g_eff[Θ] from integrated envelope metric
        """
        return self.envelope_metric.compute_envelope_curvature_metric(phase_field)

    def compute_anisotropic_envelope_metric(
        self, phase_field: np.ndarray
    ) -> np.ndarray:
        """
        Compute anisotropic effective metric using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes an anisotropic effective metric g_eff[Θ] using the
            integrated EnvelopeEffectiveMetric class, allowing for
            different spatial components reflecting anisotropic envelope dynamics.

        Mathematical Foundation:
            Uses EnvelopeEffectiveMetric.compute_anisotropic_metric() with
            envelope invariants derived from phase field gradients.

        Args:
            phase_field: Phase field configuration Θ(x,φ,t)

        Returns:
            7x7 anisotropic effective metric tensor g_eff[Θ]
        """
        # Compute envelope invariants from phase field
        phase_gradients = self._compute_phase_gradients(phase_field)
        envelope_invariants = self._compute_envelope_invariants(phase_gradients, None)

        # Extract anisotropic components
        anisotropy_measure = envelope_invariants.get("anisotropy", 0.0)
        chi_kappa = self.params.get("chi_kappa", 1.0)

        # Create anisotropic envelope invariants
        anisotropic_invariants = {
            "A_xx": chi_kappa * (1.0 + 0.1 * anisotropy_measure),
            "A_yy": chi_kappa * (1.0 - 0.05 * anisotropy_measure),
            "A_zz": chi_kappa * (1.0 + 0.02 * anisotropy_measure),
        }

        return self.envelope_metric.compute_anisotropic_metric(anisotropic_invariants)

    def compute_cosmological_scale_factor(self, t: float) -> float:
        """
        Compute cosmological scale factor using integrated EnvelopeEffectiveMetric.

        Physical Meaning:
            Computes the cosmological scale factor using the integrated
            EnvelopeEffectiveMetric class, based on VBP envelope dynamics
            rather than classical spacetime expansion.

        Mathematical Foundation:
            Uses EnvelopeEffectiveMetric.compute_scale_factor() with
            power law evolution instead of exponential growth.

        Args:
            t: Cosmological time

        Returns:
            Scale factor from VBP envelope dynamics
        """
        return self.envelope_metric.compute_scale_factor(t)
