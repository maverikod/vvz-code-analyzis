"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Experiments module for Level E models.

This module provides tools for running and managing experiments on defect systems,
including experiment runners and specialized experiment configurations.

Physical Meaning:
    Experiments module enables systematic investigation of defect behavior
    through controlled numerical experiments, allowing exploration of
    parameter space and validation of theoretical predictions.

Mathematical Foundation:
    Experiments involve solving the phase field equations for different
    parameter configurations and analyzing the resulting solutions to
    understand system behavior and validate theoretical models.
"""

from .experiment_runner import ExperimentRunner
from .specialized_experiments import SpecializedExperiments
