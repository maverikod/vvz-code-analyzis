"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP impedance calculator module.

This module implements the calculation of impedance/admittance from BVP
envelope, providing frequency response analysis and resonance detection
capabilities.

Physical Meaning:
    Calculates Y(ω), R(ω), T(ω), and peaks {ω_n,Q_n} from the BVP
    envelope at boundaries, representing the frequency response
    characteristics of the system.

Mathematical Foundation:
    Computes boundary functions from envelope:
    - Admittance Y(ω) = I(ω)/V(ω)
    - Reflection coefficient R(ω)
    - Transmission coefficient T(ω)
    - Resonance peaks {ω_n,Q_n}

Example:
    >>> calculator = BVPImpedanceCalculator(domain, config)
    >>> impedance_data = calculator.compute_impedance(envelope)
"""

import numpy as np
from typing import Dict, Any

from ..domain import Domain
from .impedance_core import ImpedanceCore
from .resonance_detector import ResonanceDetector
from .bvp_constants import BVPConstants


class BVPImpedanceCalculator:
    """
    Calculator for BVP impedance and admittance.

    Physical Meaning:
        Computes frequency-dependent impedance characteristics from
        the BVP envelope, including admittance, reflection/transmission
        coefficients, and resonance peaks.

    Mathematical Foundation:
        Computes boundary functions from envelope:
        - Admittance Y(ω) = I(ω)/V(ω)
        - Reflection coefficient R(ω)
        - Transmission coefficient T(ω)
        - Resonance peaks {ω_n,Q_n}

    Attributes:
        domain (Domain): Computational domain.
        config (Dict[str, Any]): Impedance calculation configuration.
        _impedance_core (ImpedanceCore): Core impedance calculations.
        _resonance_detector (ResonanceDetector): Resonance peak detection.
    """

    def __init__(
        self, domain: Domain, config: Dict[str, Any], constants: BVPConstants = None
    ) -> None:
        """
        Initialize impedance calculator.

        Physical Meaning:
            Sets up the calculator with configuration for frequency
            response analysis and resonance detection.

        Args:
            domain (Domain): Computational domain for impedance calculations.
            config (Dict[str, Any]): Impedance calculation configuration including:
                - frequency_range: Frequency range for analysis
                - frequency_points: Number of frequency points
                - boundary_conditions: Boundary condition type
                - quality_factor_threshold: Threshold for quality factor
            constants (BVPConstants, optional): BVP constants instance.
        """
        self.domain = domain
        self.config = config
        self.constants = constants or BVPConstants(config)
        self._setup_components()

    def _setup_components(self) -> None:
        """
        Setup impedance calculation components.

        Physical Meaning:
            Initializes the core impedance calculation and resonance
            detection components.
        """
        self._impedance_core = ImpedanceCore(self.domain, self.config, self.constants)
        self._resonance_detector = ResonanceDetector(self.constants)

        # Set quality factor threshold from constants
        quality_threshold = self.constants.get_impedance_parameter(
            "quality_factor_threshold"
        )
        self._resonance_detector.set_quality_factor_threshold(quality_threshold)

    def compute_impedance(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Compute impedance/admittance from BVP envelope.

        Physical Meaning:
            Calculates Y(ω), R(ω), T(ω), and peaks {ω_n,Q_n}
            from the BVP envelope at boundaries.

        Mathematical Foundation:
            Computes boundary functions from envelope:
            - Admittance Y(ω) = I(ω)/V(ω)
            - Reflection coefficient R(ω)
            - Transmission coefficient T(ω)
            - Resonance peaks {ω_n,Q_n}

        Args:
            envelope (np.ndarray): BVP envelope a(x) to analyze.

        Returns:
            Dict[str, Any]: Impedance analysis results including:
                - admittance: Y(ω) frequency response
                - reflection: R(ω) reflection coefficient
                - transmission: T(ω) transmission coefficient
                - peaks: {ω_n,Q_n} resonance peaks
        """
        # Create frequency array
        frequency_range = self._impedance_core.frequency_range
        frequency_points = self._impedance_core.frequency_points
        frequencies = np.linspace(
            frequency_range[0], frequency_range[1], frequency_points
        )

        # Compute admittance Y(ω) from envelope using core operations
        admittance = self._impedance_core.compute_admittance_from_envelope(
            envelope, frequencies
        )

        # Compute reflection and transmission coefficients
        reflection = self._impedance_core.compute_reflection_coefficient(admittance)
        transmission = self._impedance_core.compute_transmission_coefficient(admittance)

        # Find resonance peaks using advanced detection algorithms
        peaks = self._resonance_detector.find_resonance_peaks(frequencies, admittance)

        return {
            "admittance": admittance,
            "reflection": reflection,
            "transmission": transmission,
            "peaks": peaks,
        }

    def get_parameters(self) -> Dict[str, Any]:
        """
        Get impedance calculation parameters.

        Physical Meaning:
            Returns the current parameters for impedance calculation.

        Returns:
            Dict[str, Any]: Impedance calculation parameters.
        """
        core_params = self._impedance_core.get_parameters()
        core_params["quality_factor_threshold"] = (
            self._resonance_detector.get_quality_factor_threshold()
        )
        return core_params

    def set_quality_factor_threshold(self, threshold: float) -> None:
        """
        Set quality factor threshold.

        Physical Meaning:
            Updates the threshold for quality factor filtering
            in resonance detection.

        Args:
            threshold (float): New quality factor threshold.
        """
        self._resonance_detector.set_quality_factor_threshold(threshold)

    def get_impedance_core(self) -> ImpedanceCore:
        """
        Get impedance core component.

        Physical Meaning:
            Returns the core impedance calculation component
            for advanced operations.

        Returns:
            ImpedanceCore: Core impedance calculation component.
        """
        return self._impedance_core

    def get_resonance_detector(self) -> ResonanceDetector:
        """
        Get resonance detector component.

        Physical Meaning:
            Returns the resonance detection component
            for advanced peak analysis.

        Returns:
            ResonanceDetector: Resonance detection component.
        """
        return self._resonance_detector

    def __repr__(self) -> str:
        """String representation of impedance calculator."""
        params = self.get_parameters()
        return (
            f"BVPImpedanceCalculator(domain={self.domain}, "
            f"freq_range={params['frequency_range']}, "
            f"freq_points={params['frequency_points']})"
        )
