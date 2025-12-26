"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for phase envelope balance solver.

This module provides the base PhaseEnvelopeBalanceSolverBase class with common
initialization and setup methods.
"""

import numpy as np
from typing import Dict, Any

from ..gravity_curvature import VBPEnvelopeCurvatureCalculator
from ..cosmology import EnvelopeEffectiveMetric


class PhaseEnvelopeBalanceSolverBase:
    """
    Base class for phase envelope balance solver.
    
    Physical Meaning:
        Provides base functionality for solving phase envelope balance
        equations with VBP envelope dynamics.
    """
    
    def __init__(self, domain: "Domain", params: Dict[str, Any]):
        """
        Initialize phase envelope balance solver.
        
        Args:
            domain: Computational domain
            params: Physical parameters
        """
        self.domain = domain
        self.params = params
        self.curvature_calc = VBPEnvelopeCurvatureCalculator(domain, params)

        # Initialize EnvelopeEffectiveMetric for integration
        self.envelope_metric = EnvelopeEffectiveMetric(params)

        self._setup_envelope_parameters()
    
    def _setup_envelope_parameters(self) -> None:
        """
        Setup parameters for phase envelope balance equations.
        
        Physical Meaning:
            Initializes physical constants and numerical
            parameters for phase envelope balance solution.
        """
        self.c_phi = self.params.get("c_phi", 1.0)  # Phase velocity
        self.chi_kappa = self.params.get("chi_kappa", 1.0)  # Bridge parameter
        self.beta = self.params.get("beta", 0.5)  # Fractional order
        self.mu = self.params.get("mu", 1.0)  # Diffusion coefficient
        self.lambda_param = self.params.get("lambda", self.params.get("lambda_param", 0.0))  # Damping
        self.q = self.params.get("q", 0.0)  # Topological charge
        self.tolerance = self.params.get("tolerance", 1e-12)
        self.max_iterations = self.params.get("max_iterations", 1000)

