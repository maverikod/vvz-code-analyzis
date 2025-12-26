"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for field projections.

This module provides the base FieldProjectionBase class with common
initialization and setup methods.
"""

import numpy as np
from typing import Dict, Any
import logging

from .projections_projectors import EMProjector, StrongProjector, WeakProjector
from .projections_signature import SignatureAnalyzer


class FieldProjectionBase:
    """
    Base class for field projection onto different interaction windows.
    
    Physical Meaning:
        Provides base functionality for projecting the unified phase field
        onto different frequency windows corresponding to electromagnetic,
        strong, and weak interactions.
    """
    
    def __init__(self, field: np.ndarray, projection_params: Dict[str, Any]):
        """
        Initialize field projection.
        
        Args:
            field: Input phase field
            projection_params: Projection parameters
        """
        self.field = field
        self.projection_params = projection_params
        self.logger = logging.getLogger(__name__)

        # Initialize projectors
        self._em_projector = EMProjector(projection_params.get("em", {}))
        self._strong_projector = StrongProjector(projection_params.get("strong", {}))
        self._weak_projector = WeakProjector(projection_params.get("weak", {}))

        # Initialize signature analyzer
        self._signature_analyzer = SignatureAnalyzer()

        self.logger.info("Field projection initialized")

