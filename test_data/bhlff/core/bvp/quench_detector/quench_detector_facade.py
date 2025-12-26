"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for quench detector.

This module provides the main QuenchDetector facade class that
coordinates all quench detection components.
"""

from .quench_detector_base import QuenchDetectorBase
from .quench_detector_helpers import QuenchDetectorHelpersMixin
from .quench_detector_amplitude import QuenchDetectorAmplitudeMixin
from .quench_detector_detuning import QuenchDetectorDetuningMixin
from .quench_detector_gradient import QuenchDetectorGradientMixin
from .quench_detector_detection import QuenchDetectorDetectionMixin


class QuenchDetector(
    QuenchDetectorBase,
    QuenchDetectorHelpersMixin,
    QuenchDetectorAmplitudeMixin,
    QuenchDetectorDetuningMixin,
    QuenchDetectorGradientMixin,
    QuenchDetectorDetectionMixin
):
    """
    Facade class for quench detector with all mixins.
    
    Physical Meaning:
        Monitors local thresholds (amplitude/detuning/gradient)
        and detects when BVP dissipatively "dumps" energy into
        the medium. Quenches represent threshold events where
        the BVP field undergoes a local regime transition.
        
    Mathematical Foundation:
        Applies three threshold criteria for quench detection:
        1. Amplitude threshold: |A| > |A_q|
        2. Detuning threshold: |ω - ω_0| > Δω_q
        3. Gradient threshold: |∇A| > |∇A_q|
        where A_q, Δω_q, and ∇A_q are the quench thresholds.
    """
    pass

