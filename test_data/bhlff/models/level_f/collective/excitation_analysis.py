"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Excitation analysis for collective excitations.

This module implements excitation analysis functionality for
collective excitations in multi-particle systems.

Theoretical Background:
    Excitation analysis involves applying external fields
    to the system and analyzing the response to identify
    collective modes and their properties.

Example:
    >>> analyzer = ExcitationAnalyzer(system, excitation_params)
    >>> response = analyzer.excite_system(external_field)
    >>> analysis = analyzer.analyze_response(response)
"""

import numpy as np
from typing import Dict, Any, Optional, Tuple
from bhlff.models.base.abstract_model import AbstractModel


class ExcitationAnalyzer(AbstractModel):
    """
    Excitation analysis for collective excitations.

    Physical Meaning:
        Analyzes the response of multi-particle systems to
        external excitations, identifying collective modes
        and their properties.

    Mathematical Foundation:
        Implements excitation analysis using linear response
        theory for collective excitations.

    Attributes:
        system: Multi-particle system
        excitation_params: Excitation parameters
        frequency_range: Frequency range for analysis
        amplitude: Excitation amplitude
        excitation_type: Type of excitation
    """

    def __init__(
        self, system: "MultiParticleSystem", excitation_params: Dict[str, Any]
    ):
        """
        Initialize excitation analyzer.

        Physical Meaning:
            Sets up the excitation analyzer for studying
            collective excitations in the multi-particle system.

        Args:
            system (MultiParticleSystem): Multi-particle system
            excitation_params (Dict[str, Any]): Excitation parameters
        """
        super().__init__(system.domain)
        self.system = system
        self.excitation_params = excitation_params

        # Extract parameters
        self.frequency_range = excitation_params.get("frequency_range", [0.1, 10.0])
        self.amplitude = excitation_params.get("amplitude", 0.1)
        self.excitation_type = excitation_params.get("type", "harmonic")
        self.duration = excitation_params.get("duration", 100.0)

        # Setup analysis parameters
        self._setup_analysis_parameters()

    def excite_system(self, external_field: np.ndarray) -> np.ndarray:
        """
        Excite the system with external field.

        Physical Meaning:
            Applies external field to the system and
            computes the response.

        Args:
            external_field (np.ndarray): External field F(x,t)

        Returns:
            np.ndarray: System response R(x,t)
        """
        if self.excitation_type == "harmonic":
            return self._harmonic_excitation(external_field)
        elif self.excitation_type == "impulse":
            return self._impulse_excitation(external_field)
        elif self.excitation_type == "sweep":
            return self._frequency_sweep_excitation(external_field)
        else:
            raise ValueError(f"Unknown excitation type: {self.excitation_type}")

    def analyze_response(self, response: np.ndarray) -> Dict[str, Any]:
        """
        Analyze system response to excitation.

        Physical Meaning:
            Extracts collective mode frequencies and
            amplitudes from the response.

        Args:
            response (np.ndarray): System response R(x,t)

        Returns:
            Dict containing:
                - frequencies: ω_n (collective frequencies)
                - amplitudes: A_n (mode amplitudes)
                - damping: γ_n (damping rates)
                - participation: p_n (particle participation)
        """
        # FFT analysis
        response_fft = np.fft.fft(response, axis=-1)
        frequencies = np.fft.fftfreq(response.shape[-1], self.dt)

        # Find spectral peaks
        peaks = self._find_spectral_peaks(np.abs(response_fft), frequencies)

        # Analyze step resonator transmission
        transmission_analysis = self._analyze_step_resonator_transmission(response)

        # Compute participation ratios
        participation = self._compute_participation_ratios(response)

        # Quality factors
        quality_factors = self._compute_quality_factors(peaks, transmission_analysis)

        return {
            "frequencies": frequencies,
            "peaks": peaks,
            "transmission_analysis": transmission_analysis,
            "participation": participation,
            "quality_factors": quality_factors,
            "spectrum": response_fft,
        }

    def _setup_analysis_parameters(self) -> None:
        """
        Setup analysis parameters for collective excitations.

        Physical Meaning:
            Initializes parameters needed for analysis
            of collective excitations.
        """
        self.dt = 0.01  # Time step
        self.peak_threshold = 0.1  # Peak detection threshold
        self.damping_threshold = 0.01  # Damping analysis threshold

    def _harmonic_excitation(self, external_field: np.ndarray) -> np.ndarray:
        """
        Apply harmonic excitation to the system.

        Physical Meaning:
            Applies harmonic external field and computes
            the steady-state response.
        """
        # Time array
        t = np.arange(0, self.duration, self.dt)

        # Harmonic excitation
        omega = np.mean(self.frequency_range)
        excitation = self.amplitude * np.sin(2 * np.pi * omega * t)

        # Apply to system
        response = self._apply_excitation(external_field, excitation)

        return response

    def _impulse_excitation(self, external_field: np.ndarray) -> np.ndarray:
        """
        Apply impulse excitation to the system.

        Physical Meaning:
            Applies impulse external field and computes
            the transient response.
        """
        # Time array
        t = np.arange(0, self.duration, self.dt)

        # Impulse excitation
        impulse_duration = 0.1
        excitation = np.zeros_like(t)
        mask = t < impulse_duration
        excitation[mask] = self.amplitude

        # Apply to system
        response = self._apply_excitation(external_field, excitation)

        return response

    def _frequency_sweep_excitation(self, external_field: np.ndarray) -> np.ndarray:
        """
        Apply frequency sweep excitation to the system.

        Physical Meaning:
            Applies frequency sweep external field and
            computes the response across frequency range.
        """
        # Time array
        t = np.arange(0, self.duration, self.dt)

        # Frequency sweep
        omega_start, omega_end = self.frequency_range
        omega_t = omega_start + (omega_end - omega_start) * t / self.duration

        # Sweep excitation
        excitation = self.amplitude * np.sin(2 * np.pi * omega_t * t)

        # Apply to system
        response = self._apply_excitation(external_field, excitation)

        return response

    def _apply_excitation(
        self, external_field: np.ndarray, excitation: np.ndarray
    ) -> np.ndarray:
        """
        Apply excitation to the system and compute response.

        Physical Meaning:
            Applies the external excitation to the system
            and computes the resulting response.
        """
        # Get system dynamics
        dynamics_matrix = self.system._compute_dynamics_matrix()

        # Initialize response
        n_particles = len(self.system.particles)
        response = np.zeros((n_particles, len(excitation)))

        # Time integration
        for i, t in enumerate(np.arange(0, self.duration, self.dt)):
            if i == 0:
                continue

            # External force
            F = self._compute_external_force(external_field, excitation[i])

            # Solve dynamics equation
            # M ẍ + K x = F
            # This is simplified - in practice would use proper time integration
            try:
                response[:, i] = np.linalg.solve(dynamics_matrix, F)
            except np.linalg.LinAlgError:
                # Use pseudo-inverse if matrix is singular
                response[:, i] = np.linalg.pinv(dynamics_matrix) @ F

        return response

    def analyze(self, data: Any) -> Dict[str, Any]:
        """
        Analyze given external field by exciting the system and parsing response.

        Args:
            data (Any): External field array used to excite the system.

        Returns:
            Dict[str, Any]: Analysis including spectrum, peaks, participation, Q.
        """
        self.log_analysis_start("collective_excitations")
        external_field = data
        response = self.excite_system(external_field)
        results = self.analyze_response(response)
        self.log_analysis_complete("collective_excitations", results)
        return results

    def _compute_external_force(
        self, external_field: np.ndarray, excitation_amplitude: float
    ) -> np.ndarray:
        """
        Compute external force on particles.

        Physical Meaning:
            Calculates the external force acting
            on each particle due to the external field.
        """
        n_particles = len(self.system.particles)
        forces = np.zeros(n_particles)

        for i, particle in enumerate(self.system.particles):
            # Force from external field at particle position
            # This is simplified - in practice would interpolate field
            # Handle different field dimensions
            if external_field.ndim == 3:
                force = external_field[0, 0, 0] * excitation_amplitude * particle.charge
            elif external_field.ndim == 7:
                force = (
                    external_field[0, 0, 0, 0, 0, 0, 0]
                    * excitation_amplitude
                    * particle.charge
                )
            else:
                # Use mean value for other dimensions
                force = np.mean(external_field) * excitation_amplitude * particle.charge
            forces[i] = force

        return forces

    def _find_spectral_peaks(
        self, spectrum: np.ndarray, frequencies: np.ndarray
    ) -> Dict[str, Any]:
        """
        Find spectral peaks in the response.

        Physical Meaning:
            Identifies resonant frequencies in the
            system response spectrum.
        """
        # Find peaks above threshold
        peak_indices = []
        peak_frequencies = []
        peak_amplitudes = []

        for i in range(1, len(spectrum) - 1):
            if (
                spectrum[i] > spectrum[i - 1]
                and spectrum[i] > spectrum[i + 1]
                and spectrum[i] > self.peak_threshold
            ):
                peak_indices.append(i)
                peak_frequencies.append(frequencies[i])
                peak_amplitudes.append(spectrum[i])

        return {
            "indices": peak_indices,
            "frequencies": peak_frequencies,
            "amplitudes": peak_amplitudes,
        }

    def _analyze_step_resonator_transmission(
        self, response: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze energy exchange through step resonator boundaries.

        Physical Meaning:
            Computes transmission/reflection coefficients for collective modes
            through semi-transparent step resonator boundaries using frequency-dependent
            step resonator model.
        """
        # Initialize frequency-dependent resonator if not exists
        if not hasattr(self, "_resonator"):
            from bhlff.core.bvp.boundary.step_resonator import (
                FrequencyDependentResonator,
            )

            self._resonator = FrequencyDependentResonator(R0=0.1, T0=0.9, omega0=1.0)

        # Analyze boundary transmission/reflection using step resonator model
        transmission_coeffs = []
        reflection_coeffs = []

        for i in range(response.shape[0]):
            # Compute frequency content of the response
            field_frequencies = np.abs(response[i, :])

            # Apply step resonator model
            R, T = self._resonator.compute_coefficients(field_frequencies)

            # Compute boundary energy flux using resonator coefficients
            boundary_flux = self._compute_boundary_energy_flux(response[i, :])

            # Apply resonator filtering
            transmission_coeffs.append(np.mean(T) * boundary_flux["transmission"])
            reflection_coeffs.append(np.mean(R) * boundary_flux["reflection"])

        return {
            "transmission_coefficients": transmission_coeffs,
            "reflection_coefficients": reflection_coeffs,
            "mean_transmission": np.mean(transmission_coeffs),
            "mean_reflection": np.mean(reflection_coeffs),
            "resonator_model": "step_resonator",
            "frequency_dependent": True,
        }

    def _compute_boundary_energy_flux(self, field: np.ndarray) -> Dict[str, float]:
        """
        Compute energy flux through step resonator boundaries.

        Physical Meaning:
            Calculates energy exchange through semi-transparent
            step resonator boundaries using 7D BVP theory.
        """
        # For 1D time series, simulate step resonator behavior
        # by applying simple transmission/reflection coefficients

        # Simple step resonator simulation for 1D field
        R = 0.1  # Reflection coefficient
        T = 0.9  # Transmission coefficient

        # Apply boundary conditions to first and last points
        if len(field) > 1:
            # Simulate boundary effects
            transmitted_field = field.copy()
            transmitted_field[0] = (
                R * field[0] + T * field[1] if len(field) > 1 else field[0]
            )
            transmitted_field[-1] = (
                R * field[-1] + T * field[-2] if len(field) > 1 else field[-1]
            )
        else:
            transmitted_field = field.copy()

        # Compute transmission/reflection coefficients
        incident_energy = np.sum(np.abs(field) ** 2)
        transmitted_energy = np.sum(np.abs(transmitted_field) ** 2)

        transmission = transmitted_energy / (incident_energy + 1e-10)
        reflection = 1.0 - transmission

        return {"transmission": transmission, "reflection": reflection}

    def _compute_participation_ratios(self, response: np.ndarray) -> np.ndarray:
        """
        Compute participation ratios for collective modes.

        Physical Meaning:
            Calculates how much each particle participates
            in the collective response.
        """
        # Compute participation from response amplitudes
        participation = np.zeros(response.shape[0])

        for i in range(response.shape[0]):
            # Participation based on response amplitude
            response_amplitude = np.max(np.abs(response[i, :]))
            participation[i] = response_amplitude

        # Normalize
        if np.sum(participation) > 0:
            participation = participation / np.sum(participation)

        return participation

    def _compute_quality_factors(
        self, peaks: Dict[str, Any], transmission_analysis: Dict[str, Any]
    ) -> np.ndarray:
        """
        Compute quality factors for collective modes.

        Physical Meaning:
            Calculates quality factors based on transmission
            coefficients through step resonator boundaries.
        """
        peak_frequencies = peaks["frequencies"]
        transmission_coeffs = transmission_analysis["transmission_coefficients"]

        quality_factors = []
        for freq in peak_frequencies:
            # Use transmission coefficient as quality measure
            if transmission_coeffs:
                transmission = np.mean(transmission_coeffs)
                # Higher transmission = higher quality
                Q = transmission * freq if transmission > 0 else 0
            else:
                Q = 0
            quality_factors.append(Q)

        return np.array(quality_factors)
