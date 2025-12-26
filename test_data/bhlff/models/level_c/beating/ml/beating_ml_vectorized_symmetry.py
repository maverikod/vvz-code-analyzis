"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized symmetry computation for ML prediction.

This module provides vectorized methods for computing symmetry
in 7D phase field configurations.

Physical Meaning:
    Computes symmetry of 7D phase field configurations using
    vectorized operations for efficient analysis.
"""

import numpy as np


class VectorizedSymmetryComputation:
    """
    Vectorized symmetry computation.
    
    Physical Meaning:
        Provides vectorized methods for computing symmetry.
    """
    
    def compute_7d_phase_field_symmetry_vectorized(
        self, envelope: np.ndarray
    ) -> float:
        """
        Compute 7D phase field symmetry using vectorized operations.
        
        Physical Meaning:
            Computes symmetry of 7D phase field configuration using
            vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized correlation analysis to compute symmetry
            based on 7D phase field theory and VBP envelope properties.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Symmetry score (0-1).
        """
        # Vectorized computation of spatial symmetry
        spatial_symmetry = self.compute_spatial_symmetry_vectorized(envelope)
        
        # Vectorized computation of spectral symmetry
        spectral_symmetry = self.compute_spectral_symmetry_vectorized(envelope)
        
        # Vectorized computation of phase symmetry
        phase_symmetry = self.compute_phase_symmetry_vectorized(envelope)
        
        # Vectorized combination of symmetries
        symmetry_weights = np.array([0.4, 0.3, 0.3])
        symmetry_values = np.array(
            [spatial_symmetry, spectral_symmetry, phase_symmetry]
        )
        
        combined_symmetry = np.sum(symmetry_weights * symmetry_values)
        
        # Normalize to [0, 1] range using sigmoid-like function
        normalized_symmetry = 0.5 + 0.5 * np.tanh(combined_symmetry)
        
        return max(0.0, min(1.0, normalized_symmetry))
    
    def compute_spatial_symmetry_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute spatial symmetry using vectorized operations.
        
        Physical Meaning:
            Computes spatial symmetry of 7D phase field configuration
            using vectorized correlation analysis.
        """
        # Vectorized spatial correlation analysis
        if envelope.ndim >= 2:
            # Compute correlation along each axis
            correlations = []
            for axis in range(min(3, envelope.ndim)):  # Limit to 3D for efficiency
                axis_data = np.moveaxis(envelope, axis, 0)
                if axis_data.shape[0] > 1:
                    mid_point = axis_data.shape[0] // 2
                    left_half = axis_data[:mid_point]
                    right_half = axis_data[mid_point:]
                    
                    if left_half.shape == right_half.shape:
                        correlation = np.corrcoef(
                            left_half.flatten(), right_half.flatten()
                        )[0, 1]
                        if not np.isnan(correlation):
                            correlations.append(correlation)
            
            if correlations:
                return np.mean(correlations)
            else:
                return 0.5
        
        return 0.5
    
    def compute_spectral_symmetry_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute spectral symmetry using vectorized operations.
        
        Physical Meaning:
            Computes spectral symmetry of 7D phase field configuration
            using vectorized spectral analysis.
        """
        # Vectorized spectral analysis
        fft_envelope = np.fft.fftn(envelope)
        fft_magnitude = np.abs(fft_envelope)
        
        # Vectorized spectral symmetry computation
        if fft_magnitude.ndim >= 2:
            mid_point = fft_magnitude.shape[0] // 2
            left_spectrum = fft_magnitude[:mid_point]
            right_spectrum = fft_magnitude[mid_point:]
            
            if left_spectrum.shape == right_spectrum.shape:
                correlation = np.corrcoef(
                    left_spectrum.flatten(), right_spectrum.flatten()
                )[0, 1]
                return correlation if not np.isnan(correlation) else 0.5
        
        return 0.5
    
    def compute_phase_symmetry_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute phase symmetry using vectorized operations.
        
        Physical Meaning:
            Computes phase symmetry of 7D phase field configuration
            using vectorized phase analysis.
        """
        # Vectorized phase analysis
        phase_envelope = np.angle(envelope)
        
        # Vectorized phase correlation
        if phase_envelope.ndim >= 2:
            mid_point = phase_envelope.shape[0] // 2
            left_phase = phase_envelope[:mid_point]
            right_phase = phase_envelope[mid_point:]
            
            if left_phase.shape == right_phase.shape:
                correlation = np.corrcoef(left_phase.flatten(), right_phase.flatten())[
                    0, 1
                ]
                return correlation if not np.isnan(correlation) else 0.5
        
        return 0.5

