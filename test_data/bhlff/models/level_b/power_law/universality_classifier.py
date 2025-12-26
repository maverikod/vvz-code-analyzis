"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Universality class classifier for critical exponents.

This module implements classification of universality classes based on
critical exponent values.

Physical Meaning:
    Determines universality class from critical exponents by comparing
    with known values from theoretical models.
"""

from typing import Dict


class UniversalityClassifier:
    """
    Universality class classifier.

    Physical Meaning:
        Classifies universality class from critical exponents by comparing
        with known theoretical values.
    """

    @staticmethod
    def determine_universality_class(critical_exponents: Dict[str, float]) -> str:
        """
        Determine universality class from critical exponents.

        Physical Meaning:
            Determines universality class by comparing computed critical
            exponents with known theoretical values from different models.

        Args:
            critical_exponents (Dict[str, float]): Dictionary of critical exponents.

        Returns:
            str: Universality class identifier.
        """
        # Compare with known universality classes
        nu = critical_exponents.get("nu", 0.5)
        beta = critical_exponents.get("beta", 0.5)
        gamma = critical_exponents.get("gamma", 1.0)
        # eta is not directly used for class determination here

        # Mean field values
        if abs(nu - 0.5) < 0.1 and abs(beta - 0.5) < 0.1 and abs(gamma - 1.0) < 0.1:
            return "mean_field"

        # Ising-like values
        elif abs(nu - 0.63) < 0.1 and abs(beta - 0.33) < 0.1:
            return "ising_3d"

        # XY-like values
        elif abs(nu - 0.67) < 0.1 and abs(beta - 0.35) < 0.1:
            return "xy_3d"

        # Custom 7D values
        else:
            return "custom_7d"

