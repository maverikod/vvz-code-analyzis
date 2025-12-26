"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Physical validation decorator for BVP methods.

This module provides decorators for automatic physical validation
of BVP methods and results, ensuring theoretical compliance.
"""

import functools
import numpy as np
from typing import Dict, Any, Callable, Optional
import logging

from .physical_validator import BVPPhysicalValidator


def physical_validation_required(
    domain_shape: tuple, parameters: Dict[str, Any] = None
):
    """
    Decorator for automatic physical validation of BVP methods.

    Physical Meaning:
        Automatically validates that BVP method results satisfy
        physical constraints and theoretical bounds according to
        the 7D phase field theory framework.

    Mathematical Foundation:
        Applies comprehensive validation including:
        - Energy conservation: |E_final - E_initial| < tolerance
        - Causality: |∇φ| ≤ c (speed of light)
        - Phase coherence: |⟨exp(iφ)⟩| ≥ threshold
        - 7D structure preservation: dim(field) = 7
        - Theoretical bounds: E ≤ E_max, |∇φ| ≤ ∇φ_max

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with automatic validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Execute the original function
            result = func(*args, **kwargs)

            # Validate result if it's a dictionary with field data
            if isinstance(result, dict) and "field" in result:
                try:
                    # Initialize validator
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform physical validation
                    physical_result = validator.validate_physical_constraints(result)
                    theoretical_result = validator.validate_theoretical_bounds(result)

                    # Add validation results to the result
                    result["physical_validation"] = physical_result
                    result["theoretical_validation"] = theoretical_result
                    result["validation_summary"] = validator.get_validation_summary(
                        physical_result, theoretical_result
                    )

                    # Log validation results
                    logger = logging.getLogger(__name__)
                    overall_valid = result["validation_summary"]["overall_valid"]
                    logger.info(
                        f"Physical validation {'PASSED' if overall_valid else 'FAILED'}"
                    )

                    if not overall_valid:
                        violations = result["validation_summary"]["total_violations"]
                        warnings = result["validation_summary"]["total_warnings"]
                        logger.warning(
                            f"Validation issues: {violations} violations, {warnings} warnings"
                        )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Physical validation failed: {e}")
                    # Add error to result but don't fail the function
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


def validate_physical_constraints(
    domain_shape: tuple, parameters: Dict[str, Any] = None
):
    """
    Decorator for validating physical constraints only.

    Physical Meaning:
        Validates that results satisfy physical constraints
        without checking theoretical bounds.

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with physical constraints validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, dict) and "field" in result:
                try:
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform only physical constraints validation
                    physical_result = validator.validate_physical_constraints(result)

                    result["physical_validation"] = physical_result

                    logger = logging.getLogger(__name__)
                    constraints_valid = physical_result.get(
                        "physical_constraints_valid", False
                    )
                    logger.info(
                        f"Physical constraints validation {'PASSED' if constraints_valid else 'FAILED'}"
                    )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Physical constraints validation failed: {e}")
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


def validate_theoretical_bounds(domain_shape: tuple, parameters: Dict[str, Any] = None):
    """
    Decorator for validating theoretical bounds only.

    Physical Meaning:
        Validates that results are within theoretical bounds
        without checking physical constraints.

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with theoretical bounds validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, dict) and "field" in result:
                try:
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform only theoretical bounds validation
                    theoretical_result = validator.validate_theoretical_bounds(result)

                    result["theoretical_validation"] = theoretical_result

                    logger = logging.getLogger(__name__)
                    bounds_valid = theoretical_result.get(
                        "theoretical_bounds_valid", False
                    )
                    logger.info(
                        f"Theoretical bounds validation {'PASSED' if bounds_valid else 'FAILED'}"
                    )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Theoretical bounds validation failed: {e}")
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


