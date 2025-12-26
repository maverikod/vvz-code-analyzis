"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Abstract base class for BHLFF solvers.

This module defines the abstract base class for all solvers in the BHLFF
framework, providing common interfaces and functionality for solving
phase field equations in 7D space-time.

Physical Meaning:
    Abstract solvers provide the fundamental interface for solving
    phase field equations, including the fractional Riesz operator
    and related equations governing phase field dynamics.

Mathematical Foundation:
    All solvers implement methods for solving equations of the form
    L_β a = s(x) where L_β is the fractional Riesz operator and s(x)
    is a source term.
"""

from abc import ABC, abstractmethod

# No additional typing imports needed
import numpy as np

from ...core.domain import Domain
from ...core.domain import Parameters


class AbstractSolver(ABC):
    """
    Abstract base class for BHLFF solvers.

    Physical Meaning:
        Provides the fundamental interface for all solvers in the BHLFF
        framework, ensuring consistent behavior across different numerical
        methods and physical regimes.

    Mathematical Foundation:
        All solvers implement methods for solving the fractional Riesz
        operator L_β a = μ(-Δ)^β a + λa = s(x) and related equations.

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _initialized (bool): Initialization status.
    """

    def __init__(self, domain: Domain, parameters: Parameters) -> None:
        """
        Initialize abstract solver.

        Physical Meaning:
            Sets up the solver with computational domain and physics
            parameters, preparing for numerical solution of phase field
            equations.

        Args:
            domain (Domain): Computational domain for the simulation.
            parameters (Parameters): Physics parameters controlling
                the behavior of the phase field system.
        """
        self.domain = domain
        self.parameters = parameters
        self._initialized = False

    @abstractmethod
    def solve(self, source: np.ndarray) -> np.ndarray:
        """
        Solve the phase field equation for given source.

        Physical Meaning:
            Computes the phase field configuration that satisfies
            the governing equation with the given source term,
            representing the response of the phase field to external
            excitations or initial conditions.

        Mathematical Foundation:
            Solves L_β a = s(x) where L_β is the fractional Riesz
            operator and s(x) is the source term.

        Args:
            source (np.ndarray): Source term s(x) in real space.
                Represents external excitations or initial conditions
                that drive the phase field evolution.

        Returns:
            np.ndarray: Solution field a(x) in real space.
                Represents the phase field configuration that
                satisfies the equation.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement solve method")

    @abstractmethod
    def solve_time_evolution(
        self,
        initial_field: np.ndarray,
        source: np.ndarray,
        time_steps: int,
        dt: float,
    ) -> np.ndarray:
        """
        Solve time evolution of the phase field.

        Physical Meaning:
            Computes the time evolution of the phase field from initial
            conditions under the influence of a time-dependent source,
            representing the dynamic response of the phase field system.

        Mathematical Foundation:
            Solves ∂_t a + ν(-Δ)^β a + λa = s(x,t) with initial
            condition a(x,0) = initial_field.

        Args:
            initial_field (np.ndarray): Initial field configuration a(x,0).
            source (np.ndarray): Time-dependent source term s(x,t).
            time_steps (int): Number of time steps to compute.
            dt (float): Time step size.

        Returns:
            np.ndarray: Time evolution of the field a(x,t).

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError(
            "Subclasses must implement solve_time_evolution method"
        )

    def validate_input(self, field: np.ndarray, name: str = "field") -> None:
        """
        Validate input field shape and properties.

        Physical Meaning:
            Ensures that input fields have the correct shape and properties
            for the computational domain, preventing numerical errors and
            ensuring physical consistency.

        Args:
            field (np.ndarray): Field to validate.
            name (str): Name of the field for error messages.

        Raises:
            ValueError: If field shape is incompatible with domain.
        """
        if field.shape != self.domain.shape:
            raise ValueError(
                f"{name} shape {field.shape} incompatible with "
                f"domain shape {self.domain.shape}"
            )

    def compute_residual(self, field: np.ndarray, source: np.ndarray) -> np.ndarray:
        """
        Compute residual of the governing equation.

        Physical Meaning:
            Computes the residual r = L_β a - s to measure how well
            the field satisfies the governing equation, used for
            convergence checking and error analysis.

        Mathematical Foundation:
            Residual is r = L_β a - s where L_β is the fractional
            Riesz operator applied to the field a.

        Args:
            field (np.ndarray): Field configuration a(x).
            source (np.ndarray): Source term s(x).

        Returns:
            np.ndarray: Residual r = L_β a - s.
        """
        # Compute the fractional Riesz operator L_β a using unified backend
        from bhlff.core.fft.unified_spectral_operations import UnifiedSpectralOperations

        spectral_ops = UnifiedSpectralOperations(self.domain, precision="float64")
        field_spectral = spectral_ops.forward_fft(field, normalization="physics")

        # Get 7D wave vectors for BVP theory
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kphi1 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi2 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi3 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kt = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)

        # Create 7D meshgrids
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
        )

        # Compute 7D wave vector magnitude
        k_magnitude = np.sqrt(
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )

        # Apply fractional Laplacian in spectral space
        # L_β a = μ(-Δ)^β a + λa
        spectral_coeffs = self.parameters.get_spectral_coefficients(k_magnitude)
        operator_field_spectral = spectral_coeffs * field_spectral

        # Transform back to real space
        operator_field = spectral_ops.inverse_fft(
            operator_field_spectral, normalization="physics"
        ).real

        # Compute residual r = L_β a - s
        residual = operator_field - source

        return residual

    def get_energy(self, field: np.ndarray) -> float:
        """
        Compute energy of the field configuration.

        Physical Meaning:
            Computes the total energy of the field configuration,
            representing the energy content of the phase field
            system in the current state.

        Mathematical Foundation:
            Energy is E = ½(μ⟨a,(-Δ)^β a⟩ + λ|∇a|²) - ℜ⟨s,a⟩
            for the fractional Riesz operator according to 7D BVP theory.

        Args:
            field (np.ndarray): Field configuration a(x).

        Returns:
            float: Total energy of the field configuration.
        """
        # Compute energy using the fractional Riesz operator
        # E = ½(μ⟨a,(-Δ)^β a⟩ + λ|∇a|²) - ℜ⟨s,a⟩ according to 7D BVP theory

        # Transform field to spectral space via unified backend
        from bhlff.core.fft.unified_spectral_operations import UnifiedSpectralOperations

        spectral_ops = UnifiedSpectralOperations(self.domain, precision="float64")
        field_spectral = spectral_ops.forward_fft(field, normalization="physics")

        # Get 7D wave vectors for BVP theory
        kx = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        ky = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kz = np.fft.fftfreq(self.domain.N, self.domain.L / self.domain.N)
        kphi1 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi2 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kphi3 = np.fft.fftfreq(self.domain.N_phi, 2 * np.pi / self.domain.N_phi)
        kt = np.fft.fftfreq(self.domain.N_t, self.domain.T / self.domain.N_t)

        # Create 7D meshgrids
        KX, KY, KZ, KPHI1, KPHI2, KPHI3, KT = np.meshgrid(
            kx, ky, kz, kphi1, kphi2, kphi3, kt, indexing="ij"
        )

        # Compute 7D wave vector magnitude
        k_magnitude = np.sqrt(
            KX**2 + KY**2 + KZ**2 + KPHI1**2 + KPHI2**2 + KPHI3**2 + KT**2
        )

        # Compute fractional Laplacian in spectral space
        # (-Δ)^β a in spectral space is |k|^(2β) * â(k)
        fractional_laplacian_spectral = (
            k_magnitude ** (2 * self.parameters.beta)
        ) * field_spectral

        # Transform back to real space
        fractional_laplacian_field = spectral_ops.inverse_fft(
            fractional_laplacian_spectral, normalization="physics"
        ).real

        # Compute energy terms according to 7D BVP theory
        # μ⟨a,(-Δ)^β a⟩ = μ * ∫ a(x) * (-Δ)^β a(x) dx
        kinetic_energy = self.parameters.mu * np.sum(field * fractional_laplacian_field)

        # No mass term λ⟨a,a⟩ - replaced with derivative terms according to 7D theory
        # Compute gradient-based potential energy instead
        field_gradient = np.gradient(field)
        gradient_energy = np.sum(np.array([np.sum(g**2) for g in field_gradient]))
        potential_energy = self.parameters.lambda_param * gradient_energy

        # Total energy E = ½(μ⟨a,(-Δ)^β a⟩ + λ|∇a|²)
        total_energy = 0.5 * (kinetic_energy + potential_energy)

        return float(total_energy)

    def is_initialized(self) -> bool:
        """
        Check if solver is initialized.

        Physical Meaning:
            Returns whether the solver has been properly initialized
            and is ready for computations.

        Returns:
            bool: True if solver is initialized, False otherwise.
        """
        return self._initialized

    def __repr__(self) -> str:
        """String representation of the solver."""
        return (
            f"{self.__class__.__name__}(domain={self.domain}, "
            f"parameters={self.parameters})"
        )
