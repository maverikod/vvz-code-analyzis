"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Level D models for multimode superposition and field projections.

This module implements the main Level D models class that coordinates
multimode superposition analysis, field projections onto different
interaction windows, and phase streamline analysis.

Physical Meaning:
    Level D represents the multimode superposition and field projection level
    where all observed particles (electrons, protons, neutrinos) emerge as
    envelope functions of a high-frequency carrier field through different
    frequency-amplitude windows corresponding to electromagnetic, strong,
    and weak interactions.

Mathematical Foundation:
    - Multimode superposition: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
    - Field projections: P_EM[a], P_STRONG[a], P_WEAK[a] for different
      frequency windows
    - Phase streamlines: Analysis of ∇φ flow patterns around defects

Example:
    >>> from bhlff.models.level_d import LevelDModels
    >>> models = LevelDModels(domain, parameters)
    >>> results = models.analyze_multimode_field(field)
"""

import numpy as np
from typing import Dict, Any, List, Optional, Tuple
import logging

from bhlff.models.base.abstract_models import AbstractLevelModels
from .superposition import MultiModeModel, SuperpositionAnalyzer
from .projections import FieldProjection, ProjectionAnalyzer
from .streamlines import StreamlineAnalyzer

# Try to import CUDA-optimized versions
try:
    from .cuda.superposition_cuda import (
        MultiModeModelCUDA,
        SuperpositionAnalyzerCUDA,
    )
    from .cuda.projections_cuda import (
        FieldProjectionCUDA,
        ProjectionAnalyzerCUDA,
    )
    from .cuda.streamlines_cuda import StreamlineAnalyzerCUDA

    CUDA_MODULES_AVAILABLE = True
except ImportError:
    CUDA_MODULES_AVAILABLE = False

from bhlff.utils.cuda_utils import CUDA_AVAILABLE


class LevelDModels(AbstractLevelModels):
    """
    Level D models for multimode superposition and field projections.

    Physical Meaning:
        Implements multimode superposition analysis, field projections
        onto different interaction windows (electromagnetic, strong, weak),
        and phase streamline analysis for the 7D phase field theory.

    Mathematical Foundation:
        - Multimode superposition: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
        - Field projections: P_EM[a], P_STRONG[a], P_WEAK[a] for different
          frequency windows corresponding to different interaction types
        - Phase streamlines: Analysis of ∇φ flow patterns around defects

    Attributes:
        domain (Domain): Computational domain for simulations
        parameters (Dict): Model parameters and window settings
        _superposition_model (MultiModeModel): Multimode superposition model
        _projection_analyzer (ProjectionAnalyzer): Field projection analyzer
        _streamline_analyzer (StreamlineAnalyzer): Phase streamline analyzer
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """
        Initialize Level D models.

        Physical Meaning:
            Sets up the multimode superposition and field projection
            models for analyzing the unified phase field structure
            and its interaction windows.

        Args:
            domain (Domain): Computational domain
            parameters (Dict): Model parameters including window settings
        """
        super().__init__(domain, parameters)
        self.logger = logging.getLogger(__name__)

        # Use CUDA versions if available, otherwise fall back to CPU
        use_cuda = CUDA_MODULES_AVAILABLE and CUDA_AVAILABLE
        if use_cuda:
            try:
                self._superposition_analyzer = SuperpositionAnalyzerCUDA(
                    domain, parameters
                )
                self._projection_analyzer = ProjectionAnalyzerCUDA(domain, parameters)
                self._streamline_analyzer = StreamlineAnalyzerCUDA(domain, parameters)
                self._multimode_model = MultiModeModelCUDA(domain, parameters)
                self.logger.info("Level D models initialized with CUDA acceleration")
            except Exception as e:
                self.logger.warning(
                    f"CUDA initialization failed: {e}, falling back to CPU"
                )
                use_cuda = False

        if not use_cuda:
            # Initialize CPU versions
            self._superposition_analyzer = SuperpositionAnalyzer(domain, parameters)
            self._projection_analyzer = ProjectionAnalyzer(domain, parameters)
            self._streamline_analyzer = StreamlineAnalyzer(domain, parameters)
            self._multimode_model = MultiModeModel(domain, parameters)
            self.logger.info("Level D models initialized with CPU processing")

    def create_multi_mode_field(
        self, base_field: np.ndarray, modes: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Create multi-mode field from base field and additional modes.

        Physical Meaning:
            Constructs a multi-mode phase field by superposing
            different frequency components, representing the
            complex structure of the unified field.

        Mathematical Foundation:
            Multi-mode field: a(x,t) = Σ_m A_m(T) φ_m(x) e^(-iω_m t)
            where A_m are mode amplitudes, φ_m are spatial modes,
            and ω_m are mode frequencies.

        Args:
            base_field (np.ndarray): Base field structure
            modes (List[Dict]): List of mode parameters with keys:
                - frequency: Mode frequency
                - amplitude: Mode amplitude
                - phase: Mode phase
                - spatial_mode: Spatial mode type

        Returns:
            np.ndarray: Multi-mode field
        """
        return self._multimode_model.create_multi_mode_field(base_field, modes)

    def analyze_mode_superposition(
        self, field: np.ndarray, new_modes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze mode superposition on the frame.

        Physical Meaning:
            Tests the stability of the phase field frame when
            adding new modes, ensuring topological robustness
            of the underlying field structure.

        Mathematical Foundation:
            Computes Jaccard index between frame maps before and
            after mode addition, and analyzes frequency stability
            of spectral peaks.

        Args:
            field (np.ndarray): Base field
            new_modes (List[Dict]): New modes to add

        Returns:
            Dict: Analysis results including:
                - jaccard_index: Frame stability metric (0-1)
                - frequency_stability: Frequency shift analysis
                - frame_before: Frame structure before mode addition
                - frame_after: Frame structure after mode addition
                - passed: Whether stability criteria are met
        """
        return self._superposition_analyzer.analyze_mode_superposition(field, new_modes)

    def project_field_windows(
        self, field: np.ndarray, window_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Project fields onto different frequency-amplitude windows.

        Physical Meaning:
            Separates the unified phase field into different
            interaction regimes based on frequency and amplitude
            characteristics corresponding to electromagnetic,
            strong, and weak interactions.

        Mathematical Foundation:
            Uses frequency-domain filtering to separate different
            interaction regimes:
            - EM: P_EM[a] = FFT⁻¹[FFT(a) × H_EM(ω)]
            - Strong: P_STRONG[a] = FFT⁻¹[FFT(a) × H_STRONG(ω)]
            - Weak: P_WEAK[a] = FFT⁻¹[FFT(a) × H_WEAK(ω)]

        Args:
            field (np.ndarray): Input field
            window_params (Dict): Window parameters for each interaction type

        Returns:
            Dict: Projected fields and signatures including:
                - em_projection: Electromagnetic field projection
                - strong_projection: Strong interaction projection
                - weak_projection: Weak interaction projection
                - signatures: Characteristic signatures for each field type
        """
        return self._projection_analyzer.project_field_windows(field, window_params)

    def trace_phase_streamlines(
        self, field: np.ndarray, center: Tuple[float, ...]
    ) -> Dict[str, Any]:
        """
        Trace phase streamlines around defects.

        Physical Meaning:
            Computes streamlines of the phase gradient field,
            revealing the topological structure of phase flow
            around defects and singularities.

        Mathematical Foundation:
            Integrates the phase gradient field to find
            streamlines that are tangent to the gradient
            at each point: dx/dt = ∇φ(x)

        Args:
            field (np.ndarray): Input field
            center (Tuple): Center point for streamline tracing

        Returns:
            Dict: Streamline analysis results including:
                - phase: Field phase
                - phase_gradient: Phase gradient field
                - streamlines: Computed streamlines
                - topology: Topological analysis of streamlines
        """
        return self._streamline_analyzer.trace_phase_streamlines(field, center)

    def analyze_multimode_field(self, field: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Comprehensive analysis of multimode field.

        Physical Meaning:
            Performs complete analysis of a multimode field including
            superposition analysis, field projections, and streamline
            analysis to understand the field structure and dynamics.

        Args:
            field (np.ndarray): Input multimode field
            **kwargs: Analysis parameters

        Returns:
            Dict: Comprehensive analysis results
        """
        self.logger.info("Starting comprehensive multimode field analysis")

        # Extract analysis parameters
        mode_threshold = kwargs.get("mode_threshold", 0.1)
        window_params = kwargs.get("window_params", self._get_default_window_params())
        center = kwargs.get("center", tuple(d / 2 for d in field.shape))

        # Perform superposition analysis
        superposition_results = self._superposition_analyzer.analyze_superposition(
            field, mode_threshold
        )

        # Perform field projection analysis
        projection_results = self._projection_analyzer.project_field_windows(
            field, window_params
        )

        # Perform streamline analysis
        streamline_results = self._streamline_analyzer.trace_phase_streamlines(
            field, center
        )

        # Combine results
        results = {
            "superposition": superposition_results,
            "projections": projection_results,
            "streamlines": streamline_results,
            "field_shape": field.shape,
            "analysis_parameters": kwargs,
        }

        self.logger.info("Multimode field analysis completed")
        return results

    def _get_default_window_params(self) -> Dict[str, Any]:
        """
        Get default window parameters for field projections.

        Returns:
            Dict: Default window parameters
        """
        return {
            "em": {
                "frequency_range": [0.1, 1.0],
                "amplitude_threshold": 0.1,
                "filter_type": "bandpass",
            },
            "strong": {
                "frequency_range": [1.0, 10.0],
                "q_threshold": 100,
                "filter_type": "high_q",
            },
            "weak": {
                "frequency_range": [0.01, 0.1],
                "q_threshold": 10,
                "filter_type": "chiral",
            },
        }

    def validate_field(self, field: np.ndarray) -> bool:
        """
        Validate field for Level D analysis.

        Physical Meaning:
            Checks if the field is suitable for Level D analysis,
            including proper shape, finite values, and appropriate
            frequency content.

        Args:
            field (np.ndarray): Field to validate

        Returns:
            bool: True if field is valid
        """
        # Check shape compatibility
        if field.shape != self.domain.shape:
            self.logger.error(
                f"Field shape {field.shape} incompatible with domain shape {self.domain.shape}"
            )
            return False

        # Check for finite values
        if not np.all(np.isfinite(field)):
            self.logger.error("Field contains non-finite values")
            return False

        # Check for non-zero field
        if np.allclose(field, 0):
            self.logger.warning("Field is identically zero")
            return False

        return True

    def analyze_field(self, field: np.ndarray) -> Dict[str, Any]:
        """
        Analyze field for Level D.

        Physical Meaning:
            Performs comprehensive Level D analysis of the phase field,
            including multimode superposition, field projections, and
            streamline analysis.

        Mathematical Foundation:
            Implements Level D mathematical operations for analyzing
            the multimode structure and field projections of the phase field.

        Args:
            field (np.ndarray): Input phase field

        Returns:
            Dict: Analysis results
        """
        return self.analyze_multimode_field(field)
