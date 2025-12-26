"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for particle validation.

This module provides the base ParticleValidationBase class with common
initialization and setup methods.
"""

from typing import Dict, Any, Optional

from ...base.model_base import ModelBase


class ParticleValidationBase(ModelBase):
    """
    Base class for particle validation.
    
    Physical Meaning:
        Provides base functionality for validating inverted parameters
        against experimental data and theoretical constraints.
    """
    
    def __init__(
        self,
        inversion_results: Dict[str, Any],
        validation_criteria: Dict[str, Any],
        experimental_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize particle validation.
        
        Args:
            inversion_results: Results from parameter inversion
            validation_criteria: Validation criteria
            experimental_data: Experimental data for validation
        """
        super().__init__()
        self.inversion_results = inversion_results
        self.validation_criteria = validation_criteria
        self.experimental_data = experimental_data or {}
        self.validation_results = {}
        self._setup_validation_parameters()
    
    def _setup_validation_parameters(self) -> None:
        """
        Setup validation parameters.
        
        Physical Meaning:
            Initializes parameters for particle validation,
            including validation thresholds and criteria.
        """
        # Validation thresholds
        self.chi_squared_threshold = self.validation_criteria.get(
            "chi_squared_threshold", 0.05
        )
        self.confidence_level = self.validation_criteria.get("confidence_level", 0.95)
        self.parameter_tolerance = self.validation_criteria.get(
            "parameter_tolerance", 0.01
        )

        # Physical constraints
        self.energy_balance_tolerance = self.validation_criteria.get(
            "energy_balance_tolerance", 0.03
        )
        self.passivity_threshold = self.validation_criteria.get(
            "passivity_threshold", 0.0
        )
        self.em_tolerance = self.validation_criteria.get("em_tolerance", 0.1)

