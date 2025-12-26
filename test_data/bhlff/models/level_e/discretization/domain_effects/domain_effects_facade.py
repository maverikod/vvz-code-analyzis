"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for domain effects analyzer.

This module provides the main DomainEffectsAnalyzer facade class that
coordinates all domain effects analyzer components.
"""

from .domain_effects_base import DomainEffectsAnalyzerBase
from .domain_effects_analysis import DomainEffectsAnalyzerAnalysisMixin
from .domain_effects_simulation import DomainEffectsAnalyzerSimulationMixin
from .domain_effects_7d_computations import DomainEffectsAnalyzer7DComputationsMixin
from .domain_effects_helpers import DomainEffectsAnalyzerHelpersMixin


class DomainEffectsAnalyzer(
    DomainEffectsAnalyzerBase,
    DomainEffectsAnalyzerAnalysisMixin,
    DomainEffectsAnalyzerSimulationMixin,
    DomainEffectsAnalyzer7DComputationsMixin,
    DomainEffectsAnalyzerHelpersMixin
):
    """
    Facade class for domain effects analyzer with all mixins.
    
    Physical Meaning:
        Investigates how the finite computational domain
        affects results, particularly for long-range
        interactions and boundary effects.
    """
    pass

