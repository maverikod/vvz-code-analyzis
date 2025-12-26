"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Region identification methods for power law core analyzer.

This module provides region identification methods as a mixin class.
"""

import numpy as np
from typing import Dict, Any, List


class PowerLawCoreRegionsMixin:
    """Mixin providing region identification methods."""
    
    def _identify_tail_regions(self, envelope: np.ndarray) -> List[Dict[str, Any]]:
        """
        Identify tail regions in the envelope field.
        
        Physical Meaning:
            Identifies regions in the envelope field that exhibit
            power law behavior, typically in the tails of the distribution.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            List[Dict[str, Any]]: List of identified tail regions.
        """
        tail_regions = []
        
        # Analyze each dimension
        for dim in range(envelope.ndim):
            # Create slice for this dimension
            dim_slice = np.take(envelope, envelope.shape[dim] // 2, axis=dim)
            
            # Find tail regions in this dimension
            dim_regions = self._find_dimension_tail_regions(dim_slice, dim)
            tail_regions.extend(dim_regions)
        
        return tail_regions
    
    def _find_dimension_tail_regions(
        self, dim_slice: np.ndarray, dimension: int
    ) -> List[Dict[str, Any]]:
        """
        Find tail regions in a specific dimension.
        
        Physical Meaning:
            Finds regions in a specific dimension that exhibit
            power law behavior based on amplitude thresholds.
            
        Args:
            dim_slice (np.ndarray): Slice of envelope field for this dimension.
            dimension (int): Dimension index.
            
        Returns:
            List[Dict[str, Any]]: List of tail regions in this dimension.
        """
        regions = []
        
        # Calculate amplitude threshold
        amplitude_threshold = 0.1 * np.max(np.abs(dim_slice))
        
        # Create mask for tail regions
        mask = np.abs(dim_slice) > amplitude_threshold
        
        # Find contiguous regions
        contiguous_regions = self._find_contiguous_regions(mask)
        
        # Convert to region dictionaries
        for region_indices in contiguous_regions:
            if len(region_indices) > 5:  # Minimum region size
                region = {
                    "dimension": dimension,
                    "indices": region_indices,
                    "start_index": min(region_indices),
                    "end_index": max(region_indices),
                    "size": len(region_indices),
                }
                regions.append(region)
        
        return regions
    
    def _find_contiguous_regions(self, mask: np.ndarray) -> List[List[int]]:
        """
        Find contiguous regions in a boolean mask.
        
        Physical Meaning:
            Finds contiguous regions of True values in a boolean mask,
            representing regions that satisfy the tail criteria.
            
        Args:
            mask (np.ndarray): Boolean mask.
            
        Returns:
            List[List[int]]: List of contiguous regions as lists of indices.
        """
        regions = []
        current_region = []
        
        for i, value in enumerate(mask):
            if np.any(value) if hasattr(value, "__len__") else value:
                current_region.append(i)
            else:
                if current_region:
                    regions.append(current_region)
                    current_region = []
        
        # Add final region if exists
        if current_region:
            regions.append(current_region)
        
        return regions
    
    def _analyze_region_power_law(
        self, envelope: np.ndarray, region: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze power law behavior in a specific region.
        
        Physical Meaning:
            Analyzes power law behavior in a specific region of the
            envelope field by fitting power law functions to the data.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            region (Dict[str, Any]): Region information.
            
        Returns:
            Dict[str, Any]: Power law analysis results for this region.
        """
        # Extract region data
        region_data = self._extract_region_data(envelope, region)
        
        # Fit power law
        power_law_fit = self._fit_power_law(region_data)
        
        # Calculate fitting quality
        fitting_quality = self._calculate_fitting_quality(region_data, power_law_fit)
        
        return {
            "region_info": region,
            "power_law_fit": power_law_fit,
            "fitting_quality": fitting_quality,
            "region_data_summary": {
                "data_points": len(region_data.get("amplitudes", [])),
                "amplitude_range": [
                    np.min(region_data.get("amplitudes", [0])),
                    np.max(region_data.get("amplitudes", [0])),
                ],
                "distance_range": [
                    np.min(region_data.get("distances", [0])),
                    np.max(region_data.get("distances", [0])),
                ],
            },
        }
    
    def _extract_region_data(
        self, envelope: np.ndarray, region: Dict[str, Any]
    ) -> Dict[str, np.ndarray]:
        """
        Extract data from a specific region.
        
        Physical Meaning:
            Extracts relevant data from a specific region of the
            envelope field for power law analysis.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            region (Dict[str, Any]): Region information.
            
        Returns:
            Dict[str, np.ndarray]: Extracted region data.
        """
        dim = region["dimension"]
        indices = region["indices"]
        
        # Extract amplitudes and distances
        amplitudes = []
        distances = []
        
        for i, idx in enumerate(indices):
            # Create slice for this index
            slice_indices = [slice(None)] * envelope.ndim
            slice_indices[dim] = idx
            
            # Extract amplitude
            amplitude = np.abs(envelope[tuple(slice_indices)])
            amplitudes.append(amplitude)
            
            # Calculate distance from center
            center = envelope.shape[dim] // 2
            distance = abs(idx - center)
            distances.append(distance)
        
        return {"amplitudes": np.array(amplitudes), "distances": np.array(distances)}

