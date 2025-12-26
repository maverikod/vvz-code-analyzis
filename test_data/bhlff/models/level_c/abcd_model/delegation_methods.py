"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Delegation methods for ABCD model backward compatibility.

This module contains delegation methods that maintain backward compatibility
with the original abcd_model.py interface while delegating to modular components.
"""

import numpy as np
from typing import List, Tuple, Any
from ..abcd import ResonatorLayer


class ABCDDelegationMethods:
    """
    Delegation methods for ABCD model backward compatibility.

    Physical Meaning:
        Provides delegation methods that maintain the original interface
        while delegating to modular components for maintainability.
    """

    def __init__(
        self,
        transmission_computation,
        spectral_poles_analysis,
        admittance_computation,
        quality_factors,
        mode_analysis,
        compute_7d_wave_number,
        compute_resonator_determinants,
        compute_transmission_matrix,
        logger,
    ):
        """
        Initialize delegation methods.

        Args:
            transmission_computation: ABCDTransmissionComputation instance.
            spectral_poles_analysis: ABCDSpectralPolesAnalysis instance.
            admittance_computation: ABCDAdmittanceComputation instance.
            quality_factors: ABCDQualityFactors instance.
            mode_analysis: ABCDModeAnalysis instance.
            compute_7d_wave_number: Method to compute 7D wave number.
            compute_resonator_determinants: Method to compute spectral metrics.
            compute_transmission_matrix: Method to compute transmission matrix.
            logger: Logger instance.
        """
        self._transmission_computation = transmission_computation
        self._spectral_poles_analysis = spectral_poles_analysis
        self._admittance_computation = admittance_computation
        self._quality_factors = quality_factors
        self._mode_analysis = mode_analysis
        self._compute_7d_wave_number = compute_7d_wave_number
        self._compute_resonator_determinants = compute_resonator_determinants
        self._compute_transmission_matrix = compute_transmission_matrix
        self.logger = logger

    def _compute_layer_matrix(
        self,
        layer: ResonatorLayer,
        frequency: float,
        xp: Any = np,
    ) -> np.ndarray:
        """
        Compute transmission matrix for single layer.

        Physical Meaning:
            Computes the 2x2 transmission matrix for a single
            resonator layer at frequency ω, supporting CUDA
            operations for vectorized processing.

        Mathematical Foundation:
            For a layer with thickness Δr and wave number k:
            T = [cos(kΔr)  (1/k)sin(kΔr); -k sin(kΔr)  cos(kΔr)]
            Uses 7D wave number when 7D structure is considered.

        Args:
            layer (ResonatorLayer): Resonator layer.
            frequency (float): Frequency ω.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: 2x2 transmission matrix [A B; C D].
        """
        return self._transmission_computation.compute_layer_matrix(
            layer, frequency, xp, self._compute_7d_wave_number
        )

    def _find_spectral_poles_7d(
        self,
        frequencies: np.ndarray,
        admittance: np.ndarray,
        domain: Any,
    ) -> List[float]:
        """
        Find spectral poles using 7D phase field spectral analysis.

        Physical Meaning:
            Identifies resonance frequencies using 7D phase field spectral
            analysis, leveraging 7D Laplacian Δ₇ = Σᵢ₌₀⁶ ∂²/∂xᵢ² for enhanced
            pole detection that preserves 7D structure M₇ = ℝ³ₓ × 𝕋³_φ × ℝₜ.

        Mathematical Foundation:
            Uses 7D spectral analysis for pole detection:
            - 7D admittance: Y_7d(ω) computed using 7D wave vectors
            - 7D spectral poles: peaks in |Y_7d(ω)| with 7D structure awareness
            - 7D wave number: k_7d = sqrt(k_x² + k_y² + k_z² + k_φ₁² + k_φ₂² + k_φ₃² + k_t²)
            - Enhanced detection using 7D spectral properties

        Args:
            frequencies (np.ndarray): Frequency array.
            admittance (np.ndarray): Complex admittance array.
            domain: 7D domain object with spectral information.

        Returns:
            List[float]: List of pole frequencies from 7D spectral analysis.
        """
        return self._spectral_poles_analysis.find_spectral_poles_7d(
            frequencies, admittance, domain
        )

    def _find_admittance_poles(
        self, frequencies: np.ndarray, admittance_magnitude: np.ndarray
    ) -> List[float]:
        """
        Find admittance poles from magnitude peaks.

        Physical Meaning:
            Identifies resonance frequencies as peaks in admittance
            magnitude, representing locations where |Y(ω)| → ∞ or
            has local maxima.

        Mathematical Foundation:
            Poles are identified by:
            - Local maxima in |Y(ω)| above threshold
            - Peak detection using gradient analysis
            - Minimum peak height: 50% of maximum admittance

        Args:
            frequencies (np.ndarray): Frequency array.
            admittance_magnitude (np.ndarray): |Y(ω)| array.

        Returns:
            List[float]: List of pole frequencies.
        """
        return self._spectral_poles_analysis.find_admittance_poles(
            frequencies, admittance_magnitude
        )

    def _compute_spectral_quality_factor(
        self,
        pole_frequency: float,
        frequencies: np.ndarray,
        admittance_magnitude: np.ndarray,
    ) -> float:
        """
        Compute quality factor from spectral linewidth.

        Physical Meaning:
            Computes quality factor Q = ω₀ / (2π * Δω) from spectral
            linewidth, where Δω is the full width at half maximum (FWHM)
            of the admittance peak.

        Mathematical Foundation:
            Quality factor: Q = ω₀ / (2π * Δω)
            where:
            - ω₀ is the resonance frequency (pole frequency)
            - Δω is the FWHM of the admittance peak
            - Uses Lorentzian fitting for accurate FWHM estimation

        Args:
            pole_frequency (float): Resonance frequency ω₀.
            frequencies (np.ndarray): Frequency array.
            admittance_magnitude (np.ndarray): |Y(ω)| array.

        Returns:
            float: Quality factor Q.
        """
        # Initialize quality factors if not already done
        if self._quality_factors is None:
            from .quality_factors import ABCDQualityFactors

            self._quality_factors = ABCDQualityFactors(
                self._compute_resonator_determinants, self.logger
            )

        return self._quality_factors.compute_spectral_quality_factor(
            pole_frequency, frequencies, admittance_magnitude
        )

    def _compute_mode_amplitude_phase(self, frequency: float) -> Tuple[float, float]:
        """
        Compute mode amplitude and phase.

        Physical Meaning:
            Computes the amplitude and phase of the resonance mode
            at the given frequency from eigenvector analysis.

        Args:
            frequency (float): Frequency ω.

        Returns:
            Tuple[float, float]: (amplitude, phase) of the resonance mode.
        """
        # Initialize mode analysis if not already done
        if self._mode_analysis is None:
            from .mode_analysis import ABCDModeAnalysis

            self._mode_analysis = ABCDModeAnalysis(
                self._compute_transmission_matrix, self.logger
            )

        return self._mode_analysis.compute_mode_amplitude_phase(frequency)

    def _compute_transmission_matrices_vectorized(
        self, frequencies: np.ndarray, use_cuda_flag: bool, xp: Any, resonators: List
    ) -> np.ndarray:
        """
        Compute transmission matrices for frequency array using vectorized CUDA.

        Physical Meaning:
            Computes transmission matrices T_total(ω) for all frequencies
            simultaneously using vectorized CUDA operations with optimized
            block processing, maximizing GPU utilization and preserving
            7D structure awareness.

        Mathematical Foundation:
            For each frequency ω_i:
            T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i)
            All matrices computed in parallel using vectorized batched operations.

        Args:
            frequencies (np.ndarray): Array of frequencies.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            resonators (List): List of resonator layers.

        Returns:
            np.ndarray: Array of 2x2 transmission matrices.
        """
        return self._transmission_computation.compute_transmission_matrices_vectorized(
            frequencies, resonators, use_cuda_flag, xp, self._compute_7d_wave_number
        )

    def _compute_layer_matrices_vectorized(
        self, layer: ResonatorLayer, frequencies: np.ndarray, xp: Any
    ) -> np.ndarray:
        """
        Compute layer matrices for frequency array using vectorized operations.

        Physical Meaning:
            Computes 2x2 transmission matrices for a single layer at all
            frequencies simultaneously using vectorized CUDA operations,
            with 7D-aware wave number computation when domain is available.

        Mathematical Foundation:
            For each frequency ω_i:
            T(ω_i) = [cos(k_i Δr)  (1/k_i)sin(k_i Δr); -k_i sin(k_i Δr)  cos(k_i Δr)]
            where k_i is the 7D wave number computed from frequency and material properties.

        Args:
            layer (ResonatorLayer): Resonator layer.
            frequencies (np.ndarray): Array of frequencies.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Stack of 2x2 transmission matrices.
        """
        return self._transmission_computation.compute_layer_matrices_vectorized(
            layer, frequencies, xp, self._compute_7d_wave_number
        )

    def _compute_transmission_matrices_blocked(
        self, frequencies: np.ndarray, use_cuda_flag: bool, xp: Any, resonators: List
    ) -> np.ndarray:
        """
        Compute transmission matrices for large frequency arrays using block processing.

        Physical Meaning:
            Computes transmission matrices T_total(ω) for large frequency arrays
            using block processing that respects 80% GPU memory limit, processing
            frequencies in batches for optimal GPU utilization while maintaining
            vectorized operations within each block.

        Mathematical Foundation:
            For each frequency ω_i:
            T_total(ω_i) = T_1(ω_i) × T_2(ω_i) × ... × T_N(ω_i)
            Processes frequencies in blocks to maximize GPU memory efficiency
            while maintaining vectorized batched matrix multiplication within
            each block.

        Args:
            frequencies (np.ndarray): Array of frequencies.
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).
            resonators (List): List of resonator layers.

        Returns:
            np.ndarray: Array of 2x2 transmission matrices.
        """
        return self._transmission_computation.compute_transmission_matrices_blocked(
            frequencies, resonators, use_cuda_flag, xp, self._compute_7d_wave_number
        )

    def _compute_admittance_vectorized(
        self, frequencies_gpu: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using vectorized operations.

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for all frequencies
            using vectorized operations, maximizing GPU utilization.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        # Initialize admittance computation if not already done
        if self._admittance_computation is None:
            from .admittance_computation import ABCDAdmittanceComputation

            self._admittance_computation = ABCDAdmittanceComputation(
                self._compute_transmission_matrix, self.logger
            )

        return self._admittance_computation.compute_admittance_vectorized(
            frequencies_gpu, use_cuda_flag, xp
        )

    def _compute_admittance_blocked(
        self, frequencies_gpu: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """
        Compute admittance for frequency array using block processing (80% GPU memory).

        Physical Meaning:
            Computes admittance Y(ω) = C(ω) / A(ω) for large frequency arrays
            using block processing that respects 80% GPU memory limit,
            processing frequencies in batches for optimal GPU utilization.

        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω) where T_total = [A B; C D] is the
            system transmission matrix at frequency ω. Processes frequencies
            in blocks to maximize GPU memory efficiency while maintaining
            vectorized operations within each block.

        Args:
            frequencies_gpu (np.ndarray): Frequency array (GPU or CPU).
            use_cuda_flag (bool): Whether CUDA is available.
            xp: Array module (numpy or cupy).

        Returns:
            np.ndarray: Array of complex admittance values.
        """
        # Initialize admittance computation if not already done
        if self._admittance_computation is None:
            from .admittance_computation import ABCDAdmittanceComputation

            self._admittance_computation = ABCDAdmittanceComputation(
                self._compute_transmission_matrix, self.logger
            )

        return self._admittance_computation.compute_admittance_blocked(
            frequencies_gpu, use_cuda_flag, xp
        )

    def _compute_coupling_strength(
        self, frequency: float, all_frequencies: List[float]
    ) -> float:
        """
        Compute coupling strength with other modes.

        Physical Meaning:
            Computes the coupling strength between the mode at the
            given frequency and other system modes.

        Args:
            frequency (float): Frequency ω.
            all_frequencies (List[float]): List of all resonance frequencies.

        Returns:
            float: Coupling strength.
        """
        # Initialize mode analysis if not already done
        if self._mode_analysis is None:
            from .mode_analysis import ABCDModeAnalysis

            self._mode_analysis = ABCDModeAnalysis(
                self._compute_transmission_matrix, self.logger
            )

        return self._mode_analysis.compute_coupling_strength(frequency, all_frequencies)
