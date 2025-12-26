"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Radial analysis concentration module.

This module implements field concentration analysis functionality for radial analysis
in Level C test C1 of 7D phase field theory.

Physical Meaning:
    Analyzes field concentration patterns for boundary effects,
    including near-boundary and far-boundary concentration analysis.

Example:
    >>> concentration_analyzer = RadialConcentrationAnalyzer(bvp_core)
    >>> results = concentration_analyzer.analyze_field_concentration(domain, boundary, field)
"""

import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

from bhlff.core.bvp import BVPCore
from .data_structures import BoundaryGeometry, RadialProfile


class RadialConcentrationAnalyzer:
    """
    Radial concentration analyzer for boundary effects.

    Physical Meaning:
        Analyzes field concentration patterns for boundary effects,
        including near-boundary and far-boundary concentration analysis.

    Mathematical Foundation:
        Implements concentration analysis:
        - Field concentration analysis
        - Near-boundary concentration analysis
        - Far-boundary concentration analysis
    """

    def __init__(self, bvp_core: BVPCore):
        """
        Initialize radial concentration analyzer.

        Physical Meaning:
            Sets up the concentration analysis system with
            appropriate parameters and methods.

        Args:
            bvp_core (BVPCore): BVP core framework instance.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)

    def analyze_field_concentration(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze field concentration.

        Physical Meaning:
            Analyzes field concentration patterns for boundary effects
            including near-boundary and far-boundary concentration.

        Mathematical Foundation:
            Analyzes concentration patterns through:
            - Near-boundary concentration analysis
            - Far-boundary concentration analysis
            - Overall concentration pattern analysis

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Field concentration analysis results.
        """
        self.logger.info("Starting field concentration analysis")

        # Analyze near-boundary concentration
        near_boundary_concentration = self._analyze_near_boundary_concentration(
            domain, boundary, field
        )

        # Analyze far-boundary concentration
        far_boundary_concentration = self._analyze_far_boundary_concentration(
            domain, boundary, field
        )

        # Analyze overall concentration pattern
        overall_concentration = self._analyze_overall_concentration_pattern(
            domain, boundary, field
        )

        results = {
            "near_boundary_concentration": near_boundary_concentration,
            "far_boundary_concentration": far_boundary_concentration,
            "overall_concentration": overall_concentration,
            "concentration_analysis_complete": True,
        }

        self.logger.info("Field concentration analysis completed")
        return results

    def _analyze_near_boundary_concentration(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field: np.ndarray
    ) -> Dict[str, Any]:
        """
        Analyze near-boundary concentration.

        Physical Meaning:
            Analyzes field concentration near boundaries
            for boundary effects analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Near-boundary concentration analysis results.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Define near-boundary region
        boundary_thickness = L / (4 * N)  # Boundary thickness

        # Create near-boundary mask
        near_boundary_mask = self._create_near_boundary_mask(domain, boundary_thickness)

        # Analyze concentration in near-boundary region
        # Handle BlockedField - extract spatial part and compute statistics
        from bhlff.core.sources.blocked_field_generator import BlockedField
        
        if isinstance(field, BlockedField):
            # For BlockedField, compute statistics block-wise
            # Extract spatial part by averaging over phase and temporal dimensions
            # Get spatial slice matching mask dimensions
            N = domain["N"]
            spatial_shape = near_boundary_mask.shape
            
            # Extract spatial slice directly using slicing
            # For 7D BlockedField, we need spatial part (first 3 dims)
            # Average over phase and temporal dimensions (dims 3,4,5,6)
            # Use slicing to get spatial part
            try:
                # Try to get full spatial slice
                # Extract all spatial coordinates, first indices for phase/temporal
                spatial_slice = (slice(None), slice(None), slice(None), 0, 0, 0, 0)
                field_7d_sample = field[spatial_slice]
                
                if len(field_7d_sample.shape) == 7:
                    field_spatial = np.mean(np.abs(field_7d_sample), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(field_7d_sample)
                
                # Ensure field_spatial matches mask shape
                if field_spatial.shape != spatial_shape:
                    min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, spatial_shape))
                    field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                    near_boundary_mask = near_boundary_mask[tuple(slice(0, s) for s in min_shape)]
                
                near_boundary_field = field_spatial[near_boundary_mask]
                field_mean = np.mean(field_spatial)
            except Exception as e:
                # Fallback: use sample block for statistics
                self.logger.warning(f"Could not extract full spatial field from BlockedField: {e}, using sample")
                sample_block = field[tuple(slice(0, min(32, s)) for s in field.shape[:3]) + (0, 0, 0, 0)]
                if len(sample_block.shape) == 7:
                    field_spatial = np.mean(np.abs(sample_block), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(sample_block)
                # Crop to match mask
                if field_spatial.shape != spatial_shape:
                    min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, spatial_shape))
                    field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                    near_boundary_mask = near_boundary_mask[tuple(slice(0, s) for s in min_shape)]
                near_boundary_field = field_spatial[near_boundary_mask]
                field_mean = np.mean(field_spatial)
        else:
            # Regular numpy array
            if len(field.shape) == 7:
                field_spatial = np.mean(np.abs(field), axis=(3, 4, 5, 6))
            else:
                field_spatial = np.abs(field)
            
            # Ensure field_spatial matches mask shape
            if field_spatial.shape != near_boundary_mask.shape:
                min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, near_boundary_mask.shape))
                field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                near_boundary_mask = near_boundary_mask[tuple(slice(0, s) for s in min_shape)]
            
            near_boundary_field = field_spatial[near_boundary_mask]
            field_mean = np.mean(field_spatial)
        
        concentration_metrics = {
            "mean_concentration": np.mean(np.abs(near_boundary_field)),
            "max_concentration": np.max(np.abs(near_boundary_field)),
            "concentration_variance": np.var(np.abs(near_boundary_field)),
            "concentration_ratio": np.mean(np.abs(near_boundary_field)) / field_mean,
        }

        return concentration_metrics

    def _analyze_far_boundary_concentration(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field
    ) -> Dict[str, Any]:
        """
        Analyze far-boundary concentration.

        Physical Meaning:
            Analyzes field concentration far from boundaries
            for boundary effects analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Far-boundary concentration analysis results.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Define far-boundary region
        boundary_thickness = L / (4 * N)  # Boundary thickness

        # Create far-boundary mask
        far_boundary_mask = self._create_far_boundary_mask(domain, boundary_thickness)

        # Analyze concentration in far-boundary region
        # Handle BlockedField - extract spatial part
        from bhlff.core.sources.blocked_field_generator import BlockedField
        
        if isinstance(field, BlockedField):
            # Extract spatial part using slicing
            spatial_shape = far_boundary_mask.shape
            try:
                spatial_slice = (slice(None), slice(None), slice(None), 0, 0, 0, 0)
                field_7d_sample = field[spatial_slice]
                
                if len(field_7d_sample.shape) == 7:
                    field_spatial = np.mean(np.abs(field_7d_sample), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(field_7d_sample)
                
                if field_spatial.shape != spatial_shape:
                    min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, spatial_shape))
                    field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                    far_boundary_mask = far_boundary_mask[tuple(slice(0, s) for s in min_shape)]
                
                far_boundary_field = field_spatial[far_boundary_mask]
                field_mean = np.mean(field_spatial)
            except Exception:
                # Fallback
                sample_block = field[tuple(slice(0, min(32, s)) for s in field.shape[:3]) + (0, 0, 0, 0)]
                if len(sample_block.shape) == 7:
                    field_spatial = np.mean(np.abs(sample_block), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(sample_block)
                if field_spatial.shape != spatial_shape:
                    min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, spatial_shape))
                    field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                    far_boundary_mask = far_boundary_mask[tuple(slice(0, s) for s in min_shape)]
                far_boundary_field = field_spatial[far_boundary_mask]
                field_mean = np.mean(field_spatial)
        else:
            # Regular numpy array
            if len(field.shape) == 7:
                field_spatial = np.mean(np.abs(field), axis=(3, 4, 5, 6))
            else:
                field_spatial = np.abs(field)
            
            if field_spatial.shape != far_boundary_mask.shape:
                min_shape = tuple(min(s, m) for s, m in zip(field_spatial.shape, far_boundary_mask.shape))
                field_spatial = field_spatial[tuple(slice(0, s) for s in min_shape)]
                far_boundary_mask = far_boundary_mask[tuple(slice(0, s) for s in min_shape)]
            
            far_boundary_field = field_spatial[far_boundary_mask]
            field_mean = np.mean(field_spatial)
        
        concentration_metrics = {
            "mean_concentration": np.mean(np.abs(far_boundary_field)),
            "max_concentration": np.max(np.abs(far_boundary_field)),
            "concentration_variance": np.var(np.abs(far_boundary_field)),
            "concentration_ratio": np.mean(np.abs(far_boundary_field)) / field_mean,
        }

        return concentration_metrics

    def _analyze_overall_concentration_pattern(
        self, domain: Dict[str, Any], boundary: BoundaryGeometry, field
    ) -> Dict[str, Any]:
        """
        Analyze overall concentration pattern.

        Physical Meaning:
            Analyzes overall field concentration pattern
            for boundary effects analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary (BoundaryGeometry): Boundary geometry.
            field (np.ndarray): Field data.

        Returns:
            Dict[str, Any]: Overall concentration pattern analysis results.
        """
        # Analyze overall concentration pattern
        # Handle BlockedField - extract spatial part
        from bhlff.core.sources.blocked_field_generator import BlockedField
        
        if isinstance(field, BlockedField):
            # Extract spatial part using slicing
            try:
                spatial_slice = (slice(None), slice(None), slice(None), 0, 0, 0, 0)
                field_7d_sample = field[spatial_slice]
                
                if len(field_7d_sample.shape) == 7:
                    field_spatial = np.mean(np.abs(field_7d_sample), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(field_7d_sample)
            except Exception:
                # Fallback
                sample_block = field[tuple(slice(0, min(32, s)) for s in field.shape[:3]) + (0, 0, 0, 0)]
                if len(sample_block.shape) == 7:
                    field_spatial = np.mean(np.abs(sample_block), axis=(3, 4, 5, 6))
                else:
                    field_spatial = np.abs(sample_block)
        else:
            # Regular numpy array
            if len(field.shape) == 7:
                field_spatial = np.mean(np.abs(field), axis=(3, 4, 5, 6))
            else:
                field_spatial = np.abs(field)
        
        overall_metrics = {
            "total_concentration": np.sum(field_spatial),
            "mean_concentration": np.mean(field_spatial),
            "max_concentration": np.max(field_spatial),
            "concentration_variance": np.var(field_spatial),
            "concentration_skewness": self._calculate_skewness(field_spatial),
            "concentration_kurtosis": self._calculate_kurtosis(field_spatial),
        }

        return overall_metrics

    def _create_near_boundary_mask(
        self, domain: Dict[str, Any], boundary_thickness: float
    ) -> np.ndarray:
        """
        Create near-boundary mask.

        Physical Meaning:
            Creates mask for near-boundary region
            for concentration analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary_thickness (float): Boundary thickness.

        Returns:
            np.ndarray: Near-boundary mask.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create near-boundary mask
        near_boundary_mask = (
            (X <= boundary_thickness)
            | (X >= L - boundary_thickness)
            | (Y <= boundary_thickness)
            | (Y >= L - boundary_thickness)
            | (Z <= boundary_thickness)
            | (Z >= L - boundary_thickness)
        )

        return near_boundary_mask

    def _create_far_boundary_mask(
        self, domain: Dict[str, Any], boundary_thickness: float
    ) -> np.ndarray:
        """
        Create far-boundary mask.

        Physical Meaning:
            Creates mask for far-boundary region
            for concentration analysis.

        Args:
            domain (Dict[str, Any]): Domain parameters.
            boundary_thickness (float): Boundary thickness.

        Returns:
            np.ndarray: Far-boundary mask.
        """
        # Extract domain parameters
        N = domain["N"]
        L = domain["L"]

        # Create coordinate arrays
        x = np.linspace(0, L, N)
        y = np.linspace(0, L, N)
        z = np.linspace(0, L, N)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        # Create far-boundary mask
        far_boundary_mask = (
            (X > boundary_thickness)
            & (X < L - boundary_thickness)
            & (Y > boundary_thickness)
            & (Y < L - boundary_thickness)
            & (Z > boundary_thickness)
            & (Z < L - boundary_thickness)
        )

        return far_boundary_mask

    def _calculate_skewness(self, data: np.ndarray) -> float:
        """
        Calculate skewness.

        Physical Meaning:
            Calculates skewness of field concentration
            for pattern analysis.

        Args:
            data (np.ndarray): Data for skewness calculation.

        Returns:
            float: Skewness value.
        """
        # Calculate skewness
        mean = np.mean(data)
        std = np.std(data)
        if std > 0:
            skewness = np.mean(((data - mean) / std) ** 3)
        else:
            skewness = 0.0

        return skewness

    def _calculate_kurtosis(self, data: np.ndarray) -> float:
        """
        Calculate kurtosis.

        Physical Meaning:
            Calculates kurtosis of field concentration
            for pattern analysis.

        Args:
            data (np.ndarray): Data for kurtosis calculation.

        Returns:
            float: Kurtosis value.
        """
        # Calculate kurtosis
        mean = np.mean(data)
        std = np.std(data)
        if std > 0:
            kurtosis = np.mean(((data - mean) / std) ** 4)
        else:
            kurtosis = 0.0

        return kurtosis
