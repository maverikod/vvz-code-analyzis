"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP level interface for Level D (multimode models) implementation.

This module provides integration interface for Level D of the 7D phase field theory,
ensuring that BVP serves as the central backbone for multimode superposition,
field projections, and streamlines analysis.

Physical Meaning:
    Level D: Multimode superposition, field projections, and streamlines
    Analyzes multimode superposition patterns, field projections onto different
    subspaces, and streamline patterns in the BVP envelope.

Mathematical Foundation:
    Implements specific mathematical operations that work with BVP envelope data,
    transforming it according to Level D requirements while maintaining BVP framework compliance.

Example:
    >>> level_d = LevelDInterface(bvp_core)
    >>> results = level_d.process_bvp_data(envelope)
"""

import numpy as np
from typing import Dict, Any

from .bvp_level_interface_base import BVPLevelInterface
from .bvp_core import BVPCore


class LevelDInterface(BVPLevelInterface):
    """
    BVP integration interface for Level D (multimode models).

    Physical Meaning:
        Provides BVP data for Level D analysis of multimode superposition,
        field projections, and streamlines. Analyzes how multiple modes
        interact and superpose in the BVP envelope, providing insights
        into the complex multimode dynamics.

    Mathematical Foundation:
        Implements analysis of:
        - Mode superposition: FFT decomposition and dominant mode identification
        - Field projections: Projection onto spatial and phase subspaces
        - Streamlines: Gradient analysis and flow pattern identification
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize Level D interface.

        Physical Meaning:
            Sets up the interface for Level D analysis with access to
            BVP core functionality and constants.

        Args:
            bvp_core (BVPCore): BVP core instance for data access.
        """
        self.bvp_core = bvp_core
        self.constants = bvp_core._bvp_constants

    def process_bvp_data(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Process BVP data for Level D operations.

        Physical Meaning:
            Analyzes multimode superposition, field projections,
            and streamlines in BVP envelope to understand the
            complex multimode dynamics and field structure.

        Mathematical Foundation:
            Performs comprehensive analysis including:
            - FFT-based mode decomposition
            - Subspace projection analysis
            - Gradient-based streamline analysis

        Args:
            envelope (np.ndarray): BVP envelope in 7D space-time.
            **kwargs: Level-specific parameters.

        Returns:
            Dict[str, Any]: Processed data including:
                - envelope: Original BVP envelope
                - mode_superposition: Mode analysis results
                - field_projections: Projection analysis results
                - streamlines: Streamline analysis results
                - level: Level identifier ("D")
        """
        # Analyze mode superposition
        superposition_data = self._analyze_mode_superposition(envelope)

        # Analyze field projections
        projection_data = self._analyze_field_projections(envelope)

        # Analyze streamlines
        streamline_data = self._analyze_streamlines(envelope)

        return {
            "envelope": envelope,
            "mode_superposition": superposition_data,
            "field_projections": projection_data,
            "streamlines": streamline_data,
            "level": "D",
        }

    def _analyze_mode_superposition(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze mode superposition patterns.

        Physical Meaning:
            Performs FFT analysis to decompose the BVP envelope into
            its constituent modes and identifies dominant frequency
            components and their amplitudes.

        Mathematical Foundation:
            Uses FFT decomposition: a(x) = Σ A_k e^(ik·x)
            where A_k are the mode amplitudes and k are wave vectors.

        Args:
            envelope (np.ndarray): BVP envelope field.

        Returns:
            Dict[str, Any]: Mode superposition analysis including:
                - mode_count: Number of dominant modes
                - dominant_frequencies: List of dominant frequencies
                - mode_amplitudes: Amplitudes of dominant modes
        """
        # FFT analysis for mode decomposition
        fft_envelope = np.fft.fftn(envelope)
        power_spectrum = np.abs(fft_envelope) ** 2

        # Find dominant modes
        max_power = np.max(power_spectrum)
        mode_threshold = 0.1 * max_power
        dominant_modes = np.where(power_spectrum > mode_threshold)

        return {
            "mode_count": len(dominant_modes[0]),
            "dominant_frequencies": [float(f) for f in dominant_modes[0][:5]],
            "mode_amplitudes": [
                float(
                    np.mean(
                        power_spectrum[
                            dominant_modes[0][i],
                            dominant_modes[1][i],
                            dominant_modes[2][i],
                        ]
                    )
                )
                for i in range(min(5, len(dominant_modes[0])))
            ],
        }

    def _analyze_field_projections(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze field projections onto different subspaces.

        Physical Meaning:
            Projects the BVP envelope onto different subspaces to
            understand the field structure in spatial and phase
            dimensions separately.

        Mathematical Foundation:
            Spatial projection: P_spatial = ∫ |a(x,φ,t)| dφ dt
            Phase projection: P_phase = ∫ |a(x,φ,t)| dx dt

        Args:
            envelope (np.ndarray): BVP envelope field.

        Returns:
            Dict[str, Any]: Field projection analysis including:
                - spatial_projection_norm: Norm of spatial projection
                - phase_projection_norm: Norm of phase projection
                - projection_ratio: Ratio of spatial to phase projection
        """
        # Project onto spatial dimensions
        spatial_projection = np.sum(np.abs(envelope), axis=(1, 2))

        # Project onto phase dimensions (if available)
        if len(envelope.shape) > 3:
            phase_projection = np.sum(np.abs(envelope), axis=(0, 1, 2))
        else:
            phase_projection = np.array([1.0])

        return {
            "spatial_projection_norm": float(np.linalg.norm(spatial_projection)),
            "phase_projection_norm": float(np.linalg.norm(phase_projection)),
            "projection_ratio": float(
                np.linalg.norm(spatial_projection) / np.linalg.norm(phase_projection)
            ),
        }

    def _analyze_streamlines(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Analyze streamline patterns in the field.

        Physical Meaning:
            Computes field gradients to analyze streamline patterns
            and flow characteristics in the BVP envelope, providing
            insights into the field dynamics and structure.

        Mathematical Foundation:
            Computes divergence: ∇·v = ∂v_x/∂x + ∂v_y/∂y + ∂v_z/∂z
            Computes curl: ∇×v = (∂v_z/∂y - ∂v_y/∂z, ∂v_x/∂z - ∂v_z/∂x, ∂v_y/∂x - ∂v_x/∂y)

        Args:
            envelope (np.ndarray): BVP envelope field.

        Returns:
            Dict[str, Any]: Streamline analysis including:
                - divergence_max: Maximum divergence value
                - divergence_mean: Mean divergence value
                - curl_max: Maximum curl magnitude
                - curl_mean: Mean curl magnitude
        """
        # Compute field gradients for streamline analysis
        grad_x = np.gradient(envelope.real, axis=0)
        grad_y = np.gradient(envelope.real, axis=1)
        grad_z = np.gradient(envelope.real, axis=2)

        # Compute divergence and curl
        divergence = grad_x + grad_y + grad_z
        curl_magnitude = np.sqrt(
            (np.gradient(grad_z, axis=1) - np.gradient(grad_y, axis=2)) ** 2
            + (np.gradient(grad_x, axis=2) - np.gradient(grad_z, axis=0)) ** 2
            + (np.gradient(grad_y, axis=0) - np.gradient(grad_x, axis=1)) ** 2
        )

        return {
            "divergence_max": float(np.max(divergence)),
            "divergence_mean": float(np.mean(divergence)),
            "curl_max": float(np.max(curl_magnitude)),
            "curl_mean": float(np.mean(curl_magnitude)),
        }
