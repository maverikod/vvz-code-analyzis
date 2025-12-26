"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Anomalous dimension (eta) estimation for 7D BVP fields.

Computes η from the decay of the 7D correlation function using
log–log slope of radial correlation vs distance.
"""

from __future__ import annotations

from typing import Any
import numpy as np


def compute_anomalous_dimension(bvp_core: Any, amplitude: np.ndarray) -> float:
    """
    Compute anomalous dimension η from correlation decay.

    Physical Meaning:
        Fits C(r) ~ r^{-(d-2+η)} with d=7 using the slope on log–log axes.
    """
    from .correlation_analysis import CorrelationAnalysis

    correlation_analyzer = CorrelationAnalysis(bvp_core)
    correlation_7d = correlation_analyzer._compute_7d_correlation_function(amplitude)
    correlation_decay = correlation_analyzer._compute_correlation_decay(correlation_7d)
    radial_corr = np.array(correlation_decay["radial_correlation"])

    if len(radial_corr) > 1:
        distances = np.arange(len(radial_corr))
        distances = distances[distances > 0]
        radial_corr = radial_corr[distances]
        if len(distances) > 1 and np.all(radial_corr > 0):
            log_dist = np.log(distances)
            log_corr = np.log(radial_corr)
            if len(log_dist) > 1:
                slope = np.polyfit(log_dist, log_corr, 1)[0]
                eta = -slope - 5  # d-2 = 5 for d=7
            else:
                eta = 0.0
        else:
            eta = 0.0
    else:
        eta = 0.0

    return float(max(-1.0, min(1.0, eta)))
