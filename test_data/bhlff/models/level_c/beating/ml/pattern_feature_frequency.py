"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Frequency feature extraction for pattern classification.

This module provides methods for extracting frequency features
from 7D phase field configurations.

Physical Meaning:
    Extracts frequency characteristics from 7D phase field configuration
    using spectral analysis and FFT methods.
"""

import numpy as np
from typing import Dict, Any


class FrequencyFeatureExtraction:
    """
    Frequency feature extraction.
    
    Physical Meaning:
        Provides methods for extracting frequency features.
    """
    
    def extract_frequency_features(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Extract frequency features from envelope.
        
        Physical Meaning:
            Extracts frequency characteristics from 7D phase field configuration
            using spectral analysis and FFT methods.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Frequency features dictionary.
        """
        envelope_fft = np.fft.fftn(envelope)
        frequency_spectrum = np.abs(envelope_fft)
        
        return {
            "spectrum_peak": np.max(frequency_spectrum),
            "spectrum_mean": np.mean(frequency_spectrum),
            "spectrum_std": np.std(frequency_spectrum),
            "spectrum_entropy": self.compute_spectral_entropy(frequency_spectrum),
            "frequency_spacing": self.compute_frequency_spacing(frequency_spectrum),
            "frequency_bandwidth": self.compute_frequency_bandwidth(frequency_spectrum),
            "dominant_frequencies": np.argsort(frequency_spectrum.flatten())[-5:].tolist(),
        }
    
    def compute_spectral_entropy(self, spectrum: np.ndarray) -> float:
        """
        Compute spectral entropy.
        
        Physical Meaning:
            Computes spectral entropy of frequency spectrum
            to measure frequency distribution complexity.
        """
        # Normalize spectrum to probability distribution
        total_spectrum = np.sum(spectrum)
        if total_spectrum > 0:
            prob_dist = spectrum / total_spectrum
            entropy = -np.sum(prob_dist * np.log(prob_dist + 1e-10))
            return float(entropy)
        return 0.0
    
    def compute_frequency_spacing(self, spectrum: np.ndarray) -> float:
        """
        Compute frequency spacing.
        
        Physical Meaning:
            Computes average spacing between dominant frequencies
            in the spectrum.
        """
        # Find peaks in spectrum
        peaks = self.find_spectral_peaks(spectrum)
        if len(peaks) > 1:
            spacing = np.mean(np.diff(peaks))
            return float(spacing)
        return 0.0
    
    def compute_frequency_bandwidth(self, spectrum: np.ndarray) -> float:
        """
        Compute frequency bandwidth.
        
        Physical Meaning:
            Computes bandwidth of frequency spectrum
            to measure frequency spread.
        """
        # Compute bandwidth as standard deviation of spectrum
        bandwidth = np.std(spectrum)
        return float(bandwidth)
    
    def find_spectral_peaks(
        self, spectrum: np.ndarray, threshold: float = 0.1
    ) -> np.ndarray:
        """
        Find spectral peaks.
        
        Physical Meaning:
            Finds dominant frequency peaks in the spectrum
            above the specified threshold.
        """
        max_spectrum = np.max(spectrum)
        threshold_value = threshold * max_spectrum
        
        # Find peaks above threshold
        peaks = np.where(spectrum > threshold_value)[0]
        return peaks

