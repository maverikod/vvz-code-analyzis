"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for time stability analyzer.

This module provides the main TimeStabilityAnalyzer facade class that
coordinates all time stability analysis components.
"""

from .time_stability_base import TimeStabilityAnalyzerBase
from .time_stability_simulation import TimeStabilitySimulationMixin
from .time_stability_analysis import TimeStabilityAnalysisMixin
from .time_stability_7d_computations import TimeStability7DComputationsMixin
from .time_stability_7d_metrics import TimeStability7DMetricsMixin
from .time_stability_effects import TimeStabilityEffectsMixin
from .time_stability_resonator import TimeStabilityResonatorMixin


class TimeStabilityAnalyzer(
    TimeStabilityAnalyzerBase,
    TimeStabilitySimulationMixin,
    TimeStabilityAnalysisMixin,
    TimeStability7DComputationsMixin,
    TimeStability7DMetricsMixin,
    TimeStabilityEffectsMixin,
    TimeStabilityResonatorMixin
):
    """
    Facade class for time step stability analysis with all mixins.
    
    Physical Meaning:
        Investigates numerical stability of time integration
        schemes and optimal time step selection.
    """
    pass

