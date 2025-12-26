"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

BVP parameter access module.

This module provides parameter access methods for the BVP core,
including access to envelope parameters, quench thresholds, and impedance settings.

Physical Meaning:
    Provides access to BVP configuration parameters including
    envelope equation parameters, quench detection thresholds,
    and impedance calculation settings.

Mathematical Foundation:
    Provides access to parameters for:
    - Envelope equation: κ₀, κ₂, χ', χ''
    - Quench detection: amplitude, detuning, gradient thresholds
    - Impedance calculation: frequency range, resolution

Example:
    >>> param_access = BVPParameterAccess(bvp_core)
    >>> carrier_freq = param_access.get_carrier_frequency()
    >>> envelope_params = param_access.get_envelope_parameters()
"""

from typing import Dict, Any

from .bvp_envelope_solver import BVPEnvelopeSolver
from .quench_detector import QuenchDetector
from .bvp_impedance_calculator import BVPImpedanceCalculator
from .bvp_constants import BVPConstants


class BVPParameterAccess:
    """
    Parameter access for BVP core.

    Physical Meaning:
        Provides access to BVP configuration parameters including
        envelope equation parameters, quench detection thresholds,
        and impedance calculation settings.

    Mathematical Foundation:
        Provides access to parameters for:
        - Envelope equation: κ₀, κ₂, χ', χ''
        - Quench detection: amplitude, detuning, gradient thresholds
        - Impedance calculation: frequency range, resolution
    """

    def __init__(
        self,
        constants: BVPConstants,
        envelope_solver: BVPEnvelopeSolver,
        quench_detector: QuenchDetector,
        impedance_calculator: BVPImpedanceCalculator,
    ):
        """
        Initialize parameter access.

        Physical Meaning:
            Sets up parameter access with references to BVP components
            that contain the configuration parameters.

        Args:
            constants (BVPConstants): BVP physical constants.
            envelope_solver (BVPEnvelopeSolver): Envelope equation solver.
            quench_detector (QuenchDetector): Quench event detector.
            impedance_calculator (BVPImpedanceCalculator): Impedance calculator.
        """
        self.constants = constants
        self.envelope_solver = envelope_solver
        self.quench_detector = quench_detector
        self.impedance_calculator = impedance_calculator

    def get_carrier_frequency(self) -> float:
        """
        Get the high-frequency carrier frequency.

        Physical Meaning:
            Returns the frequency ω₀ of the high-frequency carrier
            that is modulated by the envelope.

        Returns:
            float: Carrier frequency ω₀.
        """
        return self.constants.get_envelope_parameter("carrier_frequency")

    def get_envelope_parameters(self) -> Dict[str, float]:
        """
        Get envelope equation parameters.

        Physical Meaning:
            Returns the parameters κ₀, κ₂, χ', χ'' for the
            envelope equation.

        Returns:
            Dict[str, float]: Envelope equation parameters.
        """
        return self.envelope_solver.get_parameters()

    def get_quench_thresholds(self) -> Dict[str, float]:
        """
        Get quench detection thresholds.

        Physical Meaning:
            Returns the current threshold values used for quench detection.

        Returns:
            Dict[str, float]: Quench detection thresholds.
        """
        return self.quench_detector.get_thresholds()

    def set_quench_thresholds(self, thresholds: Dict[str, float]) -> None:
        """
        Set new quench detection thresholds.

        Physical Meaning:
            Updates the threshold values used for quench detection.

        Args:
            thresholds (Dict[str, float]): New threshold values.
        """
        self.quench_detector.set_thresholds(thresholds)

    def get_impedance_parameters(self) -> Dict[str, Any]:
        """
        Get impedance calculation parameters.

        Physical Meaning:
            Returns the current parameters for impedance calculation.

        Returns:
            Dict[str, Any]: Impedance calculation parameters.
        """
        return self.impedance_calculator.get_parameters()
