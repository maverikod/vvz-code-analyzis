"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Projection analyzer for field projections.

This module provides ProjectionAnalyzer class.
"""

import numpy as np
from typing import Dict, Any, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .projections_facade import FieldProjection


class ProjectionAnalyzer:
    """
    Analyzer for field projections onto interaction windows.
    
    Physical Meaning:
        Analyzes field projections onto different interaction
        windows to understand the field structure and dynamics
        in different interaction regimes.
    """

    def __init__(self, domain: "Domain", parameters: Dict[str, Any]):
        """Initialize projection analyzer."""
        self.domain = domain
        self.parameters = parameters
        self.logger = logging.getLogger(__name__)

    def project_field_windows(
        self, field: np.ndarray, window_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Project fields onto different frequency-amplitude windows.
        
        Physical Meaning:
            Separates the unified phase field into different
            interaction regimes based on frequency and amplitude
            characteristics.
        """
        # Create field projection (lazy import to avoid circular dependency)
        from .projections_facade import FieldProjection
        projection = FieldProjection(field, window_params)

        # Perform projections
        results = projection.project_field_windows(field)

        return results