def validate_energy_conservation(
    domain_shape: tuple, parameters: Dict[str, Any] = None
):
    """
    Decorator for validating energy conservation only.

    Physical Meaning:
        Validates that energy is conserved according to
        the 7D phase field theory framework.

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with energy conservation validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, dict) and "field" in result:
                try:
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform only energy conservation validation
                    energy_result = validator._validate_energy_conservation(
                        result["field"],
                        result.get("energy"),
                        result.get("metadata", {}),
                    )

                    result["energy_validation"] = energy_result

                    logger = logging.getLogger(__name__)
                    energy_valid = energy_result.get("valid", False)
                    logger.info(
                        f"Energy conservation validation {'PASSED' if energy_valid else 'FAILED'}"
                    )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Energy conservation validation failed: {e}")
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


def validate_causality(domain_shape: tuple, parameters: Dict[str, Any] = None):
    """
    Decorator for validating causality constraints only.

    Physical Meaning:
        Validates that results satisfy causality constraints
        according to the 7D phase field theory framework.

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with causality validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, dict) and "field" in result:
                try:
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform only causality validation
                    causality_result = validator._validate_causality(
                        result["field"], result.get("metadata", {})
                    )

                    result["causality_validation"] = causality_result

                    logger = logging.getLogger(__name__)
                    causality_valid = causality_result.get("valid", False)
                    logger.info(
                        f"Causality validation {'PASSED' if causality_valid else 'FAILED'}"
                    )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Causality validation failed: {e}")
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


def validate_7d_structure(domain_shape: tuple, parameters: Dict[str, Any] = None):
    """
    Decorator for validating 7D structure preservation only.

    Physical Meaning:
        Validates that results preserve the 7D phase field
        structure according to the theoretical framework.

    Args:
        domain_shape (tuple): Shape of the computational domain.
        parameters (Dict[str, Any], optional): Validation parameters.

    Returns:
        Callable: Decorated function with 7D structure validation.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            if isinstance(result, dict) and "field" in result:
                try:
                    validator_params = parameters or {}
                    validator = BVPPhysicalValidator(domain_shape, validator_params)

                    # Perform only 7D structure validation
                    structure_result = validator._validate_7d_structure(
                        result["field"], result.get("metadata", {})
                    )

                    result["structure_validation"] = structure_result

                    logger = logging.getLogger(__name__)
                    structure_valid = structure_result.get("valid", False)
                    logger.info(
                        f"7D structure validation {'PASSED' if structure_valid else 'FAILED'}"
                    )

                except Exception as e:
                    logger = logging.getLogger(__name__)
                    logger.error(f"7D structure validation failed: {e}")
                    result["validation_error"] = str(e)

            return result

        return wrapper

    return decorator


class PhysicalValidationMixin:
    """
    Mixin class for adding physical validation capabilities to BVP classes.

    Physical Meaning:
        Provides automatic physical validation capabilities to any BVP class
        that inherits from this mixin, ensuring theoretical compliance.
    """

    def __init__(self, *args, **kwargs):
        """Initialize with physical validation capabilities."""
        super().__init__(*args, **kwargs)
        self._setup_physical_validation()

    def _setup_physical_validation(self):
        """Setup physical validation for the class."""
        if hasattr(self, "domain") and hasattr(self, "parameters"):
            domain_shape = getattr(self.domain, "shape", None)
            if domain_shape is not None:
                self.physical_validator = BVPPhysicalValidator(
                    domain_shape, self.parameters
                )
            else:
                self.physical_validator = None
        else:
            self.physical_validator = None

    def validate_result_physical(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate result using physical constraints.

        Physical Meaning:
            Validates that the result satisfies physical constraints
            according to the 7D phase field theory.

        Args:
            result (Dict[str, Any]): Result to validate.

        Returns:
            Dict[str, Any]: Physical validation results.
        """
        if self.physical_validator is None:
            return {"physical_constraints_valid": True, "constraint_violations": []}

        return self.physical_validator.validate_physical_constraints(result)

    def validate_result_theoretical(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate result using theoretical bounds.

        Physical Meaning:
            Validates that the result is within theoretical bounds
            according to the 7D phase field theory.

        Args:
            result (Dict[str, Any]): Result to validate.

        Returns:
            Dict[str, Any]: Theoretical validation results.
        """
        if self.physical_validator is None:
            return {"theoretical_bounds_valid": True, "bound_violations": []}

        return self.physical_validator.validate_theoretical_bounds(result)

    def validate_result_comprehensive(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate result using both physical constraints and theoretical bounds.

        Physical Meaning:
            Performs comprehensive validation of the result according to
            both physical constraints and theoretical bounds of the
            7D phase field theory.

        Args:
            result (Dict[str, Any]): Result to validate.

        Returns:
            Dict[str, Any]: Comprehensive validation results.
        """
        if self.physical_validator is None:
            return {
                "overall_valid": True,
                "physical_validation": {"physical_constraints_valid": True},
                "theoretical_validation": {"theoretical_bounds_valid": True},
            }

        physical_result = self.validate_result_physical(result)
        theoretical_result = self.validate_result_theoretical(result)

        return self.physical_validator.get_validation_summary(
            physical_result, theoretical_result
        )
