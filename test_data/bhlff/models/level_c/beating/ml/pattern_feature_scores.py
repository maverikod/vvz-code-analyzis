"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Pattern score computation for feature extraction.

This module provides methods for computing symmetry, regularity,
and complexity scores for pattern classification.

Physical Meaning:
    Computes pattern scores based on 7D phase field properties
    and VBP envelope analysis using full mathematical framework.
"""

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pattern_feature_helpers import PatternFeatureHelpers


class PatternScoreComputation:
    """
    Pattern score computation.
    
    Physical Meaning:
        Provides methods for computing pattern scores.
    """
    
    def __init__(self, helpers: "PatternFeatureHelpers"):
        """
        Initialize pattern score computation.
        
        Args:
            helpers: Pattern feature helpers instance.
        """
        self.helpers = helpers
    
    def calculate_symmetry_score(self, envelope: np.ndarray) -> float:
        """
        Calculate symmetry score using 7D phase field theory.
        
        Physical Meaning:
            Computes symmetry score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
        """
        # Compute 7D phase field symmetry using full mathematical framework
        phase_field_symmetry = self.compute_7d_phase_field_symmetry(envelope)
        
        # Compute VBP envelope symmetry
        vbp_symmetry = self.compute_vbp_envelope_symmetry(envelope)
        
        # Combine symmetries using 7D phase field theory
        combined_symmetry = self.combine_7d_symmetries(
            phase_field_symmetry, vbp_symmetry
        )
        
        return max(0.0, min(1.0, combined_symmetry))
    
    def calculate_regularity_score(self, envelope: np.ndarray) -> float:
        """
        Calculate regularity score using 7D phase field theory.
        
        Physical Meaning:
            Computes regularity score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
        """
        # Compute 7D phase field regularity using full mathematical framework
        phase_field_regularity = self.compute_7d_phase_field_regularity(envelope)
        
        # Compute VBP envelope regularity
        vbp_regularity = self.compute_vbp_envelope_regularity(envelope)
        
        # Combine regularities using 7D phase field theory
        combined_regularity = self.combine_7d_regularities(
            phase_field_regularity, vbp_regularity
        )
        
        return max(0.0, min(1.0, combined_regularity))
    
    def calculate_complexity_score(self, envelope: np.ndarray) -> float:
        """
        Calculate complexity score using 7D phase field theory.
        
        Physical Meaning:
            Computes complexity score based on 7D phase field properties
            and VBP envelope analysis using full mathematical framework.
        """
        # Compute 7D phase field complexity using full mathematical framework
        phase_field_complexity = self.compute_7d_phase_field_complexity(envelope)
        
        # Compute VBP envelope complexity
        vbp_complexity = self.compute_vbp_envelope_complexity(envelope)
        
        # Combine complexities using 7D phase field theory
        combined_complexity = self.combine_7d_complexities(
            phase_field_complexity, vbp_complexity
        )
        
        return max(0.0, min(1.0, combined_complexity))
    
    def compute_7d_phase_field_symmetry(self, envelope: np.ndarray) -> float:
        """
        Compute 7D phase field symmetry using full mathematical framework.
        
        Physical Meaning:
            Computes symmetry based on 7D phase field theory including
            phase coherence, topological charge, and energy density.
        """
        # Compute phase of envelope
        phase = np.angle(envelope)
        
        # Compute 7D phase field symmetry using circular statistics
        complex_phase = np.exp(1j * phase)
        mean_complex = np.mean(complex_phase)
        phase_coherence = np.abs(mean_complex)
        
        # Compute topological charge symmetry
        topological_charge = self.helpers.compute_topological_charge(envelope)
        charge_symmetry = 1.0 - abs(topological_charge)
        
        # Compute energy density symmetry
        energy_density = np.abs(envelope) ** 2
        energy_symmetry = self.helpers.compute_energy_symmetry(energy_density)
        
        # Combine symmetries using 7D phase field theory
        combined_symmetry = (
            phase_coherence * 0.4 + charge_symmetry * 0.3 + energy_symmetry * 0.3
        )
        
        return float(combined_symmetry)
    
    def compute_vbp_envelope_symmetry(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope symmetry.
        
        Physical Meaning:
            Computes VBP envelope symmetry based on envelope properties.
        """
        # Compute envelope symmetry using spatial correlation
        center = envelope.shape[0] // 2
        left_half = envelope[:center]
        right_half = envelope[center:]
        
        if left_half.shape != right_half.shape:
            return 0.5
        
        correlation = np.corrcoef(left_half.flatten(), right_half.flatten())[0, 1]
        return max(0.0, min(1.0, correlation))
    
    def combine_7d_symmetries(
        self, phase_field_symmetry: float, vbp_symmetry: float
    ) -> float:
        """
        Combine 7D symmetries using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope symmetries using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_symmetry * 0.7 + vbp_symmetry * 0.3
    
    def compute_7d_phase_field_regularity(self, envelope: np.ndarray) -> float:
        """
        Compute 7D phase field regularity using full mathematical framework.
        
        Physical Meaning:
            Computes regularity based on 7D phase field theory including
            phase coherence, topological charge, and energy density.
        """
        # Compute phase regularity using circular statistics
        phase = np.angle(envelope)
        phase_regularity = 1.0 - np.std(phase) / np.pi
        
        # Compute energy density regularity
        energy_density = np.abs(envelope) ** 2
        energy_regularity = 1.0 - np.std(energy_density) / np.mean(energy_density)
        
        # Compute topological charge regularity
        topological_charge = self.helpers.compute_topological_charge(envelope)
        charge_regularity = 1.0 - abs(topological_charge)
        
        # Combine regularities using 7D phase field theory
        combined_regularity = (
            phase_regularity * 0.4 + energy_regularity * 0.4 + charge_regularity * 0.2
        )
        
        return float(combined_regularity)
    
    def compute_vbp_envelope_regularity(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope regularity.
        
        Physical Meaning:
            Computes VBP envelope regularity based on envelope properties.
        """
        # Compute envelope regularity using variance analysis
        envelope_abs = np.abs(envelope)
        local_variance = np.var(envelope_abs)
        global_variance = np.var(envelope_abs.flatten())
        
        if global_variance == 0:
            return 1.0
        
        regularity = 1.0 - (local_variance / global_variance)
        return max(0.0, min(1.0, regularity))
    
    def combine_7d_regularities(
        self, phase_field_regularity: float, vbp_regularity: float
    ) -> float:
        """
        Combine 7D regularities using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope regularities using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_regularity * 0.7 + vbp_regularity * 0.3
    
    def compute_7d_phase_field_complexity(self, envelope: np.ndarray) -> float:
        """
        Compute 7D phase field complexity using full mathematical framework.
        
        Physical Meaning:
            Computes complexity based on 7D phase field theory including
            phase coherence, topological charge, and energy density.
        """
        # Compute phase complexity using spectral analysis
        phase = np.angle(envelope)
        phase_fft = np.fft.fftn(phase)
        phase_spectrum = np.abs(phase_fft)
        
        # Count significant phase components
        threshold = 0.1 * np.max(phase_spectrum)
        significant_components = np.sum(phase_spectrum > threshold)
        total_components = phase_spectrum.size
        phase_complexity = significant_components / total_components
        
        # Compute energy density complexity
        energy_density = np.abs(envelope) ** 2
        energy_fft = np.fft.fftn(energy_density)
        energy_spectrum = np.abs(energy_fft)
        
        # Count significant energy components
        threshold = 0.1 * np.max(energy_spectrum)
        significant_components = np.sum(energy_spectrum > threshold)
        total_components = energy_spectrum.size
        energy_complexity = significant_components / total_components
        
        # Compute topological charge complexity
        topological_charge = self.helpers.compute_topological_charge(envelope)
        charge_complexity = abs(topological_charge)
        
        # Combine complexities using 7D phase field theory
        combined_complexity = (
            phase_complexity * 0.4 + energy_complexity * 0.4 + charge_complexity * 0.2
        )
        
        return float(combined_complexity)
    
    def compute_vbp_envelope_complexity(self, envelope: np.ndarray) -> float:
        """
        Compute VBP envelope complexity.
        
        Physical Meaning:
            Computes VBP envelope complexity based on envelope properties.
        """
        # Compute envelope complexity using frequency content
        envelope_fft = np.fft.fftn(envelope)
        frequency_spectrum = np.abs(envelope_fft)
        
        # Count significant frequency components
        threshold = 0.1 * np.max(frequency_spectrum)
        significant_components = np.sum(frequency_spectrum > threshold)
        total_components = frequency_spectrum.size
        
        complexity = significant_components / total_components
        return max(0.0, min(1.0, complexity))
    
    def combine_7d_complexities(
        self, phase_field_complexity: float, vbp_complexity: float
    ) -> float:
        """
        Combine 7D complexities using phase field theory.
        
        Physical Meaning:
            Combines phase field and VBP envelope complexities using
            7D phase field theory principles.
        """
        # Weighted combination based on 7D phase field theory
        return phase_field_complexity * 0.7 + vbp_complexity * 0.3

