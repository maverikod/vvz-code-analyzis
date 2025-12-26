"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Facade class for beating ML patterns old.

This module provides the main BeatingMLPatterns facade class that
coordinates all beating ML pattern classification components.
"""

from .beating_ml_patterns_old_base import BeatingMLPatternsBase
from .beating_ml_patterns_old_classification import BeatingMLPatternsOldClassificationMixin
from .beating_ml_patterns_old_scores import BeatingMLPatternsOldScoresMixin
from .beating_ml_patterns_old_7d_computations import BeatingMLPatternsOld7DComputationsMixin
from .beating_ml_patterns_old_vbp_computations import BeatingMLPatternsOldVBPComputationsMixin
from .beating_ml_patterns_old_helpers import BeatingMLPatternsOldHelpersMixin


class BeatingMLPatterns(
    BeatingMLPatternsBase,
    BeatingMLPatternsOldClassificationMixin,
    BeatingMLPatternsOldScoresMixin,
    BeatingMLPatternsOld7DComputationsMixin,
    BeatingMLPatternsOldVBPComputationsMixin,
    BeatingMLPatternsOldHelpersMixin
):
    """
    Facade class for machine learning pattern classification with all mixins.
    
    Physical Meaning:
        Provides machine learning-based pattern classification functions
        for analyzing beating patterns in the 7D phase field.
        
    Mathematical Foundation:
        Uses machine learning techniques for pattern recognition and classification
        of beating modes and their characteristics.
    """
    pass

