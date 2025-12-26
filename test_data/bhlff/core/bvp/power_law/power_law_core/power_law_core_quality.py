"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Quality computation methods for power law core analyzer.

This module provides quality computation methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any


class PowerLawCoreQualityMixin:
    """Mixin providing quality computation methods."""
    
    def _calculate_fitting_quality(
        self, region_data: Dict[str, np.ndarray], power_law_fit: Dict[str, float]
    ) -> float:
        """
        Calculate comprehensive quality of power law fit using 7D BVP theory.
        
        Physical Meaning:
            Calculates comprehensive quality of the power law fit based on
            multiple statistical measures, parameter uncertainties, and
            physical constraints from 7D phase field theory.
            
        Mathematical Foundation:
            Combines R-squared, reduced chi-squared, parameter uncertainty,
            and physical constraints for robust quality assessment.
            
        Args:
            region_data (Dict[str, np.ndarray]): Region data.
            power_law_fit (Dict[str, float]): Power law fit parameters.
            
        Returns:
            float: Comprehensive fitting quality score (0-1).
        """
        try:
            # Extract quality metrics from fit results
            r_squared = power_law_fit.get("r_squared", 0.0)
            reduced_chi_squared = power_law_fit.get("reduced_chi_squared", float("inf"))
            parameter_errors = power_law_fit.get("parameter_errors", [0.0, 0.0])
            exponent = power_law_fit.get("exponent", 0.0)
            coefficient = power_law_fit.get("coefficient", 1.0)
            
            # Compute quality based on multiple factors
            quality_factors = []
            
            # R-squared contribution (higher is better)
            r_squared_quality = max(0.0, min(1.0, r_squared))
            quality_factors.append(r_squared_quality)
            
            # Reduced chi-squared contribution (closer to 1 is better)
            if reduced_chi_squared != float("inf"):
                chi_squared_quality = max(
                    0.0, min(1.0, 1.0 / (1.0 + abs(reduced_chi_squared - 1.0)))
                )
                quality_factors.append(chi_squared_quality)
            
            # Parameter uncertainty contribution (lower uncertainty is better)
            if len(parameter_errors) >= 2:
                amplitude_error = parameter_errors[0]
                exponent_error = parameter_errors[1]
                
                # Relative errors
                rel_amplitude_error = amplitude_error / max(abs(coefficient), 1e-10)
                rel_exponent_error = exponent_error / max(abs(exponent), 1e-10)
                
                # Uncertainty quality (lower relative error is better)
                uncertainty_quality = max(
                    0.0,
                    min(1.0, 1.0 / (1.0 + rel_amplitude_error + rel_exponent_error)),
                )
                quality_factors.append(uncertainty_quality)
            
            # Physical constraints for 7D BVP theory
            physical_quality = self._compute_physical_constraints_quality(
                exponent, coefficient
            )
            quality_factors.append(physical_quality)
            
            # Data point contribution
            data_points = len(region_data.get("amplitudes", []))
            data_quality = self._compute_data_points_quality(data_points)
            quality_factors.append(data_quality)
            
            # Compute weighted average of quality factors
            if quality_factors:
                quality = np.mean(quality_factors)
            else:
                quality = 0.0
            
            return max(0.0, min(1.0, quality))
        
        except Exception as e:
            self.logger.error(f"Quality calculation failed: {e}")
            return 0.0
    
    def _compute_r_squared_full(
        self, distances: np.ndarray, amplitudes: np.ndarray, popt: np.ndarray, func
    ) -> float:
        """
        Compute R-squared for power law fit using full 7D BVP theory.
        
        Physical Meaning:
            Computes R-squared coefficient of determination
            for power law fitting quality assessment in 7D phase field theory.
            
        Args:
            distances (np.ndarray): Distance values.
            amplitudes (np.ndarray): Amplitude values.
            popt (np.ndarray): Fitted parameters.
            func: Power law function.
            
        Returns:
            float: R-squared value.
        """
        try:
            # Compute predicted values
            predicted = func(distances, *popt)
            
            # Compute R-squared
            ss_res = np.sum((amplitudes - predicted) ** 2)
            ss_tot = np.sum((amplitudes - np.mean(amplitudes)) ** 2)
            
            if ss_tot == 0:
                return 0.0
            
            r_squared = 1 - (ss_res / ss_tot)
            return max(0.0, min(1.0, r_squared))
        
        except Exception as e:
            self.logger.error(f"R-squared computation failed: {e}")
            return 0.0
    
    def _compute_chi_squared_full(
        self, distances: np.ndarray, amplitudes: np.ndarray, popt: np.ndarray, func
    ) -> float:
        """
        Compute chi-squared statistic for power law fit using 7D BVP theory.
        
        Physical Meaning:
            Computes chi-squared statistic for goodness of fit
            assessment in power law analysis for 7D phase field theory.
            
        Args:
            distances (np.ndarray): Distance values.
            amplitudes (np.ndarray): Amplitude values.
            popt (np.ndarray): Fitted parameters.
            func: Power law function.
            
        Returns:
            float: Chi-squared value.
        """
        try:
            # Compute predicted values
            predicted = func(distances, *popt)
            
            # Compute chi-squared with proper error handling
            chi_squared = np.sum(
                ((amplitudes - predicted) / np.maximum(amplitudes, 1e-10)) ** 2
            )
            
            return float(chi_squared)
        
        except Exception as e:
            self.logger.error(f"Chi-squared computation failed: {e}")
            return float("inf")
    
    def _compute_fitting_quality_full(self, pcov: np.ndarray) -> float:
        """
        Compute fitting quality from covariance matrix using 7D BVP theory.
        
        Physical Meaning:
            Computes fitting quality based on parameter uncertainty
            from covariance matrix analysis for 7D phase field theory.
            
        Args:
            pcov (np.ndarray): Parameter covariance matrix.
            
        Returns:
            float: Fitting quality metric (0-1).
        """
        try:
            # Compute parameter uncertainties
            param_errors = np.sqrt(np.diag(pcov))
            
            # Compute relative uncertainties
            rel_errors = param_errors / np.maximum(np.abs(param_errors), 1e-10)
            
            # Quality based on uncertainty (lower is better)
            quality = 1.0 / (1.0 + np.mean(rel_errors))
            
            return max(0.0, min(1.0, quality))
        
        except Exception as e:
            self.logger.error(f"Fitting quality computation failed: {e}")
            return 0.0
    
    def _compute_physical_constraints_quality(
        self, exponent: float, coefficient: float
    ) -> float:
        """
        Compute quality based on physical constraints for 7D BVP theory.
        
        Physical Meaning:
            Evaluates physical constraints for power law parameters
            based on 7D phase field theory principles.
            
        Args:
            exponent (float): Power law exponent.
            coefficient (float): Power law coefficient.
            
        Returns:
            float: Physical constraints quality (0-1).
        """
        try:
            quality = 1.0
            
            # Check exponent bounds for 7D BVP theory
            if abs(exponent) > 10:  # Unrealistic exponent
                quality *= 0.5
            elif abs(exponent) > 5:  # Questionable exponent
                quality *= 0.8
            
            # Check coefficient bounds
            if coefficient <= 0:  # Invalid coefficient
                quality *= 0.0
            elif coefficient > 100:  # Unrealistic coefficient
                quality *= 0.7
            
            return max(0.0, min(1.0, quality))
        
        except Exception as e:
            self.logger.error(f"Physical constraints quality computation failed: {e}")
            return 0.0
    
    def _compute_data_points_quality(self, data_points: int) -> float:
        """
        Compute quality based on number of data points.
        
        Physical Meaning:
            Evaluates quality based on the number of data points
            available for power law fitting in 7D phase field theory.
            
        Args:
            data_points (int): Number of data points.
            
        Returns:
            float: Data points quality (0-1).
        """
        try:
            if data_points < 3:
                return 0.0
            elif data_points < 5:
                return 0.7
            elif data_points < 10:
                return 0.8
            elif data_points < 20:
                return 0.9
            else:
                return 1.0
        
        except Exception as e:
            self.logger.error(f"Data points quality computation failed: {e}")
            return 0.0

