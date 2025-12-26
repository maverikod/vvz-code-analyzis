"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Vectorized regularity computation for ML prediction.

This module provides vectorized methods for computing regularity
in 7D phase field configurations.

Physical Meaning:
    Computes regularity of 7D phase field configurations using
    vectorized operations for efficient analysis.
"""

import numpy as np


class VectorizedRegularityComputation:
    """
    Vectorized regularity computation.
    
    Physical Meaning:
        Provides vectorized methods for computing regularity.
    """
    
    def compute_7d_phase_field_regularity_vectorized(
        self, envelope: np.ndarray
    ) -> float:
        """
        Compute 7D phase field regularity using vectorized operations.
        
        Physical Meaning:
            Computes regularity of 7D phase field configuration using
            vectorized operations for efficient analysis.
            
        Mathematical Foundation:
            Uses vectorized variance analysis to compute regularity
            based on 7D phase field theory and VBP envelope properties.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            float: Regularity score (0-1).
        """
        # Vectorized computation of spatial regularity
        spatial_regularity = self.compute_spatial_regularity_vectorized(envelope)
        
        # Vectorized computation of temporal regularity
        temporal_regularity = self.compute_temporal_regularity_vectorized(envelope)
        
        # Vectorized computation of spectral regularity
        spectral_regularity = self.compute_spectral_regularity_vectorized(envelope)
        
        # Vectorized combination of regularities
        regularity_weights = np.array([0.4, 0.3, 0.3])
        regularity_values = np.array(
            [spatial_regularity, temporal_regularity, spectral_regularity]
        )
        
        combined_regularity = np.sum(regularity_weights * regularity_values)
        
        return max(0.0, min(1.0, combined_regularity))
    
    def compute_spatial_regularity_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute spatial regularity using vectorized operations.
        
        Physical Meaning:
            Computes spatial regularity of 7D phase field configuration
            using vectorized variance analysis.
        """
        # Vectorized spatial variance analysis
        spatial_variance = np.var(envelope, axis=tuple(range(1, envelope.ndim)))
        
        # Vectorized regularity computation
        if len(spatial_variance) > 1:
            regularity = 1.0 / (1.0 + np.mean(spatial_variance))
            return max(0.0, min(1.0, regularity))
        
        return 0.5
    
    def compute_temporal_regularity_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute temporal regularity using vectorized operations.
        
        Physical Meaning:
            Computes temporal regularity of 7D phase field configuration
            using vectorized variance analysis for efficiency.
        """
        # Vectorized variance analysis for efficiency
        if envelope.ndim >= 1:
            # Compute variance along time axis (last dimension)
            if envelope.ndim > 1:
                # Use last dimension as time axis
                time_axis = envelope.ndim - 1
                variance = np.var(envelope, axis=time_axis)
                
                # Compute regularity based on variance
                if variance.size > 0:
                    # Lower variance means higher regularity
                    max_variance = np.max(variance)
                    if max_variance > 0:
                        regularity = 1.0 - (np.mean(variance) / max_variance)
                        return max(0.0, min(1.0, regularity))
            else:
                # For 1D arrays, use simple variance
                variance = np.var(envelope)
                if variance > 0:
                    regularity = 1.0 / (1.0 + variance)
                    return max(0.0, min(1.0, regularity))
        
        return 0.5
    
    def compute_spectral_regularity_vectorized(self, envelope: np.ndarray) -> float:
        """
        Compute spectral regularity using vectorized operations.
        
        Physical Meaning:
            Computes spectral regularity of 7D phase field configuration
            using vectorized spectral analysis.
        """
        # Vectorized spectral analysis
        fft_envelope = np.fft.fftn(envelope)
        fft_magnitude = np.abs(fft_envelope)
        
        # Vectorized spectral regularity computation
        spectral_variance = np.var(fft_magnitude)
        spectral_mean = np.mean(fft_magnitude)
        
        if spectral_mean > 0:
            regularity = 1.0 / (1.0 + spectral_variance / spectral_mean)
            return max(0.0, min(1.0, regularity))
        
        return 0.5

