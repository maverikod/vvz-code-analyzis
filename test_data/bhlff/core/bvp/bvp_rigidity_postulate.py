"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP Rigidity Postulate implementation for BVP framework.

This module implements Postulate 3 of the BVP framework, which states that
BVP field is "rigid" with high stiffness κ and short correlation length ℓ,
making it resistant to deformation and maintaining structural integrity.

Theoretical Background:
    BVP rigidity ensures that the field maintains its structural properties
    under perturbations. High stiffness κ and short correlation length ℓ
    create a rigid framework that resists deformation.

Example:
    >>> postulate = BVPRigidityPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any
from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate


class BVPRigidityPostulate(BVPPostulate):
    """
    Postulate 3: BVP Rigidity.

    Physical Meaning:
        BVP field is "rigid" with high stiffness κ and short
        correlation length ℓ, resistant to deformation.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize BVP rigidity postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            analyzing BVP field rigidity properties.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.stiffness_threshold = constants.get_quench_parameter("stiffness_threshold")
        self.correlation_length_threshold = constants.get_quench_parameter(
            "correlation_length_threshold"
        )

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply BVP rigidity postulate.

        Physical Meaning:
            Verifies that BVP field exhibits high stiffness and
            short correlation length, indicating rigidity.

        Mathematical Foundation:
            Analyzes field gradients and correlation functions to
            determine stiffness and correlation length.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including stiffness analysis,
                correlation length, and rigidity validation.
        """
        # Analyze field stiffness
        stiffness_analysis = self._analyze_field_stiffness(envelope)

        # Analyze correlation length
        correlation_analysis = self._analyze_correlation_length(envelope)

        # Check rigidity properties
        rigidity_properties = self._check_rigidity_properties(
            stiffness_analysis, correlation_analysis
        )

        # Validate BVP rigidity
        satisfies_postulate = self._validate_bvp_rigidity(rigidity_properties)

        return {
            "stiffness_analysis": stiffness_analysis,
            "correlation_analysis": correlation_analysis,
            "rigidity_properties": rigidity_properties,
            "satisfies_postulate": satisfies_postulate,
            "postulate_satisfied": satisfies_postulate,
        }

    def _analyze_field_stiffness(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze field stiffness from spatial gradients.

        Physical Meaning:
            Computes field stiffness from second derivatives and
            gradient magnitudes, indicating resistance to deformation.

        Mathematical Foundation:
            Stiffness κ ∝ |∇²A|/|A| where A is envelope amplitude.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Stiffness analysis.
        """
        amplitude = np.abs(envelope)

        # Compute second derivatives (Laplacian)
        laplacian = np.zeros_like(amplitude)
        for axis in range(3):  # Spatial dimensions only
            second_derivative = np.gradient(
                np.gradient(amplitude, self.domain.dx, axis=axis),
                self.domain.dx,
                axis=axis,
            )
            laplacian += second_derivative

        # Compute stiffness
        stiffness = np.abs(laplacian) / (amplitude + 1e-12)

        # Compute statistics
        mean_stiffness = np.mean(stiffness)
        std_stiffness = np.std(stiffness)
        max_stiffness = np.max(stiffness)

        return {
            "stiffness_field": stiffness,
            "mean_stiffness": mean_stiffness,
            "std_stiffness": std_stiffness,
            "max_stiffness": max_stiffness,
            "laplacian": laplacian,
        }

    def _analyze_correlation_length(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze correlation length of the field.

        Physical Meaning:
            Computes correlation length from spatial correlation
            function, indicating field coherence length.

        Mathematical Foundation:
            Correlation length ℓ is the characteristic length
            over which field values are correlated.

        Args:
            envelope (np.ndarray): BVP envelope.

        Returns:
            Dict[str, Any]: Correlation analysis.
        """
        amplitude = np.abs(envelope)

        # Compute spatial correlation function
        correlation_lengths = []
        for axis in range(3):  # Spatial dimensions only
            # Compute autocorrelation along each axis
            autocorr = self._compute_autocorrelation(amplitude, axis)
            correlation_length = self._extract_correlation_length(autocorr, axis)
            correlation_lengths.append(correlation_length)

        # Compute statistics
        mean_correlation_length = np.mean(correlation_lengths)
        std_correlation_length = np.std(correlation_lengths)
        min_correlation_length = np.min(correlation_lengths)

        return {
            "correlation_lengths": correlation_lengths,
            "mean_correlation_length": mean_correlation_length,
            "std_correlation_length": std_correlation_length,
            "min_correlation_length": min_correlation_length,
        }

    def _compute_autocorrelation(self, amplitude: np.ndarray, axis: int) -> np.ndarray:
        """
        Compute autocorrelation function along specified axis.

        Physical Meaning:
            Calculates spatial autocorrelation to determine
            field coherence properties.

        Args:
            amplitude (np.ndarray): Field amplitude.
            axis (int): Axis along which to compute autocorrelation.

        Returns:
            np.ndarray: Autocorrelation function.
        """
        # Compute autocorrelation using FFT
        fft_amplitude = np.fft.fft(amplitude, axis=axis)
        autocorr_fft = fft_amplitude * np.conj(fft_amplitude)
        autocorr = np.fft.ifft(autocorr_fft, axis=axis).real

        # Normalize
        autocorr = autocorr / np.max(autocorr)

        return autocorr

    def _extract_correlation_length(self, autocorr: np.ndarray, axis: int) -> float:
        """
        Extract correlation length from autocorrelation function.

        Physical Meaning:
            Finds characteristic length where autocorrelation
            drops to 1/e of its maximum value.

        Args:
            autocorr (np.ndarray): Autocorrelation function.
            axis (int): Axis along which correlation was computed.

        Returns:
            float: Correlation length.
        """
        # Find center of autocorrelation
        center_idx = autocorr.shape[axis] // 2

        # Extract correlation along axis
        if axis == 0:
            corr_profile = autocorr[center_idx, :, :]
        elif axis == 1:
            corr_profile = autocorr[:, center_idx, :]
        else:
            corr_profile = autocorr[:, :, center_idx]

        # Find 1/e point
        max_corr = np.max(corr_profile)
        threshold = max_corr / np.e

        # Find where correlation drops below threshold
        indices = np.where(corr_profile < threshold)[0]
        if len(indices) > 0:
            correlation_length = indices[0] * self.domain.dx
        else:
            correlation_length = len(corr_profile) * self.domain.dx

        return correlation_length

    def _check_rigidity_properties(
        self, stiffness_analysis: Dict[str, Any], correlation_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check rigidity properties of the BVP field.

        Physical Meaning:
            Verifies that field exhibits high stiffness and
            short correlation length, indicating rigidity.

        Args:
            stiffness_analysis (Dict[str, Any]): Stiffness analysis.
            correlation_analysis (Dict[str, Any]): Correlation analysis.

        Returns:
            Dict[str, Any]: Rigidity properties.
        """
        mean_stiffness = stiffness_analysis["mean_stiffness"]
        min_correlation_length = correlation_analysis["min_correlation_length"]

        # Check stiffness threshold
        high_stiffness = mean_stiffness > self.stiffness_threshold

        # Check correlation length threshold
        short_correlation = min_correlation_length < self.correlation_length_threshold

        # Overall rigidity
        is_rigid = high_stiffness and short_correlation

        return {
            "high_stiffness": high_stiffness,
            "short_correlation": short_correlation,
            "is_rigid": is_rigid,
            "rigidity_quality": (
                mean_stiffness / max(self.stiffness_threshold, 1e-12)
                + self.correlation_length_threshold / max(min_correlation_length, 1e-12)
            )
            / 2,
        }

    def _validate_bvp_rigidity(self, rigidity_properties: Dict[str, Any]) -> bool:
        """
        Validate BVP rigidity postulate.

        Physical Meaning:
            Checks that field exhibits sufficient rigidity
            properties for BVP framework validity.

        Args:
            rigidity_properties (Dict[str, Any]): Rigidity properties.

        Returns:
            bool: True if BVP rigidity is satisfied.
        """
        return rigidity_properties["is_rigid"]
