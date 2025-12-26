"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Boundary analysis package.

This package contains modules for boundary analysis
for Level C test C1 in 7D phase field theory.

Physical Meaning:
    Implements comprehensive boundary analysis for the 7D phase field
    theory, focusing on boundary effects, admittance contrast, and resonance
    mode analysis.

Example:
    >>> from bhlff.models.level_c.boundary import BoundaryAnalysis
    >>> analyzer = BoundaryAnalysis(bvp_core)
    >>> results = analyzer.analyze_single_wall(domain, boundary_params)
"""

from .data_structures import BoundaryGeometry, AdmittanceSpectrum, RadialProfile
from .admittance_analysis import AdmittanceAnalyzer
from .radial_analysis import RadialAnalyzer
