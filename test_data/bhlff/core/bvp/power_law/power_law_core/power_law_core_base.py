"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Base class for power law core analyzer.

This module provides the base PowerLawCoreBase class with common
initialization and main analysis methods.
"""

from typing import Dict, Any, List
import logging

from ...bvp_core.bvp_core_facade import BVPCoreFacade as BVPCore
from ..power_law_comparison import PowerLawComparison
from ..power_law_optimization import PowerLawOptimization
from ..power_law_statistics import PowerLawStatistics


class PowerLawCoreBase:
    """
    Base class for core power law analyzer.
    
    Physical Meaning:
        Provides base functionality for core analysis of power law behavior
        in BVP envelope fields, coordinating specialized analysis modules.
    """
    
    def __init__(self, bvp_core: BVPCore = None):
        """
        Initialize power law analyzer.
        
        Args:
            bvp_core (BVPCore): BVP core instance for field access.
        """
        self.bvp_core = bvp_core
        self.logger = logging.getLogger(__name__)
        
        # Analysis parameters
        self.statistical_significance = 0.05
        self.optimization_tolerance = 1e-6
        self.max_optimization_iterations = 100
        
        # Initialize specialized modules
        self.comparison = PowerLawComparison(bvp_core)
        self.optimization = PowerLawOptimization(bvp_core)
        self.statistics = PowerLawStatistics(bvp_core)
    
    def analyze_envelope_power_laws(self, envelope) -> List[Dict[str, Any]]:
        """
        Analyze power law behavior in envelope field.
        
        Physical Meaning:
            Analyzes power law behavior in the envelope field by
            identifying tail regions and fitting power laws to them.
            
        Args:
            envelope: 7D envelope field data.
            
        Returns:
            List[Dict[str, Any]]: List of power law analysis results for each region.
        """
        self.logger.info("Starting envelope power law analysis")
        
        # Identify tail regions
        tail_regions = self._identify_tail_regions(envelope)
        
        # Analyze each region
        results = []
        for region in tail_regions:
            region_result = self._analyze_region_power_law(envelope, region)
            results.append(region_result)
        
        self.logger.info(
            f"Envelope power law analysis completed: {len(results)} regions analyzed"
        )
        return results
    
    def analyze_power_law_tails(self, envelope) -> Dict[str, Any]:
        """
        Analyze power law tails in BVP envelope field.
        
        Physical Meaning:
            Analyzes the power law decay of BVP envelope amplitude in the
            tail region, which characterizes the field's long-range behavior
            in homogeneous medium according to the 7D phase field theory.
            
        Mathematical Foundation:
            Computes power law decay A(r) ∝ r^(2β-3) in the tail region,
            where β is the fractional order and r is the radial distance
            from the field center.
            
        Args:
            envelope: BVP envelope field to analyze.
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - tail_slope: Power law exponent α
                - r_squared: R-squared value of the fit
                - power_law_range: Range of radial distances used
        """
        # Get power law analysis results
        power_law_results = self.analyze_envelope_power_laws(envelope)
        
        if not power_law_results:
            return {"tail_slope": 0.0, "r_squared": 0.0, "power_law_range": [0.0, 0.0]}
        
        # Use the first (most significant) result
        first_result = power_law_results[0]
        
        return {
            "tail_slope": first_result.get("slope", 0.0),
            "r_squared": first_result.get("r_squared", 0.0),
            "power_law_range": first_result.get("range", [0.0, 0.0]),
        }

