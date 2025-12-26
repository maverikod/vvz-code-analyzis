"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Compatibility shim for BeatingMLPredictionCore import path.

This module re-exports BeatingMLPredictionCore from the nested
beating_ml_prediction package so legacy imports continue to work:

    from bhlff.models.level_c.beating.ml.beating_ml_prediction_core import BeatingMLPredictionCore
"""

from .beating_ml_prediction.beating_ml_prediction_core import BeatingMLPredictionCore

__all__ = ["BeatingMLPredictionCore"]
