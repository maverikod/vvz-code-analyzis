"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Coupling feature extraction for ML prediction.

This module provides methods for extracting coupling-related features
from 7D phase field configurations for ML prediction.

Physical Meaning:
    Extracts coupling-related features including coupling strength,
    interaction energy, symmetry, and nonlinear effects from 7D phase
    field configurations for mode coupling prediction.
"""

import numpy as np
from typing import Dict, Any
from .feature_calculators import FeatureCalculator
from .phase_field_features import PhaseFieldFeatures


class CouplingFeatureExtractor:
    """
    Coupling feature extractor for ML prediction.
    
    Physical Meaning:
        Provides methods for extracting coupling-related features
        from 7D phase field configurations.
    """
    
    def __init__(self, calculator: FeatureCalculator, phase_features: PhaseFieldFeatures):
        """
        Initialize coupling feature extractor.
        
        Args:
            calculator: Feature calculator instance.
            phase_features: Phase field features instance.
        """
        self.calculator = calculator
        self.phase_features = phase_features
    
    def extract_coupling_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract coupling features from envelope.
        
        Physical Meaning:
            Extracts coupling-related features from envelope
            for ML prediction of mode coupling.
            
        Mathematical Foundation:
            Computes coupling strength, interaction energy, symmetry,
            and nonlinear effects from 7D phase field configuration.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Coupling features dictionary.
        """
        # Calculate coupling strength
        coupling_strength = self.calculator.calculate_coupling_strength(envelope)
        
        # Calculate interaction energy
        interaction_energy = self.calculator.calculate_interaction_energy(envelope)
        
        # Calculate coupling symmetry
        coupling_symmetry = self.calculator.calculate_coupling_symmetry(envelope)
        
        # Calculate nonlinear strength
        nonlinear_strength = self.calculator.calculate_nonlinear_strength(envelope)
        
        # Calculate mixing degree
        mixing_degree = self.calculator.calculate_mixing_degree(envelope)
        
        # Calculate coupling efficiency
        coupling_efficiency = self.calculator.calculate_coupling_efficiency(envelope)
        
        # Calculate 7D phase field features
        phase_coherence = self.phase_features._compute_phase_coherence(
            {
                "coupling_symmetry": coupling_symmetry,
                "autocorrelation": 0.0,  # Will be computed in frequency features
            }
        )
        topological_charge = self.phase_features._compute_topological_charge(
            {
                "mixing_degree": mixing_degree,
                "nonlinear_strength": nonlinear_strength,
            }
        )
        
        return {
            "coupling_strength": coupling_strength,
            "interaction_energy": interaction_energy,
            "coupling_symmetry": coupling_symmetry,
            "nonlinear_strength": nonlinear_strength,
            "mixing_degree": mixing_degree,
            "coupling_efficiency": coupling_efficiency,
            "phase_coherence": phase_coherence,
            "topological_charge": topological_charge,
        }

