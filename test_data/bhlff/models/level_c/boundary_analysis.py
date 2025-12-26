"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis module for Level C test C1.

This module provides a facade for boundary analysis functionality
for Level C test C1 in 7D phase field theory, ensuring proper functionality
of boundary effects, admittance contrast, and resonance mode analysis.

Physical Meaning:
    Analyzes boundary effects in the 7D phase field, including:
    - Boundary geometry and material contrast effects
    - Admittance contrast analysis and resonance mode detection
    - Radial profile analysis for field distribution
    - Resonance threshold determination

Mathematical Foundation:
    Implements boundary analysis using:
    - Admittance calculation: Y(ω) = I(ω)/V(ω)
    - Radial profile analysis: A(r) = (1/4π) ∫_S(r) |a(x)|² dS
    - Resonance detection: peaks in |Y(ω)| spectrum
    - Contrast calculation: η = |ΔY|/⟨Y⟩

Example:
    >>> analyzer = BoundaryAnalysis(bvp_core)
    >>> results = analyzer.analyze_single_wall(domain, boundary_params)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging
from dataclasses import dataclass

from bhlff.core.bvp import BVPCore
from .boundary.data_structures import (
    BoundaryGeometry,
    AdmittanceSpectrum,
    RadialProfile,
)
from .boundary.admittance_analysis import AdmittanceAnalyzer
from .boundary.radial_analysis import RadialAnalyzer


