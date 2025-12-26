"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Core Quenches Postulate implementation for BVP framework.

This module implements the core functionality of Postulate 5 of the BVP framework,
which states that BVP field exhibits "quenches" - localized regions where field
amplitude drops significantly, creating energy dumps and phase discontinuities.

Theoretical Background:
    Quenches represent localized energy dissipation events in the BVP field
    where field amplitude drops below critical thresholds. These events
    are essential for understanding field dynamics and energy transport.

Example:
    >>> postulate = QuenchesPostulate(domain, constants)
    >>> results = postulate.apply(envelope)
"""

import numpy as np
from typing import Dict, Any

from ..domain.domain import Domain
from .bvp_constants import BVPConstants
from .bvp_postulate_base import BVPPostulate
from .quench_detector import QuenchDetector
from .quenches_analyzer import QuenchesAnalyzer


class QuenchesPostulate(BVPPostulate):
    """
    Postulate 5: Quenches.

    Physical Meaning:
        BVP field exhibits "quenches" - localized regions where
        field amplitude drops significantly, creating energy dumps.
    """

    def __init__(self, domain: Domain, constants: BVPConstants):
        """
        Initialize quenches postulate.

        Physical Meaning:
            Sets up the postulate with domain and constants for
            detecting and analyzing quench events.

        Args:
            domain (Domain): Computational domain for analysis.
            constants (BVPConstants): BVP physical constants.
        """
        self.domain = domain
        self.constants = constants
        self.quench_threshold = constants.get_quench_parameter("quench_threshold")
        self.energy_dump_threshold = constants.get_quench_parameter(
            "energy_dump_threshold"
        )
        self.min_quench_size = constants.get_quench_parameter("min_quench_size")

        # Initialize helper components
        # Create config for QuenchDetector with CUDA toggle (default: True)
        use_cuda_default = True
        try:
            # Allow overriding via constants if provided
            use_cuda_default = bool(self.constants.get_quench_parameter("use_cuda"))
        except Exception:
            pass

        config = {
            "amplitude_threshold": self.quench_threshold,
            "detuning_threshold": 1e-2,
            "gradient_threshold": 1e-3,
            "use_cuda": use_cuda_default,
        }

        # Prepare 7D domain for detector without allocating giant coordinate grids
        from ..domain.config import SpatialConfig, PhaseConfig, TemporalConfig
        from ..domain.domain_7d import Domain7D

        if isinstance(domain, Domain7D):
            domain_7d = domain
        else:
            # Derive resolutions from provided domain when possible; fall back to safe defaults
            N = getattr(domain, "N", 16)
            N_phi = getattr(domain, "N_phi", 8)
            N_t = getattr(domain, "N_t", 16)
            L = getattr(domain, "L", 1.0)
            T = getattr(domain, "T", 1.0)

            spatial_config = SpatialConfig(L_x=L, L_y=L, L_z=L, N_x=N, N_y=N, N_z=N)
            phase_config = PhaseConfig(N_phi_1=N_phi, N_phi_2=N_phi, N_phi_3=N_phi)
            temporal_config = TemporalConfig(T_max=T, N_t=N_t, dt=T / max(N_t, 1))
            domain_7d = Domain7D(spatial_config, phase_config, temporal_config)

        self.detector = QuenchDetector(domain_7d, config)
        self.analyzer = QuenchesAnalyzer(domain, constants)

    def apply(self, envelope: np.ndarray, **kwargs) -> Dict[str, Any]:
        """
        Apply quenches postulate.

        Physical Meaning:
            Detects and analyzes quench events in the BVP field,
            including energy dumps and phase discontinuities.

        Mathematical Foundation:
            Identifies regions where field amplitude drops below
            critical thresholds and analyzes energy dissipation.

        Args:
            envelope (np.ndarray): BVP envelope to analyze.

        Returns:
            Dict[str, Any]: Results including quench detection,
                energy analysis, and quench validation.
        """
        # Detect quench events
        quench_detection = self.detector.detect_quenches(envelope)

        # Analyze quench properties
        quench_analysis = self.analyzer.analyze_quench_properties(
            envelope, quench_detection
        )

        # Compute energy dumps
        energy_analysis = self.analyzer.analyze_energy_dumps(envelope, quench_detection)

        # Validate quenches
        satisfies_postulate = self._validate_quenches(quench_analysis, energy_analysis)

        return {
            "quench_detection": quench_detection,
            "quench_analysis": quench_analysis,
            "energy_analysis": energy_analysis,
            "satisfies_postulate": satisfies_postulate,
            "postulate_satisfied": satisfies_postulate,
        }

    def _validate_quenches(
        self, quench_analysis: Dict[str, Any], energy_analysis: Dict[str, Any]
    ) -> bool:
        """
        Validate that quenches satisfy the postulate.

        Physical Meaning:
            Checks that detected quenches exhibit the expected
            properties of energy dissipation and phase discontinuities.

        Args:
            quench_analysis (Dict[str, Any]): Quench analysis results.
            energy_analysis (Dict[str, Any]): Energy analysis results.

        Returns:
            bool: True if quenches satisfy the postulate.
        """
        # Check that quenches were detected
        num_quenches = quench_analysis.get("num_quenches", 0)
        if num_quenches == 0:
            return False

        # Check energy dump properties
        energy_dump_ratio = energy_analysis.get("energy_dump_ratio", 0.0)
        if energy_dump_ratio < self.energy_dump_threshold:
            return False

        # Check quench size distribution
        avg_quench_size = quench_analysis.get("avg_quench_size", 0)
        if avg_quench_size < self.min_quench_size:
            return False

        return True
