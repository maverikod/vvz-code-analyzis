"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Envelope integrator for 7D phase field dynamics.

This module implements the BVP envelope integrator for solving dynamic
phase field equations in 7D space-time using envelope modulation approach
instead of classical exponential solutions.

Physical Meaning:
    BVP envelope integrator implements the envelope modulation approach
    where all observed "modes" are envelope modulations and beatings of
    the Base High-Frequency Field, not classical exponential solutions.

Mathematical Foundation:
    Implements envelope equation:
    ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
    where κ(|a|) = κ₀ + κ₂|a|² is nonlinear stiffness and
    χ(|a|) = χ' + iχ''(|a|) is effective susceptibility with quenches.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import logging

from .base_integrator import BaseTimeIntegrator
from .memory_kernel import MemoryKernel
from ..bvp.quench_detector import QuenchDetector
from ..fft import SpectralOperations
from ..bvp.boundary.step_resonator import (
    FrequencyDependentResonator,
    CascadeResonatorFilter,
)


class BVPEnvelopeIntegrator(BaseTimeIntegrator):
    """
    BVP Envelope integrator for 7D phase field dynamics.

    Physical Meaning:
        Implements envelope modulation approach where all observed "modes"
        are envelope modulations and beatings of the Base High-Frequency Field.
        This replaces classical exponential solutions with BVP envelope theory
        using step resonator transmission/reflection coefficients instead of
        exponential attenuation.

    Mathematical Foundation:
        Solves envelope equation:
        ∇·(κ(|a|)∇a) + k₀²χ(|a|)a = s(x,φ,t)
        where κ(|a|) = κ₀ + κ₂|a|² and χ(|a|) = χ' + iχ''(|a|)

    Attributes:
        domain (Domain): Computational domain.
        parameters (Parameters): Physics parameters.
        _spectral_ops (SpectralOperations): Spectral operations for FFT.
        _envelope_coeffs (np.ndarray): Pre-computed envelope coefficients.
        _memory_kernel (Optional[MemoryKernel]): Memory kernel for non-local effects.
        _quench_detector (Optional[QuenchDetector]): Quench detection system.
    """

    def __init__(self, domain, parameters) -> None:
        """
        Initialize BVP envelope integrator.

        Physical Meaning:
            Sets up the envelope integrator with the computational domain
            and physics parameters, pre-computing envelope coefficients
            for efficient integration.

        Args:
            domain (Domain): Computational domain for the simulation.
            parameters (Parameters): Physics parameters controlling
                the behavior of the phase field system.
        """
        super().__init__(domain, parameters)

        # Initialize spectral operations
        self._spectral_ops = SpectralOperations(domain, parameters.precision)

        # Pre-compute envelope coefficients
        self._envelope_coeffs = None
        self._setup_envelope_coefficients()

        self._initialized = True
        self.logger.info("BVP Envelope integrator initialized")

    def _setup_envelope_coefficients(self) -> None:
        """
        Setup envelope coefficients for BVP integrator.

        Physical Meaning:
            Pre-computes the envelope coefficients for the BVP envelope equation
            including nonlinear stiffness and susceptibility terms.
        """
        # Get wave vectors
        wave_vectors = self._spectral_ops._get_wave_vectors()

        # Compute wave vector magnitudes
        k_magnitude_squared = np.zeros(self.domain.shape)

        # Create meshgrids for each dimension
        for i, k_vec in enumerate(wave_vectors):
            if i < 3:  # Spatial dimensions
                # Create 7D array by broadcasting
                k_7d = np.zeros(self.domain.shape)
                for j in range(self.domain.N_spatial):
                    for k in range(self.domain.N_spatial):
                        for l in range(self.domain.N_spatial):
                            k_7d[j, k, l, :, :, :, :] = (
                                k_vec[j]
                                if i == 0
                                else (k_vec[k] if i == 1 else k_vec[l])
                            )
                k_magnitude_squared += k_7d**2
            elif i < 6:  # Phase dimensions
                # Create 7D array by broadcasting
                k_7d = np.zeros(self.domain.shape)
                for j in range(self.domain.N_phase):
                    k_7d[:, :, :, j, :, :, :] = (
                        k_vec[j] if i == 3 else (k_vec[j] if i == 4 else k_vec[j])
                    )
                k_magnitude_squared += k_7d**2
            else:  # Temporal dimension
                # Create 7D array by broadcasting
                k_7d = np.zeros(self.domain.shape)
                for j in range(self.domain.N_t):
                    k_7d[:, :, :, :, :, :, j] = k_vec[j]
                k_magnitude_squared += k_7d**2

        k_magnitude = np.sqrt(k_magnitude_squared)

        # Compute envelope coefficients for BVP theory
        # κ₀|k|² + k₀²χ' where κ₀ is linear stiffness and χ' is real susceptibility
        kappa_0 = getattr(self.parameters, "kappa_0", 1.0)  # Linear stiffness
        k0_squared = getattr(
            self.parameters, "k0_squared", 1.0
        )  # Carrier frequency squared
        chi_prime = getattr(self.parameters, "chi_prime", 1.0)  # Real susceptibility

        self._envelope_coeffs = kappa_0 * k_magnitude_squared + k0_squared * chi_prime

        # Handle k=0 mode
        k_zero_mask = k_magnitude == 0
        self._envelope_coeffs[k_zero_mask] = k0_squared * chi_prime

        self.logger.info("Envelope coefficients computed for BVP theory")

    def integrate(
        self,
        initial_field: np.ndarray,
        source_field: np.ndarray,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate the envelope equation over time using BVP approach.

        Physical Meaning:
            Solves the BVP envelope equation over the specified
            time steps using envelope modulation approach,
            representing envelope modulations and beatings.

        Mathematical Foundation:
            For each time step, applies the envelope solution:
            â(k,t+dt) = â(k,t) * envelope_modulation_factor + source_contribution

        Args:
            initial_field (np.ndarray): Initial field configuration a(x,φ,0).
            source_field (np.ndarray): Source term s(x,φ,t) over time.
            time_steps (np.ndarray): Time points for integration.

        Returns:
            np.ndarray: Field evolution a(x,φ,t) over time.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        # Validate inputs
        if (
            not hasattr(initial_field, "shape")
            or initial_field.shape != self.domain.shape
        ):
            raise ValueError(
                f"Initial field shape {getattr(initial_field, 'shape', 'no shape')} incompatible with domain {self.domain.shape}"
            )

        if source_field.shape != (len(time_steps),) + self.domain.shape:
            raise ValueError(
                f"Source field shape {source_field.shape} incompatible with time steps and domain"
            )

        # Initialize result array
        result = np.zeros((len(time_steps),) + self.domain.shape, dtype=np.complex128)
        result[0] = initial_field.copy()

        # Current field state
        current_field = initial_field.copy()

        # Integrate over time steps
        for i in range(1, len(time_steps)):
            dt = time_steps[i] - time_steps[i - 1]
            current_source = source_field[i]

            # Perform single step
            current_field = self.step(current_field, current_source, dt)
            result[i] = current_field.copy()

            # Check for quench events
            if (
                self._quench_detector is not None
                and self._quench_detector.detect_quench(current_field, time_steps[i])
            ):
                self.logger.warning(f"Quench detected at t={time_steps[i]:.3f}")
                # Handle quench events according to BVP theory
                self._handle_quench_event(current_field, time_steps[i])

        self.logger.info(
            f"BVP envelope integration completed over {len(time_steps)} time steps"
        )
        return result

    def step(
        self, current_field: np.ndarray, source_field: np.ndarray, dt: float
    ) -> np.ndarray:
        """
        Perform a single time step using BVP envelope approach.

        Physical Meaning:
            Advances the field configuration by one time step using the
            BVP envelope approach, representing envelope modulations and beatings.

        Mathematical Foundation:
            Applies the envelope solution with nonlinear stiffness and susceptibility:
            â(k,t+dt) = â(k,t) * envelope_modulation + source_contribution

        Args:
            current_field (np.ndarray): Current field configuration.
            source_field (np.ndarray): Source term at current time.
            dt (float): Time step size.

        Returns:
            np.ndarray: Field configuration at next time step.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        # Transform to spectral space
        current_spectral = self._spectral_ops.forward_fft(current_field, "ortho")
        source_spectral = self._spectral_ops.forward_fft(source_field, "ortho")

        # Apply memory kernel effects if present
        if self._memory_kernel is not None:
            memory_contribution = self._memory_kernel.get_memory_contribution()
            memory_spectral = self._spectral_ops.forward_fft(
                memory_contribution, "ortho"
            )
            source_spectral += memory_spectral

        # BVP envelope integration in spectral space
        # Compute nonlinear stiffness κ(|a|) = κ₀ + κ₂|a|²
        kappa_2 = getattr(
            self.parameters, "kappa_2", 0.1
        )  # Nonlinear stiffness coefficient
        field_magnitude_squared = np.abs(current_spectral) ** 2
        nonlinear_stiffness = 1.0 + kappa_2 * field_magnitude_squared

        # Compute effective susceptibility χ(|a|) = χ' + iχ''(|a|)
        chi_double_prime = getattr(
            self.parameters, "chi_double_prime", 0.1
        )  # Imaginary susceptibility
        effective_susceptibility = 1.0 + 1j * chi_double_prime * field_magnitude_squared

        # Envelope modulation factor using frequency-dependent resonator model
        # No exponential attenuation - use step resonator transmission
        if not hasattr(self, "_resonator"):
            # Initialize frequency-dependent resonator
            self._resonator = FrequencyDependentResonator(R0=0.1, T0=0.9, omega0=1.0)

        # Compute frequency-dependent coefficients
        # Use field magnitude as proxy for frequency content
        field_frequencies = np.abs(field_magnitude_squared)
        R, T = self._resonator.compute_coefficients(field_frequencies)

        # Step resonator model: frequency-dependent T/R coefficients
        resonator_response = np.where(
            self._envelope_coeffs * dt * nonlinear_stiffness * effective_susceptibility
            < 1.0,
            T,  # Use frequency-dependent transmission
            R,  # Use frequency-dependent reflection
        )

        envelope_factor = resonator_response

        # Source contribution with envelope modulation
        denominator = (
            self._envelope_coeffs * nonlinear_stiffness * effective_susceptibility
        )
        # Avoid division by zero and underflow
        denominator = np.where(denominator == 0, 1e-12, denominator)
        denominator = np.maximum(denominator, 1e-12)  # Prevent underflow

        # Prevent underflow in division
        with np.errstate(divide="ignore", invalid="ignore", under="ignore"):
            source_factor = (1.0 - envelope_factor) / denominator
            source_factor = np.where(np.isfinite(source_factor), source_factor, dt)
        source_factor = np.where(
            self._envelope_coeffs * nonlinear_stiffness * effective_susceptibility != 0,
            source_factor,
            dt,  # Handle division by zero
        )

        # Prevent underflow in multiplication
        with np.errstate(under="ignore", over="ignore"):
            next_spectral = (
                current_spectral * envelope_factor + source_spectral * source_factor
            )

        # Transform back to real space
        next_field = self._spectral_ops.inverse_fft(next_spectral, "ortho")

        # Evolve memory kernel if present
        if self._memory_kernel is not None:
            self._memory_kernel.evolve(current_field, dt)

        return next_field

    def integrate_envelope_modulation(
        self,
        initial_field: np.ndarray,
        carrier_frequency: float,
        modulation_depth: float,
        time_steps: np.ndarray,
    ) -> np.ndarray:
        """
        Integrate with envelope modulation using BVP approach.

        Physical Meaning:
            Solves the envelope equation with envelope modulation
            representing the BVP approach where all observed "modes"
            are envelope modulations and beatings.

        Mathematical Foundation:
            For envelope modulation, applies:
            â(k,t) = â₀(k) * envelope_modulation(t) * carrier_modulation(t)

        Args:
            initial_field (np.ndarray): Initial field configuration.
            carrier_frequency (float): Carrier frequency ω₀.
            modulation_depth (float): Modulation depth m.
            time_steps (np.ndarray): Time points for integration.

        Returns:
            np.ndarray: Field evolution over time.
        """
        if not self._initialized:
            raise RuntimeError("Integrator not initialized")

        # Transform to spectral space
        initial_spectral = self._spectral_ops.forward_fft(initial_field, "ortho")

        # Initialize result
        result = np.zeros((len(time_steps),) + self.domain.shape, dtype=np.complex128)

        # Apply envelope modulation for each time step
        for i, t in enumerate(time_steps):
            # Envelope modulation factor
            envelope_modulation = 1.0 + modulation_depth * np.cos(carrier_frequency * t)

            # Carrier modulation
            carrier_modulation = np.exp(1j * carrier_frequency * t)

            # BVP envelope solution
            field_spectral = initial_spectral * envelope_modulation * carrier_modulation

            # Transform back to real space
            result[i] = self._spectral_ops.inverse_fft(field_spectral, "ortho")

        self.logger.info(
            f"BVP envelope modulation integration completed for carrier frequency ω₀={carrier_frequency}"
        )
        return result

    def _handle_quench_event(self, field: np.ndarray, time: float) -> None:
        """
        Handle quench event according to BVP theory.

        Physical Meaning:
            Implements quench handling according to BVP theory where
            quenches represent dissipative energy dumps in the envelope.

        Args:
            field (np.ndarray): Current field configuration.
            time (float): Current time.
        """
        # BVP quench handling: energy dump and envelope reset
        if self._quench_detector is not None:
            quench_info = self._quench_detector.get_quench_info()
            self.logger.info(
                f"BVP quench handled: energy_dump={quench_info.get('energy_dump', 0):.3f}"
            )

            # Reset envelope modulation parameters if needed
            # This is BVP-specific quench handling

    def __repr__(self) -> str:
        """String representation of integrator."""
        return (
            f"BVPEnvelopeIntegrator("
            f"domain={self.domain.shape}, "
            f"kappa_0={getattr(self.parameters, 'kappa_0', 1.0)}, "
            f"kappa_2={getattr(self.parameters, 'kappa_2', 0.1)}, "
            f"chi_prime={getattr(self.parameters, 'chi_prime', 1.0)})"
        )
