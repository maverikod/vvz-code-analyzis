"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for power law optimization.

This module provides the base PowerLawOptimizationBase class with common
initialization and main optimization methods.
"""

import numpy as np
from typing import Dict, Any, List
import logging

from ...bvp_core.bvp_core_facade import BVPCoreFacade as BVPCore


class PowerLawOptimizationBase:
    """
    Base class for power law optimization analyzer.
    
    Physical Meaning:
        Provides base functionality for optimization of power law fits
        for better accuracy and reliability.
    """
    
    def __init__(self, bvp_core: BVPCore = None):
        """Initialize power law optimization analyzer."""
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        self.optimization_tolerance = 1e-6
        self.max_optimization_iterations = 100
    
    def optimize_power_law_fits(self, envelope: np.ndarray) -> Dict[str, Any]:
        """
        Optimize power law fits for better accuracy using full 7D BVP theory.
        
        Physical Meaning:
            Optimizes power law fits using advanced fitting techniques
            based on 7D phase field theory principles, including
            iterative refinement, parameter adjustment, and quality assessment.
            
        Mathematical Foundation:
            Implements complete optimization using scipy.optimize with
            proper convergence criteria and error handling.
            
        Args:
            envelope (np.ndarray): 7D envelope field data.
            
        Returns:
            Dict[str, Any]: Comprehensive optimization results.
        """
        self.logger.info("Starting power law optimization using 7D BVP theory")
        
        try:
            # Extract regions from envelope using 7D phase field analysis
            regions = self._extract_optimization_regions(envelope)
            
            if not regions:
                raise ValueError("No valid regions found for optimization")
            
            # Initialize optimization results
            optimization_results = []
            total_improvement = 0.0
            successful_optimizations = 0
            
            # Optimize each region
            for region_idx, region in enumerate(regions):
                try:
                    # Perform full optimization for this region
                    region_result = self._optimize_region_fit(envelope, region)
                    optimization_results.append(region_result)
                    
                    if region_result.get("optimization_successful", False):
                        successful_optimizations += 1
                        total_improvement += region_result.get("improvement", 0.0)
                    
                except Exception as e:
                    self.logger.warning(f"Region {region_idx} optimization failed: {e}")
                    # Add failed region result
                    optimization_results.append(
                        {
                            "region_index": region_idx,
                            "optimization_successful": False,
                            "error": str(e),
                        }
                    )
            
            # Calculate overall optimization quality
            optimization_quality = self._calculate_optimization_quality(
                optimization_results
            )
            
            # Compute final results
            results = {
                "optimization_successful": successful_optimizations > 0,
                "successful_regions": successful_optimizations,
                "total_regions": len(regions),
                "success_rate": (
                    successful_optimizations / len(regions) if regions else 0.0
                ),
                "average_improvement": total_improvement
                / max(successful_optimizations, 1),
                "total_improvement": total_improvement,
                "optimization_quality": optimization_quality,
                "region_results": optimization_results,
                "convergence_achieved": optimization_quality.get("overall_quality", 0.0)
                > 0.7,
            }
            
            self.logger.info(
                f"Power law optimization completed: {successful_optimizations}/{len(regions)} regions successful"
            )
            return results
            
        except Exception as e:
            self.logger.error(f"Power law optimization failed: {e}")
            return {
                "optimization_successful": False,
                "error": str(e),
                "successful_regions": 0,
                "total_regions": 0,
                "success_rate": 0.0,
                "average_improvement": 0.0,
                "total_improvement": 0.0,
                "optimization_quality": {"overall_quality": 0.0},
                "region_results": [],
                "convergence_achieved": False,
            }

