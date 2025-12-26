"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quench memory analysis package.

This package contains modules for quench memory analysis
for Level C test C3 in 7D phase field theory.

Physical Meaning:
    Implements comprehensive analysis of quench memory effects
    in the 7D phase field theory, including memory formation,
    pinning effects, and field stabilization.

Example:
    >>> from bhlff.models.level_c.memory import QuenchMemoryAnalysis
    >>> analyzer = QuenchMemoryAnalysis(bvp_core)
    >>> results = analyzer.analyze_quench_memory(domain, memory_params)
"""

from .data_structures import MemoryParameters, QuenchEvent, MemoryKernel, MemoryState
from .memory_evolution import MemoryEvolutionAnalyzer
from .pinning_analysis import PinningAnalyzer
from .correlation_analysis import CorrelationAnalyzer
