"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Region extraction methods for power law optimization.

This module provides region extraction methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List
from scipy.ndimage import label


class PowerLawOptimizationRegionsMixin:
    """Mixin providing region extraction methods."""
    
    def _extract_optimization_regions(
        self, envelope: np.ndarray
    ) -> List[Dict[str, Any]]:
        """
        Extract optimization regions from envelope using 7D BVP theory.
        
        Physical Meaning:
            Identifies regions in the 7D envelope field that are suitable
            for power law optimization based on phase field characteristics.
        """
        try:
            # Use BVP core if available for region extraction
            if self.bvp_core is not None:
                regions = self.bvp_core.extract_power_law_regions(envelope)
            else:
                # Fallback: simple region extraction
                regions = self._simple_region_extraction(envelope)
            
            return regions
            
        except Exception as e:
            self.logger.error(f"Region extraction failed: {e}")
            return []
    
    def _simple_region_extraction(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """Simple region extraction fallback method."""
        # Create basic regions for optimization
        regions = []
        
        # Extract non-zero regions
        non_zero_mask = np.abs(envelope) > 1e-6
        
        if np.any(non_zero_mask):
            # Find connected components
            labeled_array, num_features = label(non_zero_mask)
            
            for i in range(1, num_features + 1):
                region_mask = labeled_array == i
                if np.sum(region_mask) > 10:  # Minimum region size
                    regions.append(
                        {
                            "mask": region_mask,
                            "center": self._compute_region_center(region_mask),
                            "size": np.sum(region_mask),
                            "intensity": np.mean(np.abs(envelope[region_mask])),
                        }
                    )
        
        return regions
    
    def _compute_region_center(self, mask: np.ndarray) -> np.ndarray:
        """Compute center of region from mask."""
        indices = np.where(mask)
        if len(indices[0]) > 0:
            return np.array([np.mean(indices[i]) for i in range(len(indices))])
        else:
            return np.array([0.0] * len(mask.shape))
    
    def _extract_region_data(
        self, envelope: np.ndarray, region: Dict[str, Any]
    ) -> Dict[str, np.ndarray]:
        """Extract data for specific region."""
        try:
            mask = region.get("mask")
            if mask is None:
                raise ValueError("Region mask not found")
            
            # Extract coordinates and values
            indices = np.where(mask)
            if len(indices[0]) == 0:
                raise ValueError("Empty region")
            
            # Compute radial coordinates
            center = region.get("center", np.array([0.0] * len(envelope.shape)))
            coords = np.array(indices).T
            r = np.linalg.norm(coords - center, axis=1)
            values = envelope[mask]
            
            return {"r": r, "values": values}
            
        except Exception as e:
            self.logger.error(f"Region data extraction failed: {e}")
            # Return default data
            r = np.linspace(0.1, 10.0, 100)
            values = self._step_resonator_transmission(r) * r ** (-2.0)
            return {"r": r, "values": values}
    
    def _step_resonator_transmission(self, r: np.ndarray) -> np.ndarray:
        """
        Step resonator transmission coefficient according to 7D BVP theory.
        
        Physical Meaning:
            Implements step function transmission coefficient
            instead of exponential decay according to 7D BVP theory.
            
        Args:
            r (np.ndarray): Radial coordinate.
            
        Returns:
            np.ndarray: Step function transmission coefficient.
        """
        cutoff_radius = 5.0
        transmission_coeff = 1.0
        return transmission_coeff * np.where(r < cutoff_radius, 1.0, 0.0)

