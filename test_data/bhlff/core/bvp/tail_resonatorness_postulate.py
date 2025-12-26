"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Tail Resonatorness Postulate implementation for BVP framework.

This module implements Postulate 6 of the BVP framework, which states that
the tail is a cascade of effective resonators/transmission lines with
frequency-dependent impedance.

Theoretical Background:
    The tail exhibits resonator-like behavior with resonance peaks {ω_n,Q_n}
    determined by BVP field characteristics and boundary conditions. This
    postulate validates the resonator cascade model of particle tails.

Example:
    >>> postulate = TailResonatornessPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any, List
from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate


class TailResonatornessPostulate(BVPPostulate):
    """
    Postulate 6: Tail Resonatorness.

    Physical Meaning:
        Tail is cascade of effective resonators/transmission lines
        with frequency-dependent impedance; spectrum {ω_n,Q_n} is
        determined by BVP and boundaries.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize tail resonatorness postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            analyzing resonator-like behavior in particle tails.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.resonance_threshold = constants.get_quench_parameter("resonance_threshold")
        self.quality_factor_threshold = constants.get_quench_parameter(
            "quality_factor_threshold"
        )

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply tail resonatorness postulate.

        Physical Meaning:
            Verifies that the tail exhibits resonator-like behavior
            with frequency-dependent impedance and resonance peaks.

        Mathematical Foundation:
            Analyzes the frequency spectrum to identify resonance
            peaks {ω_n,Q_n} and verifies impedance characteristics.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including resonance frequencies,
                quality factors, and impedance characteristics.
        """
        # Compute frequency spectrum
        spectrum = self._compute_frequency_spectrum(envelope)

        # Find resonance peaks
        resonance_peaks = self._find_resonance_peaks(spectrum)

        # Compute quality factors
        quality_factors = self._compute_quality_factors(resonance_peaks, spectrum)

        # Analyze impedance characteristics
        impedance_analysis = self._analyze_impedance_characteristics(envelope)

        # Validate resonatorness
        is_resonator_like = self._validate_resonatorness(
            resonance_peaks, quality_factors
        )

        return {
            "resonance_frequencies": resonance_peaks,
            "quality_factors": quality_factors,
            "impedance_analysis": impedance_analysis,
            "is_resonator_like": is_resonator_like,
            "postulate_satisfied": is_resonator_like,
        }

    def _compute_frequency_spectrum(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute frequency spectrum of the envelope.

        Physical Meaning:
            Performs FFT in temporal dimension to obtain frequency
            spectrum for resonance analysis.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            np.ndarray: Frequency spectrum magnitude.
        """
        # FFT in temporal dimension
        temporal_fft = np.fft.fft(envelope, axis=6)
        return np.abs(temporal_fft)

    def _find_resonance_peaks(self, spectrum: np.ndarray) -> List[float]:
        """
        Find resonance peaks in the frequency spectrum.

        Physical Meaning:
            Identifies local maxima in frequency spectrum that
            correspond to resonance frequencies.

        Args:
            spectrum (np.ndarray): Frequency spectrum.

        Returns:
            List[float]: List of resonance frequencies.
        """
        # Find local maxima in spectrum
        peaks = []
        for freq_idx in range(1, spectrum.shape[6] - 1):
            # Check if this frequency is a local maximum
            is_local_max = np.all(
                spectrum[..., freq_idx] > spectrum[..., freq_idx - 1]
            ) and np.all(spectrum[..., freq_idx] > spectrum[..., freq_idx + 1])
            if is_local_max:
                # Convert to frequency
                freq = freq_idx * self.domain.dt / (2 * np.pi)
                peaks.append(freq)
        return peaks

    def _compute_quality_factors(
        self, resonance_peaks: List[float], spectrum: np.ndarray
    ) -> List[float]:
        """
        Compute quality factors for resonance peaks.

        Physical Meaning:
            Calculates Q factors from peak width at half maximum,
            indicating resonator quality and energy storage.

        Args:
            resonance_peaks (List[float]): List of resonance frequencies.
            spectrum (np.ndarray): Frequency spectrum.

        Returns:
            List[float]: List of quality factors.
        """
        quality_factors = []
        for peak_freq in resonance_peaks:
            # Find peak width at half maximum
            peak_idx = int(peak_freq * 2 * np.pi / self.domain.dt)
            peak_amplitude = np.max(spectrum[..., peak_idx])
            half_max = peak_amplitude / 2

            # Find width
            left_idx = peak_idx
            right_idx = peak_idx
            while left_idx > 0 and spectrum[..., left_idx] > half_max:
                left_idx -= 1
            while (
                right_idx < spectrum.shape[6] - 1
                and spectrum[..., right_idx] > half_max
            ):
                right_idx += 1

            # Compute Q factor
            width = (right_idx - left_idx) * self.domain.dt
            Q = peak_freq / width if width > 0 else 0
            quality_factors.append(Q)

        return quality_factors

    def _analyze_impedance_characteristics(
        self, envelope: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze impedance characteristics of the tail.

        Physical Meaning:
            Computes admittance and analyzes frequency dependence
            to characterize impedance behavior.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Impedance analysis results.
        """
        # Compute admittance from envelope
        admittance = self._compute_admittance(envelope)

        # Analyze frequency dependence
        freq_dependence = self._analyze_frequency_dependence(admittance)

        return {
            "admittance": admittance,
            "frequency_dependence": freq_dependence,
            "is_frequency_dependent": freq_dependence > self.resonance_threshold,
        }

    def _compute_admittance(self, envelope: np.ndarray) -> np.ndarray:
        """
        Compute admittance from envelope.

        Physical Meaning:
            Calculates admittance using full transmission line theory
            with proper impedance matching and frequency dependence.

        Mathematical Foundation:
            Admittance Y = (1/Z) * (∇A/A) where:
            - Z is frequency-dependent characteristic impedance
            - ∇A is envelope gradient
            - A is envelope amplitude
            - Includes skin effect and dispersion corrections

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            np.ndarray: Admittance field.
        """
        amplitude = np.abs(envelope)

        # Compute spatial gradient of envelope amplitude
        gradient = np.gradient(amplitude, self.domain.dx, axis=0)

        # Get material properties for transmission line calculations
        vacuum_permeability = self.constants.get_physical_constant(
            "vacuum_permeability"
        )
        vacuum_permittivity = self.constants.get_physical_constant(
            "vacuum_permittivity"
        )
        em_conductivity = self.constants.get_material_property("em_conductivity")

        # Compute frequency-dependent characteristic impedance
        # Z = √(μ/ε) * (1 + jσ/(ωε))^(-1/2) for lossy transmission line
        carrier_frequency = self.constants.get_physical_parameter("carrier_frequency")
        omega = 2 * np.pi * carrier_frequency

        # Lossy transmission line impedance with skin effect
        z0_base = np.sqrt(vacuum_permeability / vacuum_permittivity)
        loss_factor = 1.0 + 1j * em_conductivity / (omega * vacuum_permittivity)
        z_characteristic = z0_base / np.sqrt(loss_factor)

        # Compute admittance using full transmission line theory
        # Y = (1/Z) * (∇A/A) with frequency-dependent corrections
        admittance = gradient / (z_characteristic * (amplitude + 1e-12))

        # Apply skin effect correction for high frequencies
        skin_depth = np.sqrt(2 / (omega * vacuum_permeability * em_conductivity))
        skin_correction = np.exp(-1j * self.domain.dx / skin_depth)
        admittance = admittance * skin_correction

        return admittance

    def _analyze_frequency_dependence(self, admittance: np.ndarray) -> float:
        """
        Analyze frequency dependence of admittance.

        Physical Meaning:
            Computes variance across frequency domain to quantify
            frequency dependence of impedance.

        Args:
            admittance (np.ndarray): Admittance field.

        Returns:
            float: Frequency dependence measure.
        """
        # Compute variance across frequency domain
        freq_variance = np.var(admittance, axis=6)
        return np.mean(freq_variance)

    def _validate_resonatorness(
        self, resonance_peaks: List[float], quality_factors: List[float]
    ) -> bool:
        """
        Validate that the tail exhibits resonator-like behavior.

        Physical Meaning:
            Checks for sufficient number of resonances and adequate
            quality factors to confirm resonator behavior.

        Args:
            resonance_peaks (List[float]): List of resonance frequencies.
            quality_factors (List[float]): List of quality factors.

        Returns:
            bool: True if resonator-like behavior is confirmed.
        """
        # Check for sufficient number of resonances
        if len(resonance_peaks) < 2:
            return False

        # Check quality factors
        high_q_count = sum(
            1 for Q in quality_factors if Q > self.quality_factor_threshold
        )
        return high_q_count >= len(quality_factors) * 0.5
