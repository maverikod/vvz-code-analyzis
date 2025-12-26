"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Helper methods for ABCD model.

This module provides helper methods as a mixin class.
"""

import numpy as np
from typing import List, Tuple, Dict, Any
from ...abcd import ResonatorLayer, SystemMode

from ..admittance_computation import ABCDAdmittanceComputation
from ..quality_factors import ABCDQualityFactors
from ..mode_analysis import ABCDModeAnalysis
from ..delegation_methods import ABCDDelegationMethods


class ABCDModelHelpersMixin:
    """Mixin providing helper methods."""
    
    def find_resonance_conditions(
        self, frequency_range: Tuple[float, float]
    ) -> List[float]:
        """
        Find frequencies satisfying resonance conditions using spectral metrics.
        
        Physical Meaning:
            Finds all resonance frequencies using physically motivated
            spectral metrics (poles/Q factors) instead of generic determinant
            checks. Uses 7D phase field spectral analysis when available.
            
        Mathematical Foundation:
            Resonance condition: spectral poles from admittance analysis:
            - Compute admittance Y(ω) = C(ω) / A(ω) for all frequencies
            - Find poles where |Y(ω)| → ∞ or Im(Y(ω)) has peaks
            - Quality factor: Q = ω₀ / (2π * Δω) from spectral linewidth
            - Uses 7D spectral operations when BVP core is available
            
        Args:
            frequency_range (Tuple[float, float]): (ω_min, ω_max) range.
            
        Returns:
            List[float]: List of resonance frequencies from spectral analysis.
        """
        omega_min, omega_max = frequency_range
        
        # Use vectorized frequency sweep with CUDA if available
        n_points = 1000
        frequencies = np.logspace(np.log10(omega_min), np.log10(omega_max), n_points)
        
        # Compute spectral metrics (poles/Q factors) instead of determinants
        resonance_frequencies = self._find_spectral_poles(frequencies)
        
        return resonance_frequencies
    
    def find_system_modes(
        self, frequency_range: Tuple[float, float]
    ) -> List[SystemMode]:
        """
        Find system resonance modes.
        
        Physical Meaning:
            Identifies all system resonance modes in the given frequency
            range, computing their frequencies, quality factors, and
            coupling properties.
            
        Mathematical Foundation:
            For each resonance frequency ω_n:
            - Quality factor: Q_n = ω_n / (2 * Im(ω_n))
            - Amplitude: |A_n| from eigenvector analysis
            - Phase: arg(A_n) from eigenvector analysis
            
        Args:
            frequency_range (Tuple[float, float]): Frequency range to search.
            
        Returns:
            List[SystemMode]: List of system resonance modes.
        """
        resonance_frequencies = self.find_resonance_conditions(frequency_range)
        
        # Initialize mode analysis if not already done
        if self._mode_analysis is None:
            self._mode_analysis = ABCDModeAnalysis(
                self.compute_transmission_matrix, self.logger
            )
        
        system_modes = []
        for i, omega_n in enumerate(resonance_frequencies):
            # Compute quality factor
            Q_n = self._compute_quality_factor(omega_n)
            
            # Compute mode amplitude and phase
            amplitude, phase = self._mode_analysis.compute_mode_amplitude_phase(omega_n)
            
            # Compute coupling strength
            coupling_strength = self._mode_analysis.compute_coupling_strength(
                omega_n, resonance_frequencies
            )
            
            mode = SystemMode(
                frequency=omega_n,
                quality_factor=Q_n,
                amplitude=amplitude,
                phase=phase,
                mode_index=i,
                coupling_strength=coupling_strength,
            )
            system_modes.append(mode)
        
        return system_modes
    
    def analyze_resonator_chain(
        self,
        domain: Dict[str, Any],
        resonator_layers: List[ResonatorLayer],
        abcd_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Analyze resonator chain using ABCD model.
        
        Physical Meaning:
            Analyzes a resonator chain using the ABCD transmission
            matrix method, finding resonance modes and system properties.
            
        Args:
            domain (Dict[str, Any]): Domain parameters.
            resonator_layers (List[ResonatorLayer]): List of resonator layers.
            abcd_params (Dict[str, Any]): ABCD model parameters.
            
        Returns:
            Dict[str, Any]: Analysis results including resonance modes.
        """
        # Set resonators if provided
        if resonator_layers:
            self.resonators = resonator_layers
            self._compute_layer_properties()
            # Reinitialize transmission computation with new resonators
            from ..transmission_computation import ABCDTransmissionComputation
            self._transmission_computation = ABCDTransmissionComputation(
                self.resonators, self.bvp_core, self.use_cuda, self.logger
            )
        
        # Get frequency range from parameters
        frequency_range = abcd_params.get("frequency_range", (0.1, 2.0))
        
        # Find system modes
        system_modes = self.find_system_modes(frequency_range)
        
        # Compute transmission matrices for key frequencies
        key_frequencies = [mode.frequency for mode in system_modes[:5]]  # First 5 modes
        transmission_matrices = {}
        for freq in key_frequencies:
            transmission_matrices[freq] = self.compute_transmission_matrix(freq)
        
        return {
            "system_modes": system_modes,
            "transmission_matrices": transmission_matrices,
            "frequency_range": frequency_range,
            "num_resonators": len(self.resonators),
        }
    
    def compute_system_admittance(self, frequency: float) -> complex:
        """
        Compute total system admittance.
        
        Physical Meaning:
            Computes the complex admittance Y(ω) = I(ω)/V(ω) of the
            entire resonator chain, representing the system's
            response to external excitation.
            
        Mathematical Foundation:
            Y(ω) = C(ω) / A(ω)
            where T_total = [A B; C D] is the system transmission matrix
            
        Args:
            frequency (float): Frequency ω for admittance calculation.
            
        Returns:
            complex: Complex admittance Y(ω).
        """
        T = self.compute_transmission_matrix(frequency)
        A, B, C, D = T[0, 0], T[0, 1], T[1, 0], T[1, 1]
        
        # Avoid division by zero
        if abs(A) < 1e-12:
            return complex(0, 0)
        
        return C / A
    
    def _find_spectral_poles(self, frequencies: np.ndarray) -> List[float]:
        """
        Find spectral poles from admittance analysis.
        
        Physical Meaning:
            Finds resonance frequencies by identifying spectral poles
            in the admittance response, using physically motivated
            spectral metrics instead of determinant checks.
            
        Mathematical Foundation:
            Spectral poles are identified as:
            - Peaks in |Y(ω)| where admittance magnitude is maximum
            - Zeros of Im(Y(ω)) where phase crosses zero
            - Uses 7D spectral analysis when field generator is available
            
        Args:
            frequencies (np.ndarray): Frequency array.
            
        Returns:
            List[float]: List of resonance frequencies (spectral poles).
        """
        # Compute spectral metrics using compute_resonator_determinants
        spectral_metrics = self.compute_resonator_determinants(frequencies)
        return spectral_metrics["spectral_poles"].tolist()
    
    def _compute_quality_factor(self, frequency: float) -> float:
        """
        Compute quality factor for given frequency using spectral metrics.
        
        Physical Meaning:
            Computes the quality factor Q = ω₀ / (2π * Δω) from spectral
            linewidth, which characterizes the resonance sharpness and
            energy storage using physically motivated spectral metrics.
            
        Mathematical Foundation:
            Uses spectral quality factor calculation:
            Q = ω₀ / (2π * Δω)
            where Δω is the FWHM from admittance spectral analysis.
            
        Args:
            frequency (float): Resonance frequency ω₀.
            
        Returns:
            float: Quality factor Q.
        """
        # Initialize quality factors if not already done
        if self._quality_factors is None:
            self._quality_factors = ABCDQualityFactors(
                self.compute_resonator_determinants, self.logger
            )
        
        return self._quality_factors.compute_quality_factor(frequency)
    
    def _get_delegation(self):
        """Get or create delegation methods instance."""
        if self._delegation is None:
            self._delegation = ABCDDelegationMethods(
                self._transmission_computation,
                self._spectral_poles_analysis,
                self._admittance_computation,
                self._quality_factors,
                self._mode_analysis,
                self._compute_7d_wave_number,
                self.compute_resonator_determinants,
                self.compute_transmission_matrix,
                self.logger,
            )
        return self._delegation
    
    def _compute_layer_matrix(
        self,
        layer: ResonatorLayer,
        frequency: float,
        xp: Any = np,
    ) -> np.ndarray:
        """Compute transmission matrix for single layer."""
        return self._get_delegation()._compute_layer_matrix(layer, frequency, xp)
    
    def _find_spectral_poles_7d(
        self,
        frequencies: np.ndarray,
        admittance: np.ndarray,
        domain: Any,
    ) -> List[float]:
        """Find spectral poles using 7D phase field spectral analysis."""
        return self._get_delegation()._find_spectral_poles_7d(
            frequencies, admittance, domain
        )
    
    def _find_admittance_poles(
        self, frequencies: np.ndarray, admittance_magnitude: np.ndarray
    ) -> List[float]:
        """Find admittance poles from magnitude peaks."""
        return self._get_delegation()._find_admittance_poles(
            frequencies, admittance_magnitude
        )
    
    def _compute_spectral_quality_factor(
        self,
        pole_frequency: float,
        frequencies: np.ndarray,
        admittance_magnitude: np.ndarray,
    ) -> float:
        """Compute quality factor from spectral linewidth."""
        return self._get_delegation()._compute_spectral_quality_factor(
            pole_frequency, frequencies, admittance_magnitude
        )
    
    def _compute_mode_amplitude_phase(self, frequency: float) -> Tuple[float, float]:
        """Compute mode amplitude and phase."""
        return self._get_delegation()._compute_mode_amplitude_phase(frequency)
    
    def _compute_transmission_matrices_vectorized(
        self, frequencies: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """Compute transmission matrices for frequency array using vectorized CUDA."""
        return self._get_delegation()._compute_transmission_matrices_vectorized(
            frequencies, use_cuda_flag, xp, self.resonators
        )
    
    def _compute_layer_matrices_vectorized(
        self, layer: ResonatorLayer, frequencies: np.ndarray, xp: Any
    ) -> np.ndarray:
        """Compute layer matrices for frequency array using vectorized operations."""
        return self._get_delegation()._compute_layer_matrices_vectorized(
            layer, frequencies, xp
        )
    
    def _compute_transmission_matrices_blocked(
        self, frequencies: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """Compute transmission matrices for large frequency arrays using block processing."""
        return self._get_delegation()._compute_transmission_matrices_blocked(
            frequencies, use_cuda_flag, xp, self.resonators
        )
    
    def _compute_admittance_vectorized(
        self, frequencies_gpu: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """Compute admittance for frequency array using vectorized operations."""
        return self._get_delegation()._compute_admittance_vectorized(
            frequencies_gpu, use_cuda_flag, xp
        )
    
    def _compute_admittance_blocked(
        self, frequencies_gpu: np.ndarray, use_cuda_flag: bool, xp: Any
    ) -> np.ndarray:
        """Compute admittance for frequency array using block processing (80% GPU memory)."""
        return self._get_delegation()._compute_admittance_blocked(
            frequencies_gpu, use_cuda_flag, xp
        )
    
    def _compute_coupling_strength(
        self, frequency: float, all_frequencies: List[float]
    ) -> float:
        """Compute coupling strength with other modes."""
        return self._get_delegation()._compute_coupling_strength(
            frequency, all_frequencies
        )

