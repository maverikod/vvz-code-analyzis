"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for failure detector.

This module provides the base FailureDetectorBase class with common initialization
and setup logic for failure detection and boundary analysis.
"""

import logging
from typing import Any, Dict


class FailureDetectorBase:
    """
    Base class for failure detection and boundary analysis.
    
    Physical Meaning:
        Provides initialization and shared utilities for detecting
        physical and numerical failures in the 7D phase field theory.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize failure detector.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._setup_logging()
        self._setup_failure_criteria()
    
    def _setup_logging(self) -> None:
        """Setup logging for failure detection."""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _setup_failure_criteria(self) -> None:
        """Setup criteria for failure detection."""
        self.failure_criteria = {
            "passivity_violation": self._check_passivity_violation,
            "singular_mode": self._check_singular_mode,
            "energy_conservation": self._check_energy_conservation,
            "topological_charge": self._check_topological_charge,
            "numerical_stability": self._check_numerical_stability,
        }