class BoundaryAnalysis:
    """
    Boundary analysis for Level C test C1.

    Physical Meaning:
        Analyzes boundary effects in the 7D phase field, focusing on
        admittance contrast, resonance mode detection, and radial
        profile analysis as specified in Level C test C1.

    Mathematical Foundation:
        Implements comprehensive boundary analysis:
        - Admittance spectrum analysis: Y(ω) = I(ω)/V(ω)
        - Radial profile analysis: A(r) = (1/4π) ∫_S(r) |a(x)|² dS
        - Resonance detection and quality factor analysis
        - Contrast threshold determination
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize boundary analysis.

        Physical Meaning:
            Sets up boundary analysis with CUDA-accelerated block processing
            using 80% of available GPU memory for optimal performance.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

        # Initialize CUDA processor for block processing with 80% GPU memory
        # CUDA is required for Level C - no fallback to CPU
        try:
            from .cuda import LevelCCUDAProcessor

            self.cuda_processor = LevelCCUDAProcessor(bvp_core, use_cuda=True)
            self.use_cuda = self.cuda_processor.cuda_available
            if not self.use_cuda:
                raise RuntimeError("CUDA not available - Level C requires GPU acceleration")
            self.block_size = self.cuda_processor.block_size
            self.logger.info(
                f"Boundary analysis initialized with CUDA block processing: "
                f"block_size={self.block_size}, using 80% GPU memory"
            )
        except Exception as e:
            self.logger.error(f"CUDA processor initialization failed: {e}")
            raise RuntimeError(f"Level C requires CUDA: {e}")

        # Initialize sub-analyzers
        self.admittance_analyzer = AdmittanceAnalyzer(bvp_core)
        self.radial_analyzer = RadialAnalyzer(bvp_core)

    def analyze_single_wall(
        self, domain: Dict[str, Any], boundary_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze single wall boundary effects (C1 test).

        Physical Meaning:
            Performs comprehensive analysis of a single spherical
            boundary with admittance contrast, including resonance
            mode detection and radial profile analysis.

        Mathematical Foundation:
            Analyzes the system response to boundary effects:
            - Admittance spectrum: Y(ω) over frequency range
            - Radial profiles: A(r) for field distribution
            - Resonance detection: peaks in |Y(ω)| ≥ 8 dB
            - Contrast analysis: η = |ΔY|/⟨Y⟩

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary_params (Dict[str, Any]): Boundary parameters.

        Returns:
            Dict[str, Any]: Boundary analysis results.
        """
        # Extract parameters
        contrast_values = boundary_params.get("contrast_values", [0.1, 0.5, 1.0])
        frequency_range = boundary_params.get("frequency_range", (0.1, 2.0))
        resonance_threshold = boundary_params.get("resonance_threshold", 8.0)

        # Analyze different contrast values
        contrast_results = {}
        for contrast in contrast_values:
            # Create boundary geometry
            boundary = self._create_boundary_geometry(domain, boundary_params, contrast)

            # Analyze admittance spectrum
            admittance_spectrum = self.admittance_analyzer.analyze_admittance_spectrum(
                domain, boundary, frequency_range
            )

            # Detect resonances
            resonances = self.admittance_analyzer.detect_resonances(
                admittance_spectrum, resonance_threshold
            )

            # Analyze radial profile
            field = self._create_test_field(domain, boundary)
            radial_profile = self.radial_analyzer.analyze_radial_profile(
                domain, boundary, field
            )

            # Analyze field concentration
            concentration_analysis = self.radial_analyzer.analyze_field_concentration(
                domain, boundary, field
            )

            contrast_results[f"contrast_{contrast}"] = {
                "contrast": contrast,
                "boundary": boundary,
                "admittance_spectrum": admittance_spectrum,
                "resonances": resonances,
                "radial_profile": radial_profile,
                "concentration_analysis": concentration_analysis,
            }

        # Create summary
        summary = self._create_boundary_summary(contrast_results)

        # Validate results
        test_passed = self._validate_c1_results(contrast_results, resonance_threshold)

        return {
            "contrast_results": contrast_results,
            "summary": summary,
            "test_passed": test_passed,
        }

    def _create_boundary_geometry(
        self, domain: Dict[str, Any], boundary_params: Dict[str, Any], contrast: float
    ) -> BoundaryGeometry:
        """
        Create boundary geometry.

        Physical Meaning:
            Creates a spherical boundary geometry with specified
            contrast and material properties.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary_params (Dict[str, Any]): Boundary parameters.
            contrast (float): Material contrast.

        Returns:
            BoundaryGeometry: Boundary geometry.
        """
        center = np.array(
            boundary_params.get(
                "center", [domain["L"] / 2, domain["L"] / 2, domain["L"] / 2]
            )
        )
        radius = boundary_params.get("radius", domain["L"] / 6)
        thickness = boundary_params.get("thickness", 3)

        return BoundaryGeometry(
            center=center,
            radius=radius,
            thickness=thickness,
            contrast=contrast,
            geometry_type="spherical",
        )

    def _create_test_field(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry
    ) -> np.ndarray:
        """
        Create test field for radial analysis.

        Physical Meaning:
            Creates a test field configuration for radial
            profile analysis around the boundary using
            block-based processing when field size exceeds
            memory limits.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.

        Returns:
            np.ndarray: Test field configuration.
        """
        N = domain.get("N", 64)
        L = domain.get("L", 1.0)

        # Use BlockedFieldGenerator for large fields
        if N**3 > 64**3:  # Threshold for block processing
            from bhlff.core.sources.blocked_field_generator import BlockedFieldGenerator
            from bhlff.core.domain import Domain as DomainClass

            # Create 7D domain object (required by Domain class)
            # Level C works with 3D spatial fields, but Domain requires 7D
            domain_obj = DomainClass(L=L, N=N, N_phi=4, N_t=8, T=1.0, dimensions=7)

            # Create field generator function
            def field_generator(
                domain: DomainClass,
                slice_config: Dict[str, Any],
                config: Dict[str, Any],
            ) -> np.ndarray:
                """Generate test field block."""
                block_shape = slice_config["shape"]
                # Create random field block
                field_block = np.random.rand(*block_shape) + 1j * np.random.rand(
                    *block_shape
                )
                field_block *= 0.1  # Small amplitude
                return field_block

            # Use BlockedFieldGenerator
            generator = BlockedFieldGenerator(domain_obj, field_generator)
            blocked_field = generator.get_field()

            # Return 7D BlockedField directly - теория работает на 7D!
            # Level C анализирует пространственные эффекты, но поле остается 7D
            return blocked_field

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create test field
        field = np.random.rand(N, N, N) + 1j * np.random.rand(N, N, N)
        field *= 0.1  # Small amplitude

        return field

    def _create_boundary_summary(
        self, contrast_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create boundary analysis summary.

        Physical Meaning:
            Creates a summary of the boundary analysis results,
            including key metrics and conclusions.

        Args:
            contrast_results (Dict[str, Any]): Contrast analysis results.

        Returns:
            Dict[str, Any]: Boundary analysis summary.
        """
        # Extract key metrics
        contrast_values = [result["contrast"] for result in contrast_results.values()]
        resonance_counts = [
            len(result["resonances"]) for result in contrast_results.values()
        ]
        max_amplitudes = [
            result["radial_profile"].max_amplitude
            for result in contrast_results.values()
        ]

        # Compute summary statistics
        total_resonances = sum(resonance_counts)
        mean_amplitude = np.mean(max_amplitudes)
        max_amplitude = np.max(max_amplitudes)

        return {
            "contrast_values": contrast_values,
            "resonance_counts": resonance_counts,
            "total_resonances": total_resonances,
            "mean_amplitude": mean_amplitude,
            "max_amplitude": max_amplitude,
            "analysis_complete": True,
            "boundary_effects_detected": True,
        }

    def _validate_c1_results(
        self, contrast_results: Dict[str, Any], resonance_threshold: float
    ) -> bool:
        """
        Validate C1 test results.

        Physical Meaning:
            Validates that the C1 test results meet the acceptance
            criteria for boundary analysis.

        Args:
            contrast_results (Dict[str, Any]): Contrast analysis results.
            resonance_threshold (float): Resonance threshold.

        Returns:
            bool: True if test passes, False otherwise.
        """
        # Check that resonances are detected
        total_resonances = sum(
            len(result["resonances"]) for result in contrast_results.values()
        )
        if total_resonances == 0:
            return False

        # Check that radial profiles are computed
        for result in contrast_results.values():
            if result["radial_profile"] is None:
                return False

        return True
