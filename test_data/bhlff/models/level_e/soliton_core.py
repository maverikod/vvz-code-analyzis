"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core soliton functionality for Level E experiments in 7D phase field theory.

This module contains the core soliton model class with basic functionality
for finding and analyzing soliton solutions.

Theoretical Background:
    Implements the core 7D phase field configuration Θ(x,φ,t) ∈ T^3_φ with
    topological charge B computed via U(1)^3 winding integrals and basic
    soliton operations. The classical SU(3) field configuration is a
    4D pedagogical limit, not the core 7D construction.

Example:
    >>> soliton = SolitonModel(domain, physics_params)
    >>> solution = soliton.find_soliton_solution(initial_guess)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from abc import ABC, abstractmethod

from .soliton_energy import SolitonEnergyCalculator
from .soliton_stability import SolitonStabilityAnalyzer
from .soliton_optimization import SolitonOptimizer, ConvergenceError


class SolitonModel(ABC):
    """
    Base class for soliton models in 7D phase field theory.

    Physical Meaning:
        Represents stable localized solutions of the nonlinear phase field
        equations with topological protection. Solitons are the fundamental
        particle-like structures in the 7D theory, realized as phase patterns
        on the U(1)^3 substrate with controlled winding over φ-coordinates.

    Mathematical Foundation:
        Implements the 7D phase field configuration Θ(x,φ,t) ∈ T^3_φ with
        topological charge B computed via U(1)^3 winding integrals and WZW
        term for baryon number conservation. The classical SU(3) field
        configuration is a 4D pedagogical limit, not the core 7D construction.
    """

    def __init__(self, domain: "Domain", physics_params: Dict[str, Any]):
        """
        Initialize soliton model.

        Physical Meaning:
            Sets up the computational framework for finding and analyzing
            stable soliton solutions in the 7D phase field.

        Args:
            domain: Computational domain with grid information
            physics_params: Physical parameters including β, μ, λ, S₄, S₆
        """
        self.domain = domain
        self.params = physics_params
        self._setup_field_operators()
        self._setup_topological_charge()

        # Initialize specialized components
        self._energy_calculator = SolitonEnergyCalculator(domain, physics_params)
        self._stability_analyzer = SolitonStabilityAnalyzer(domain, physics_params)
        self._optimizer = SolitonOptimizer(domain, physics_params)

    def _setup_field_operators(self) -> None:
        """
        Setup field operators for soliton calculations.

        Physical Meaning:
            Initializes the mathematical operators needed for computing
            the energy functional and its derivatives in the 7D phase field.
        """
        # Setup fractional Laplacian operator
        self._setup_fractional_laplacian()

        # Setup Skyrme terms
        self._setup_skyrme_terms()

        # Setup WZW term
        self._setup_wzw_term()

    def _setup_fractional_laplacian(self) -> None:
        """Setup fractional Laplacian operator."""
        mu = self.params.get("mu", 1.0)
        beta = self.params.get("beta", 1.0)

        # Compute wave vectors
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)

        KX, KY, KZ = np.meshgrid(kx, ky, kz, indexing="ij")
        k_magnitude = np.sqrt(KX**2 + KY**2 + KZ**2)

        # Fractional Laplacian in spectral space
        self._frac_laplacian_spectral = mu * (k_magnitude ** (2 * beta))

    def _setup_skyrme_terms(self) -> None:
        """Setup Skyrme interaction terms."""
        self.S4 = self.params.get("S4", 0.1)
        self.S6 = self.params.get("S6", 0.01)
        self.F2 = self.params.get("F2", 1.0)

    def _setup_wzw_term(self) -> None:
        """
        Setup Wess-Zumino-Witten term for baryon number conservation.

        Physical Meaning:
            Initializes the WZW term that ensures baryon number conservation
            and provides the correct quantum statistics for solitons.

        Mathematical Foundation:
            WZW coefficient: (N_c/240π²)∫ε^μνρστTr(L_μ L_ν L_ρ L_σ L_τ) d⁵x
        """
        self.N_c = self.params.get("N_c", 3)  # Number of colors
        self.wzw_coupling = self.params.get("wzw_coupling", 1.0)
        self.wzw_coefficient = self.N_c / (240 * np.pi**2)

        # Setup WZW integration parameters
        self.wzw_integration_order = self.params.get("wzw_integration_order", 5)
        self.wzw_precision = self.params.get("wzw_precision", 1e-6)

    def _setup_topological_charge(self) -> None:
        """
        Setup topological charge calculation for 7D U(1)^3 phase winding.

        Physical Meaning:
            Initializes the calculation of topological charge which represents
            the baryon number of the soliton via U(1)^3 winding over φ-coordinates.

        Mathematical Foundation:
            B = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ) for 7D phase field Θ(x,φ) ∈ T^3_φ
            The classical SU(3) form B = (1/24π²)∫ε^μνρσTr(L_ν L_ρ L_σ) is a
            4D pedagogical limit, not the core 7D construction.
        """
        self.charge_integration_radius = self.params.get("charge_radius", 2.0)
        self.charge_precision = self.params.get("charge_precision", 1e-6)
        self.charge_integration_points = self.params.get(
            "charge_integration_points", 64
        )

    def find_soliton_solution(self, initial_guess: np.ndarray) -> Dict[str, Any]:
        """
        Find soliton solution using iterative methods.

        Physical Meaning:
            Searches for stable localized field configurations that minimize
            the energy functional while preserving topological charge.

        Mathematical Foundation:
            Solves the stationary equation δE/δU = 0 where E is the energy
            functional with Skyrme terms and WZW contribution.

        Args:
            initial_guess: Initial field configuration U(x)

        Returns:
            Dict containing solution, energy, topological charge, stability
        """
        # Use optimizer to find solution
        solution = self._optimizer.find_solution(initial_guess)

        # Analyze solution properties
        energy = self.compute_soliton_energy(solution)
        charge = self.compute_topological_charge(solution)
        stability = self.analyze_soliton_stability(solution)

        return {
            "solution": solution,
            "energy": energy,
            "topological_charge": charge,
            "stability": stability,
        }

    def compute_soliton_energy(self, soliton: np.ndarray) -> float:
        """
        Compute total energy of soliton configuration.

        Physical Meaning:
            Calculates the total energy of the soliton including kinetic,
            Skyrme, and WZW contributions.

        Mathematical Foundation:
            E = ∫[F₂²/2 Tr(L_M L^M) + S₄/4 J₄[U] + S₆/6 J₆[U] + Γ_WZW[U]] dV

        Args:
            soliton: Soliton field configuration

        Returns:
            Total energy of the configuration
        """
        return self._energy_calculator.compute_total_energy(soliton)

    def analyze_soliton_stability(self, soliton: np.ndarray) -> Dict[str, Any]:
        """
        Analyze stability of soliton solution.

        Physical Meaning:
            Investigates the response of the soliton to small perturbations
            to determine if it represents a stable minimum of the energy
            functional.

        Mathematical Foundation:
            Computes the spectrum of the Hessian matrix δ²E/δU² at the
            soliton solution to identify unstable modes.

        Args:
            soliton: Soliton field configuration

        Returns:
            Dict containing stability analysis, unstable modes, frequencies
        """
        return self._stability_analyzer.analyze_stability(soliton)

    def compute_topological_charge(self, soliton: np.ndarray) -> float:
        """
        Compute topological charge of soliton via 7D U(1)^3 phase winding.

        Physical Meaning:
            Calculates the baryon number B via U(1)^3 winding over φ-coordinates
            which represents the topological charge of the soliton in 7D phase
            field theory.

        Mathematical Foundation:
            B = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ) for 7D phase field Θ(x,φ) ∈ T^3_φ
            The classical SU(3) form B = (1/24π²)∫ε^μνρσTr(L_ν L_ρ L_σ) is a
            4D pedagogical limit, not the core 7D construction.

        Args:
            soliton: Soliton field configuration

        Returns:
            Topological charge (baryon number)
        """
        if soliton.ndim < 7:
            return 0.0

        # For 7D phase field Θ(x,φ,t), compute U(1)^3 winding over φ-coordinates
        # B = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ)

        # Extract phase coordinates (last 3 dimensions are φ-coordinates)
        if soliton.shape[-3:] != (8, 8, 8):  # Assuming 8x8x8 φ-grid
            return 0.0

        # Compute phase gradients along φ-coordinates
        dphi = 2 * np.pi / 8  # Phase coordinate spacing
        phase_gradients = []
        for i in range(3):
            axis = -3 + i  # φ-coordinate axes
            if soliton.shape[axis] > 1:
                grad = np.gradient(soliton, dphi, axis=axis)
                phase_gradients.append(grad)
            else:
                phase_gradients.append(np.zeros_like(soliton))

        # Compute U(1)^3 winding integral
        # For each spatial point x, integrate ∇_φ·Θ over T³_φ
        charge_density = 0.0
        for i in range(soliton.shape[0]):  # x-coordinates
            for j in range(soliton.shape[1]):
                for k in range(soliton.shape[2]):
                    # Extract phase field at spatial point (i,j,k)
                    phase_field = soliton[i, j, k, :, :, :]

                    # Compute phase gradients at this spatial point
                    phase_grads = [grad[i, j, k, :, :, :] for grad in phase_gradients]

                    # Compute winding integral over T³_φ
                    # B = (1/8π²)∫_T³_φ dφ₁dφ₂dφ₃ ∇_φ·Θ(x,φ)
                    winding_integral = 0.0
                    for phi1 in range(8):
                        for phi2 in range(8):
                            for phi3 in range(8):
                                # Compute divergence ∇_φ·Θ
                                div_phi = (
                                    phase_grads[0][phi1, phi2, phi3]
                                    + phase_grads[1][phi1, phi2, phi3]
                                    + phase_grads[2][phi1, phi2, phi3]
                                )
                                winding_integral += div_phi

                    charge_density += winding_integral

        return float(charge_density / (8 * np.pi**2))
